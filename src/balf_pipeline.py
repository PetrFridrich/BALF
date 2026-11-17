"""Phase 1 of the BALF pipeline: cells as instance masks.

This is the approach that came out of research/, in particular
research/2026-11-14-cellpose-rematch/, where it is called "fusion":

    Cellpose decides WHICH cells exist - it is conservative and skips debris
    and broken cells, which a differential count must exclude anyway.

    A supervised model decides HOW FAR each cell reaches - Cellpose hugs
    nuclei and dense cores and leaves pale cytoplasm outside.

Watershed joins them: Cellpose instances are the markers, the supervised
foreground is the mask. Its median cell diameter landed at 128.9px against the
~120px measured from nuclei, closest of every variant tried, and nothing in the
pipeline was fitted to that number.

Scale matters. Cells are ~120px across in the project images AND in the
labelled thesis crops, which are crops at the original scale rather than
downscales. Feeding a segmentation model half that figure causes over-splitting.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

Image.MAX_IMAGE_PIXELS = None

BACKGROUND, CYTOPLASM, NUCLEUS = 0, 1, 2
SIGMAS = (1, 2, 4, 8)

CELL_DIAMETER_PX = 120
NATIVE_DIAMETER_PX = 30

MIN_MARKER_AREA = 50
MIN_INSTANCE_AREA = 400
SMOOTH_RADIUS = 3

TRAIN_SAMPLES_PER_IMAGE = 30_000
RANDOM_STATE = 42

THESIS_DATA = Path("/home/user/fido18246/ing_thesis/Data")


# --------------------------------------------------------------------------
# features
# --------------------------------------------------------------------------

def features(image: np.ndarray) -> np.ndarray:
    """27 per-pixel features: colour, optical density, multiscale texture.

    Optical density is included because May-Grunwald-Giemsa is a two-dye
    stain, so it separates nucleus from cytoplasm on physical grounds where
    raw RGB does not.
    """
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


# --------------------------------------------------------------------------
# semantic model
# --------------------------------------------------------------------------

def train_semantic_model(limit: int | None = None, verbose: bool = True):
    """Train the background/cytoplasm/nucleus classifier on the thesis labels.

    Sampling is uniform, NOT balanced per class. The real balance is about
    88/7/5 and training on 33/33/33 cost 0.05 Jaccard in
    research/2026-11-13-supervised-nuclei/.
    """
    from sklearn.ensemble import HistGradientBoostingClassifier

    names = sorted(p.stem for p in (THESIS_DATA / "Labels_ALL").glob("*.txt"))
    if limit:
        names = names[:limit]
    if not names:
        raise FileNotFoundError(
            f"No labelled images under {THESIS_DATA}. Clone "
            "https://github.com/Fido18246/ing_thesis first."
        )

    rng = np.random.default_rng(RANDOM_STATE)
    xs, ys = [], []
    for i, name in enumerate(names, start=1):
        image = np.array(Image.open(THESIS_DATA / "Images_ALL" / f"{name}.png").convert("RGB"))
        labels = np.loadtxt(THESIS_DATA / "Labels_ALL" / f"{name}.txt", dtype=np.uint8).ravel()
        X = features(image)
        pick = rng.choice(labels.size, size=min(TRAIN_SAMPLES_PER_IMAGE, labels.size), replace=False)
        xs.append(X[pick])
        ys.append(labels[pick])
        if verbose and i % 10 == 0:
            print(f"  features {i}/{len(names)}", flush=True)

    model = HistGradientBoostingClassifier(max_iter=200, random_state=RANDOM_STATE)
    model.fit(np.concatenate(xs), np.concatenate(ys))
    return model


def load_or_train(cache: Path, limit: int | None = None, verbose: bool = True):
    """Train once, reuse afterwards. Training costs about two minutes."""
    import joblib

    if cache.exists():
        if verbose:
            print(f"model z cache: {cache}", flush=True)
        return joblib.load(cache)

    if verbose:
        print("model v cache není, učím (~2 min)…", flush=True)
    model = train_semantic_model(limit=limit, verbose=verbose)
    cache.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, cache, compress=3)
    if verbose:
        print(f"uloženo: {cache}", flush=True)
    return model


def predict_semantic(model, image: np.ndarray) -> np.ndarray:
    h, w = image.shape[:2]
    return model.predict(features(image)).reshape(h, w).astype(np.uint8)


# --------------------------------------------------------------------------
# instances
# --------------------------------------------------------------------------

def cellpose_instances(model, image: np.ndarray, diameter: int = CELL_DIAMETER_PX) -> np.ndarray:
    """Cellpose at the right scale, prescaled for speed (11.6x, IoU 0.97)."""
    scale = NATIVE_DIAMETER_PX / diameter
    h, w = image.shape[:2]
    small = np.array(
        Image.fromarray(image).resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    )
    masks = model.eval(small, diameter=NATIVE_DIAMETER_PX)[0]
    return np.array(
        Image.fromarray(masks.astype(np.int32), mode="I").resize((w, h), Image.NEAREST)
    )


def drop_small_labels(labelled: np.ndarray, min_area: int) -> np.ndarray:
    """Remove small labels WITHOUT relabelling.

    Binarising a label map and relabelling it merges instances that touch,
    which silently collapsed the fusion markers once already.
    """
    out = labelled.copy()
    areas = np.bincount(out.ravel())
    small = np.flatnonzero(areas < min_area)
    out[np.isin(out, small[small > 0])] = 0
    return out


def post_process(masks: np.ndarray) -> np.ndarray:
    """Smooth ragged borders, fill holes, drop specks - per instance."""
    from skimage.morphology import binary_closing, disk, remove_small_objects

    out = np.zeros_like(masks)
    footprint = disk(SMOOTH_RADIUS)
    next_id = 1
    for index, window in enumerate(ndi.find_objects(masks), start=1):
        if window is None:
            continue
        pad = SMOOTH_RADIUS + 2
        ys, xs = window
        y0, y1 = max(0, ys.start - pad), min(masks.shape[0], ys.stop + pad)
        x0, x1 = max(0, xs.start - pad), min(masks.shape[1], xs.stop + pad)
        patch = masks[y0:y1, x0:x1] == index
        if patch.sum() < MIN_INSTANCE_AREA:
            continue
        patch = ndi.binary_fill_holes(binary_closing(patch, footprint))
        patch = remove_small_objects(patch, min_size=MIN_INSTANCE_AREA)
        if not patch.any():
            continue
        region = out[y0:y1, x0:x1]
        region[patch & (region == 0)] = next_id
        next_id += 1
    return out


def fuse(cellpose_masks: np.ndarray, semantic: np.ndarray) -> np.ndarray:
    """Cellpose says which cells exist; the semantic map says how far they reach."""
    from skimage.segmentation import watershed

    markers = drop_small_labels(cellpose_masks, MIN_MARKER_AREA)
    # Union, so a cell Cellpose found outside our foreground is not discarded.
    body = np.logical_or(semantic > BACKGROUND, cellpose_masks > 0)
    distance = ndi.distance_transform_edt(body)
    return post_process(watershed(-distance, markers, mask=body))


def segment(image: np.ndarray, semantic_model, cellpose_model) -> dict:
    """Full phase 1 on one image. Returns masks and the intermediates."""
    semantic = predict_semantic(semantic_model, image)
    cellpose_masks = cellpose_instances(cellpose_model, image)
    return {
        "semantic": semantic,
        "cellpose": cellpose_masks,
        "masks": fuse(cellpose_masks, semantic),
    }


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------

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


def save_overlay(image: np.ndarray, masks: np.ndarray, path: Path, max_width: int = 1400) -> None:
    """Boundaries are drawn AFTER downscaling; a 1px outline drawn at full size
    all but vanishes when the image is then shrunk, making good masks look
    full of holes."""
    from skimage.segmentation import find_boundaries

    h, w = image.shape[:2]
    scale = min(1.0, max_width / w)
    size = (int(w * scale), int(h * scale))
    small = np.array(Image.fromarray(image).resize(size, Image.LANCZOS))
    small_masks = np.array(
        Image.fromarray(masks.astype(np.int32), mode="I").resize(size, Image.NEAREST)
    )
    small[find_boundaries(small_masks, mode="outer")] = [255, 0, 0]
    Image.fromarray(small).save(path, quality=88, optimize=True)
