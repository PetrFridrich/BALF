"""From semantic maps to instance masks, and a comparison against Cellpose.

The supervised experiment left a 3-class map (background / cytoplasm /
nucleus) at Jaccard 0.77. That is not yet what the project needs: phase 1 owes
instance masks, one outline per cell.

This joins the two halves and puts them against the pretrained baseline:

* train histogram gradient boosting on the thesis-labelled images, predict a
  3-class map on held-out ones;
* seed marker-controlled watershed from the PREDICTED nuclei, not ground-truth
  ones, so the number reflects a pipeline that could actually run;
* run Cellpose on the same held-out images;
* compare counts, size distributions and foreground agreement with the labels.

No instance ground truth exists, so instance quality itself cannot be scored.
Foreground IoU against the labels is the one honest number here; the rest is
descriptive, plus overlays to judge by eye.

Run:  uv run python run.py [--test N]
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

Image.MAX_IMAGE_PIXELS = None

THESIS = Path("/home/user/fido18246/ing_thesis/Data")
OUT_DIR = Path(__file__).parent / "outputs"

BACKGROUND, CYTOPLASM, NUCLEUS = 0, 1, 2
SIGMAS = (1, 2, 4, 8)
TRAIN_SAMPLES_PER_IMAGE = 30_000
RANDOM_STATE = 42

# Cellpose rescales internally to ~30px objects; prescaling first was an 11.6x
# win in the baseline experiment. Cells here run ~60px at 2012x1518 (half the
# project resolution, so half the ~120px measured on the full-size images).
CELL_DIAMETER_PX = 60
NATIVE_DIAMETER_PX = 30

MIN_NUCLEUS_AREA = 50
PREVIEW_MAX_WIDTH = 1400


# --------------------------------------------------------------------------
# features (same 27 as the supervised experiment)
# --------------------------------------------------------------------------

def features(image: np.ndarray) -> np.ndarray:
    from skimage.color import rgb2gray
    from skimage.feature import hessian_matrix, hessian_matrix_eigvals
    from skimage.filters import gaussian, laplace, sobel

    planes: list[np.ndarray] = []
    rgb = image.astype(np.float32) / 255.0
    planes.extend(rgb[..., c] for c in range(3))

    optical_density = -np.log10((image.astype(np.float32) + 1.0) / 256.0)
    planes.extend(optical_density[..., c] for c in range(3))

    gray = rgb2gray(rgb).astype(np.float32)
    planes.append(gray)

    for sigma in SIGMAS:
        smoothed = gaussian(gray, sigma=sigma).astype(np.float32)
        planes.append(smoothed)
        planes.append(sobel(smoothed).astype(np.float32))
        planes.append(laplace(smoothed).astype(np.float32))
        hxx, hxy, hyy = hessian_matrix(
            smoothed, sigma=sigma, order="rc", use_gaussian_derivatives=False
        )
        large, small = hessian_matrix_eigvals((hxx, hxy, hyy))
        planes.append(large.astype(np.float32))
        planes.append(small.astype(np.float32))

    return np.stack([p.ravel() for p in planes], axis=1)


def load(name: str) -> tuple[np.ndarray, np.ndarray]:
    image = np.array(Image.open(THESIS / "Images_ALL" / f"{name}.png").convert("RGB"))
    labels = np.loadtxt(THESIS / "Labels_ALL" / f"{name}.txt", dtype=np.uint8)
    return image, labels


# --------------------------------------------------------------------------
# instance extraction
# --------------------------------------------------------------------------

def watershed_instances(semantic: np.ndarray) -> np.ndarray:
    """Split the predicted cell body using predicted nuclei as markers."""
    from skimage.segmentation import watershed

    body = semantic > BACKGROUND
    # Drop speck-sized nuclei: they would each seed a spurious instance.
    markers, count = ndi.label(semantic == NUCLEUS)
    if count:
        areas = np.bincount(markers.ravel())
        too_small = np.flatnonzero(areas < MIN_NUCLEUS_AREA)
        markers[np.isin(markers, too_small)] = 0
        markers, _ = ndi.label(markers > 0)

    distance = ndi.distance_transform_edt(body)
    return watershed(-distance, markers, mask=body)


def cellpose_instances(model, image: np.ndarray) -> np.ndarray:
    scale = NATIVE_DIAMETER_PX / CELL_DIAMETER_PX
    h, w = image.shape[:2]
    small = np.array(
        Image.fromarray(image).resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    )
    masks = model.eval(small, diameter=NATIVE_DIAMETER_PX)[0]
    return np.array(
        Image.fromarray(masks.astype(np.int32), mode="I").resize((w, h), Image.NEAREST)
    )


def instance_stats(masks: np.ndarray) -> dict:
    ids = np.unique(masks)
    ids = ids[ids != 0]
    if ids.size == 0:
        return {"count": 0, "coverage_pct": 0.0}
    areas = np.bincount(masks.ravel())
    areas = areas[1:][areas[1:] > 0]
    diameters = 2 * np.sqrt(areas / np.pi)
    return {
        "count": int(ids.size),
        "coverage_pct": round(100 * float((masks > 0).mean()), 2),
        "diameter_median_px": round(float(np.median(diameters)), 1),
        "diameter_p10_px": round(float(np.percentile(diameters, 10)), 1),
        "diameter_p90_px": round(float(np.percentile(diameters, 90)), 1),
    }


def foreground_iou(masks: np.ndarray, labels: np.ndarray) -> float:
    a, b = masks > 0, labels > BACKGROUND
    union = np.logical_or(a, b).sum()
    return round(float(np.logical_and(a, b).sum() / union), 3) if union else 0.0


def save_preview(image: np.ndarray, masks: np.ndarray, path: Path) -> None:
    from skimage.segmentation import find_boundaries

    h, w = image.shape[:2]
    scale = min(1.0, PREVIEW_MAX_WIDTH / w)
    size = (int(w * scale), int(h * scale))
    small = np.array(Image.fromarray(image).resize(size, Image.LANCZOS))
    small_masks = np.array(
        Image.fromarray(masks.astype(np.int32), mode="I").resize(size, Image.NEAREST)
    )
    small[find_boundaries(small_masks, mode="outer")] = [255, 0, 0]
    Image.fromarray(small).save(path, quality=88, optimize=True)


# --------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", type=int, default=10)
    args = parser.parse_args()

    from cellpose import models as cellpose_models
    from sklearn.ensemble import HistGradientBoostingClassifier

    OUT_DIR.mkdir(exist_ok=True)
    names = sorted(p.stem for p in (THESIS / "Labels_ALL").glob("*.txt"))
    test_names = names[: args.test]
    train_names = names[args.test :]
    rng = np.random.default_rng(RANDOM_STATE)

    print(f"trénink {len(train_names)} snímků, test {len(test_names)}\n", flush=True)

    # --- train the semantic model ---------------------------------------
    print("Učím semantický model…", flush=True)
    start = time.perf_counter()
    xs, ys = [], []
    for name in train_names:
        image, labels = load(name)
        X, y = features(image), labels.ravel()
        # Uniform sampling keeps the real 88/7/5 balance; the previous
        # experiment showed balancing costs 0.05 Jaccard.
        pick = rng.choice(y.size, size=min(TRAIN_SAMPLES_PER_IMAGE, y.size), replace=False)
        xs.append(X[pick])
        ys.append(y[pick])
    Xtr, ytr = np.concatenate(xs), np.concatenate(ys)
    del xs, ys

    model = HistGradientBoostingClassifier(max_iter=200, random_state=RANDOM_STATE)
    model.fit(Xtr, ytr)
    print(f"  natrénováno na {Xtr.shape[0]:,} px za {time.perf_counter() - start:.0f} s\n", flush=True)
    del Xtr, ytr

    cellpose = cellpose_models.CellposeModel(gpu=False)

    rows = []
    for i, name in enumerate(test_names, start=1):
        image, labels = load(name)
        h, w = labels.shape

        t0 = time.perf_counter()
        semantic = model.predict(features(image)).reshape(h, w).astype(np.uint8)
        semantic_seconds = time.perf_counter() - t0

        t0 = time.perf_counter()
        ws = watershed_instances(semantic)
        watershed_seconds = time.perf_counter() - t0

        t0 = time.perf_counter()
        cp = cellpose_instances(cellpose, image)
        cellpose_seconds = time.perf_counter() - t0

        row = {
            "image": name,
            "semantic_seconds": round(semantic_seconds, 1),
            "watershed": {
                **instance_stats(ws),
                "foreground_iou_vs_labels": foreground_iou(ws, labels),
                "seconds": round(semantic_seconds + watershed_seconds, 1),
            },
            "cellpose": {
                **instance_stats(cp),
                "foreground_iou_vs_labels": foreground_iou(cp, labels),
                "seconds": round(cellpose_seconds, 1),
            },
        }
        rows.append(row)

        print(
            f"  [{i:2}/{len(test_names)}] {name}\n"
            f"       watershed {row['watershed']['count']:4} instancí  "
            f"medián {row['watershed']['diameter_median_px']:6.1f} px  "
            f"IoU popředí {row['watershed']['foreground_iou_vs_labels']:.3f}  "
            f"({row['watershed']['seconds']:.0f} s)\n"
            f"       cellpose  {row['cellpose']['count']:4} instancí  "
            f"medián {row['cellpose']['diameter_median_px']:6.1f} px  "
            f"IoU popředí {row['cellpose']['foreground_iou_vs_labels']:.3f}  "
            f"({row['cellpose']['seconds']:.0f} s)",
            flush=True,
        )

        if i <= 3:
            save_preview(image, ws, OUT_DIR / f"{name}_watershed.jpg")
            save_preview(image, cp, OUT_DIR / f"{name}_cellpose.jpg")

    def avg(method: str, key: str) -> float:
        return round(float(np.mean([r[method][key] for r in rows])), 3)

    summary = {
        method: {
            "count_mean": avg(method, "count"),
            "coverage_pct_mean": avg(method, "coverage_pct"),
            "diameter_median_mean": avg(method, "diameter_median_px"),
            "foreground_iou_mean": avg(method, "foreground_iou_vs_labels"),
            "seconds_mean": avg(method, "seconds"),
        }
        for method in ("watershed", "cellpose")
    }

    print("\n=== souhrn ===", flush=True)
    print(f"{'metoda':12} {'instancí':>9} {'pokrytí':>9} {'medián':>8} {'IoU popředí':>12} {'čas':>7}", flush=True)
    for method, s in summary.items():
        print(
            f"{method:12} {s['count_mean']:9.1f} {s['coverage_pct_mean']:8.1f}% "
            f"{s['diameter_median_mean']:8.1f} {s['foreground_iou_mean']:12.3f} "
            f"{s['seconds_mean']:6.0f} s",
            flush=True,
        )

    (OUT_DIR / "metrics.json").write_text(
        json.dumps(
            {
                "note": "instance quality is NOT scored - no instance ground truth exists",
                "train_images": len(train_names),
                "test_images": len(test_names),
                "summary": summary,
                "per_image": rows,
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
