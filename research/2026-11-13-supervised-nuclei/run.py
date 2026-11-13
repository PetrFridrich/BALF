"""Supervised background/cytoplasm/nucleus segmentation of BALF images.

Reproduces the Random Forest result from the author's master's thesis and
tries to beat it, on the same 50 pixel-labelled images and the same protocol:
5-fold cross-validation split BY IMAGE (the thesis uses k_fold.split(paths)),
so the numbers are directly comparable.

Two bets on top of the thesis setup:

* Colour deconvolution. The May-Grunwald-Giemsa stain is two dyes, so optical
  density separates nucleus from cytoplasm on physical grounds, where raw RGB
  does not. Unsupervised clustering on raw RGB managed only IoU 0.50, which is
  the symptom this is meant to fix.
* Histogram gradient boosting, which usually beats a forest on tabular data
  and stays cheap on CPU.

Run:  uv run python run.py [--images N] [--per-image-samples N]
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

THESIS = Path("/home/user/fido18246/ing_thesis/Data")
OUT_DIR = Path(__file__).parent / "outputs"

CLASS_NAMES = {0: "pozadi", 1: "cytoplazma", 2: "jadro"}
SIGMAS = (1, 2, 4, 8)

# IoU is estimated on a uniform pixel subsample per test image: both the
# intersection and the union scale with the sampling rate, so the ratio holds.
EVAL_PIXELS = 300_000
RANDOM_STATE = 42


def optical_density(image: np.ndarray) -> np.ndarray:
    """Beer-Lambert optical density — the space stain separation works in."""
    return -np.log10((image.astype(np.float32) + 1.0) / 256.0)


def features(image: np.ndarray) -> np.ndarray:
    """Per-pixel feature stack, shape (H*W, n_features), float32."""
    from skimage.color import rgb2gray
    from skimage.feature import hessian_matrix, hessian_matrix_eigvals
    from skimage.filters import gaussian, laplace, sobel

    planes: list[np.ndarray] = []

    rgb = image.astype(np.float32) / 255.0
    planes.extend(rgb[..., c] for c in range(3))
    planes.extend(optical_density(image)[..., c] for c in range(3))

    gray = rgb2gray(rgb).astype(np.float32)
    planes.append(gray)

    for sigma in SIGMAS:
        smoothed = gaussian(gray, sigma=sigma).astype(np.float32)
        planes.append(smoothed)
        planes.append(sobel(smoothed).astype(np.float32))
        planes.append(laplace(smoothed).astype(np.float32))
        # Hessian eigenvalues separate blob-like nuclei from flat cytoplasm.
        hxx, hxy, hyy = hessian_matrix(smoothed, sigma=sigma, order="rc", use_gaussian_derivatives=False)
        large, small = hessian_matrix_eigvals((hxx, hxy, hyy))
        planes.append(large.astype(np.float32))
        planes.append(small.astype(np.float32))

    return np.stack([p.ravel() for p in planes], axis=1)


def load(name: str) -> tuple[np.ndarray, np.ndarray]:
    image = np.array(Image.open(THESIS / "Images_ALL" / f"{name}.png").convert("RGB"))
    labels = np.loadtxt(THESIS / "Labels_ALL" / f"{name}.txt", dtype=np.uint8)
    return image, labels


def macro_jaccard(truth: np.ndarray, predicted: np.ndarray) -> tuple[float, dict]:
    per_class = {}
    scores = []
    for value, name in CLASS_NAMES.items():
        t, p = truth == value, predicted == value
        union = np.logical_or(t, p).sum()
        score = float(np.logical_and(t, p).sum() / union) if union else 0.0
        per_class[name] = round(score, 4)
        scores.append(score)
    return round(float(np.mean(scores)), 4), per_class


def build_models():
    from sklearn.ensemble import (
        ExtraTreesClassifier,
        HistGradientBoostingClassifier,
        RandomForestClassifier,
    )

    return {
        "RandomForest": RandomForestClassifier(
            n_estimators=100, n_jobs=-1, random_state=RANDOM_STATE
        ),
        "HistGradientBoosting": HistGradientBoostingClassifier(
            max_iter=200, random_state=RANDOM_STATE
        ),
        "ExtraTrees": ExtraTreesClassifier(
            n_estimators=100, n_jobs=-1, random_state=RANDOM_STATE
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--images", type=int, default=50)
    parser.add_argument("--per-image-samples", type=int, default=30_000)
    args = parser.parse_args()

    from sklearn.model_selection import KFold

    OUT_DIR.mkdir(exist_ok=True)
    names = sorted(p.stem for p in (THESIS / "Labels_ALL").glob("*.txt"))[: args.images]
    rng = np.random.default_rng(RANDOM_STATE)

    # --- feature extraction, once per image -------------------------------
    print(f"Počítám features pro {len(names)} snímků…", flush=True)
    train_x: dict[str, np.ndarray] = {}
    train_y: dict[str, np.ndarray] = {}
    eval_x: dict[str, np.ndarray] = {}
    eval_y: dict[str, np.ndarray] = {}

    start = time.perf_counter()
    for i, name in enumerate(names):
        image, labels = load(name)
        X = features(image)
        y = labels.ravel()

        # Stratified subsample for training: rare classes must not vanish.
        picked = []
        for value in CLASS_NAMES:
            idx = np.flatnonzero(y == value)
            if idx.size:
                take = min(args.per_image_samples // len(CLASS_NAMES), idx.size)
                picked.append(rng.choice(idx, size=take, replace=False))
        pick = np.concatenate(picked)
        train_x[name], train_y[name] = X[pick], y[pick]

        # Uniform subsample for evaluation: must keep the true class balance.
        ev = rng.choice(y.size, size=min(EVAL_PIXELS, y.size), replace=False)
        eval_x[name], eval_y[name] = X[ev], y[ev]

        if (i + 1) % 10 == 0:
            print(f"  {i + 1}/{len(names)}  ({time.perf_counter() - start:.0f} s)", flush=True)

    print(f"features hotovy za {time.perf_counter() - start:.0f} s, "
          f"{train_x[names[0]].shape[1]} příznaků\n", flush=True)

    # --- 5-fold cross-validation by image ---------------------------------
    results: dict[str, list] = {k: [] for k in build_models()}
    folds = KFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)

    for fold, (train_idx, test_idx) in enumerate(folds.split(names), start=1):
        tr = [names[i] for i in train_idx]
        te = [names[i] for i in test_idx]
        Xtr = np.concatenate([train_x[n] for n in tr])
        ytr = np.concatenate([train_y[n] for n in tr])
        Xte = np.concatenate([eval_x[n] for n in te])
        yte = np.concatenate([eval_y[n] for n in te])

        print(f"fold {fold}/5 — trénink {Xtr.shape[0]:,} px, test {Xte.shape[0]:,} px", flush=True)

        for label, model in build_models().items():
            t0 = time.perf_counter()
            model.fit(Xtr, ytr)
            fit_seconds = time.perf_counter() - t0

            t0 = time.perf_counter()
            predicted = model.predict(Xte)
            predict_seconds = time.perf_counter() - t0

            jaccard, per_class = macro_jaccard(yte, predicted)
            accuracy = round(float((predicted == yte).mean()), 4)
            results[label].append(
                {
                    "fold": fold,
                    "jaccard_macro": jaccard,
                    "accuracy": accuracy,
                    "per_class_jaccard": per_class,
                    "fit_seconds": round(fit_seconds, 1),
                    "predict_seconds": round(predict_seconds, 1),
                }
            )
            print(
                f"  {label:22} Jaccard {jaccard:.4f}  acc {accuracy:.4f}  "
                f"jádro {per_class['jadro']:.3f}  cyto {per_class['cytoplazma']:.3f}  "
                f"({fit_seconds:.0f} s)",
                flush=True,
            )
        print(flush=True)

    # --- summary ----------------------------------------------------------
    summary = {}
    for label, runs in results.items():
        j = [r["jaccard_macro"] for r in runs]
        summary[label] = {
            "jaccard_macro_mean": round(float(np.mean(j)), 4),
            "jaccard_macro_std": round(float(np.std(j)), 4),
            "accuracy_mean": round(float(np.mean([r["accuracy"] for r in runs])), 4),
            "nucleus_jaccard_mean": round(
                float(np.mean([r["per_class_jaccard"]["jadro"] for r in runs])), 4
            ),
            "cytoplasm_jaccard_mean": round(
                float(np.mean([r["per_class_jaccard"]["cytoplazma"] for r in runs])), 4
            ),
            "fit_seconds_mean": round(float(np.mean([r["fit_seconds"] for r in runs])), 1),
        }

    print("=== souhrn (5-fold CV po snímcích) ===", flush=True)
    for label, s in sorted(summary.items(), key=lambda kv: -kv[1]["jaccard_macro_mean"]):
        print(
            f"  {label:22} Jaccard {s['jaccard_macro_mean']:.4f} ± {s['jaccard_macro_std']:.4f}"
            f"   jádro {s['nucleus_jaccard_mean']:.3f}   trénink {s['fit_seconds_mean']:.0f} s",
            flush=True,
        )

    (OUT_DIR / "metrics.json").write_text(
        json.dumps(
            {
                "protocol": "5-fold CV split by image; IoU on uniform pixel subsample",
                "images": len(names),
                "features": int(train_x[names[0]].shape[1]),
                "summary": summary,
                "folds": results,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\n-> {OUT_DIR / 'metrics.json'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
