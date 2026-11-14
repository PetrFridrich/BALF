"""Cellpose at the right scale, post-processed masks, and a fusion of both.

Corrects a measurement error. The labelled thesis images are 2012x1518, which
is both half of 4024x3036 and a quarter-crop of it, so the two cannot be told
apart by size. Nucleus diameter settles it: 69.7px in the thesis labels
against ~69px measured on the full-size images. They are CROPS at the original
scale, so cells run ~120px, not ~60px.

The previous experiment ran Cellpose at diameter 60, half the true size, which
the Cellpose docs warn causes over-splitting. Its comparison is therefore void
and is repeated here.

Five methods on the same held-out images:

* cellpose_d60   - the wrong setting, kept so the size of the error is on record
* cellpose_d120  - Cellpose at the true scale
* watershed      - our supervised map, nuclei seed watershed (as before)
* watershed_pp   - the same with morphological post-processing
* fusion         - Cellpose instances as markers, our predicted foreground as
                   the mask: each method supplies what it is good at. Cellpose
                   finds clean cells and skips debris; our model knows how far
                   the cytoplasm reaches.

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

TRUE_CELL_DIAMETER_PX = 120  # measured: crops at original scale
WRONG_CELL_DIAMETER_PX = 60  # what the previous experiment used
NATIVE_DIAMETER_PX = 30

MIN_NUCLEUS_AREA = 50
MIN_INSTANCE_AREA = 400
SMOOTH_RADIUS = 3
PREVIEW_MAX_WIDTH = 1400


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


def clean_markers(marker_source: np.ndarray, min_area: int) -> np.ndarray:
    markers, count = ndi.label(marker_source)
    if count:
        areas = np.bincount(markers.ravel())
        markers[np.isin(markers, np.flatnonzero(areas < min_area))] = 0
        markers, _ = ndi.label(markers > 0)
    return markers


def watershed_from(markers: np.ndarray, body: np.ndarray) -> np.ndarray:
    from skimage.segmentation import watershed

    distance = ndi.distance_transform_edt(body)
    return watershed(-distance, markers, mask=body)


def post_process(masks: np.ndarray) -> np.ndarray:
    """Smooth ragged borders, fill holes, drop specks — per instance."""
    from skimage.morphology import disk, binary_closing, remove_small_objects

    out = np.zeros_like(masks)
    footprint = disk(SMOOTH_RADIUS)
    objects = ndi.find_objects(masks)
    next_id = 1
    for index, window in enumerate(objects, start=1):
        if window is None:
            continue
        pad = SMOOTH_RADIUS + 2
        ys, xs = window
        y0, y1 = max(0, ys.start - pad), min(masks.shape[0], ys.stop + pad)
        x0, x1 = max(0, xs.start - pad), min(masks.shape[1], xs.stop + pad)
        patch = masks[y0:y1, x0:x1] == index
        if patch.sum() < MIN_INSTANCE_AREA:
            continue
        patch = binary_closing(patch, footprint)
        patch = ndi.binary_fill_holes(patch)
        patch = remove_small_objects(patch, min_size=MIN_INSTANCE_AREA)
        if not patch.any():
            continue
        # Writing in order means later instances win overlaps from closing.
        region = out[y0:y1, x0:x1]
        region[patch & (region == 0)] = next_id
        next_id += 1
    return out


def cellpose_instances(model, image: np.ndarray, diameter: int) -> np.ndarray:
    scale = NATIVE_DIAMETER_PX / diameter
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
        return {"count": 0, "coverage_pct": 0.0, "diameter_median_px": 0.0}
    areas = np.bincount(masks.ravel())
    areas = areas[1:][areas[1:] > 0]
    diameters = 2 * np.sqrt(areas / np.pi)
    return {
        "count": int(ids.size),
        "coverage_pct": round(100 * float((masks > 0).mean()), 2),
        "diameter_median_px": round(float(np.median(diameters)), 1),
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", type=int, default=10)
    args = parser.parse_args()

    from cellpose import models as cellpose_models
    from sklearn.ensemble import HistGradientBoostingClassifier

    OUT_DIR.mkdir(exist_ok=True)
    names = sorted(p.stem for p in (THESIS / "Labels_ALL").glob("*.txt"))
    test_names, train_names = names[: args.test], names[args.test :]
    rng = np.random.default_rng(RANDOM_STATE)

    print(f"trénink {len(train_names)}, test {len(test_names)}\nUčím…", flush=True)
    start = time.perf_counter()
    xs, ys = [], []
    for name in train_names:
        image, labels = load(name)
        X, y = features(image), labels.ravel()
        pick = rng.choice(y.size, size=min(TRAIN_SAMPLES_PER_IMAGE, y.size), replace=False)
        xs.append(X[pick])
        ys.append(y[pick])
    model = HistGradientBoostingClassifier(max_iter=200, random_state=RANDOM_STATE)
    model.fit(np.concatenate(xs), np.concatenate(ys))
    del xs, ys
    print(f"  hotovo za {time.perf_counter() - start:.0f} s\n", flush=True)

    cellpose = cellpose_models.CellposeModel(gpu=False)
    rows = []

    for i, name in enumerate(test_names, start=1):
        image, labels = load(name)
        h, w = labels.shape

        semantic = model.predict(features(image)).reshape(h, w).astype(np.uint8)
        body = semantic > BACKGROUND

        variants: dict[str, np.ndarray] = {}
        variants["cellpose_d60"] = cellpose_instances(cellpose, image, WRONG_CELL_DIAMETER_PX)
        cp120 = cellpose_instances(cellpose, image, TRUE_CELL_DIAMETER_PX)
        variants["cellpose_d120"] = cp120

        ws = watershed_from(clean_markers(semantic == NUCLEUS, MIN_NUCLEUS_AREA), body)
        variants["watershed"] = ws
        variants["watershed_pp"] = post_process(ws)

        # Fusion: Cellpose decides WHICH cells exist, our model decides HOW FAR
        # each one reaches. Cellpose instances become markers; the mask is our
        # predicted foreground unioned with them, so a cell Cellpose found
        # outside our foreground is not thrown away.
        fusion_markers = clean_markers(cp120 > 0, MIN_NUCLEUS_AREA)
        variants["fusion"] = post_process(
            watershed_from(fusion_markers, np.logical_or(body, cp120 > 0))
        )

        row = {"image": name}
        for label, masks in variants.items():
            row[label] = {
                **instance_stats(masks),
                "foreground_iou_vs_labels": foreground_iou(masks, labels),
            }
        rows.append(row)

        print(f"  [{i:2}/{len(test_names)}] {name}", flush=True)
        for label in variants:
            s = row[label]
            print(
                f"       {label:14} {s['count']:4} instancí  "
                f"medián {s['diameter_median_px']:6.1f} px  "
                f"IoU {s['foreground_iou_vs_labels']:.3f}",
                flush=True,
            )

        if i <= 2:
            for label, masks in variants.items():
                save_preview(image, masks, OUT_DIR / f"{name}_{label}.jpg")

    methods = ["cellpose_d60", "cellpose_d120", "watershed", "watershed_pp", "fusion"]
    summary = {
        m: {
            key: round(float(np.mean([r[m][key] for r in rows])), 3)
            for key in ("count", "coverage_pct", "diameter_median_px", "foreground_iou_vs_labels")
        }
        for m in methods
    }

    print("\n=== souhrn ===", flush=True)
    print(f"{'metoda':16}{'instancí':>10}{'pokrytí':>10}{'medián':>9}{'IoU popředí':>13}", flush=True)
    for m in methods:
        s = summary[m]
        print(
            f"{m:16}{s['count']:10.1f}{s['coverage_pct']:9.1f}%"
            f"{s['diameter_median_px']:9.1f}{s['foreground_iou_vs_labels']:13.3f}",
            flush=True,
        )

    (OUT_DIR / "metrics.json").write_text(
        json.dumps(
            {
                "note": "instance correctness is NOT scored - no instance ground truth exists",
                "true_cell_diameter_px": TRUE_CELL_DIAMETER_PX,
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
