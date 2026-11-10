"""Cellpose baseline on BALF images, CPU only.

Measures how long a pretrained Cellpose model takes on a full 4024x3036 image
and how many objects it finds, for two target diameters: nuclei and whole
cells. Writes an overlay preview per run so the segmentation can be judged by
eye, plus a metrics JSON.

Run:  uv run python run_baseline.py <image> [<image> ...]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

# Diameters measured on sample_1/image_1; see CLAUDE.md.
NUCLEUS_DIAMETER_PX = 69
CELL_DIAMETER_PX = 120

PREVIEW_DOWNSCALE = 4
OUT_DIR = Path(__file__).parent / "outputs"


def load_model():
    """Return (model, eval_kwargs_builder, version) across Cellpose APIs."""
    import cellpose
    from cellpose import models

    version = getattr(cellpose, "version", "unknown")
    major = int(str(version).split(".")[0]) if str(version)[0].isdigit() else 0

    if major >= 4:
        # Cellpose-SAM: single generalist model, no model_type, no channels.
        model = models.CellposeModel(gpu=False)

        def eval_kwargs(diameter):
            return {"diameter": diameter}

    else:
        # Cellpose 3.x and earlier: pick a model and pass channels explicitly.
        model = models.Cellpose(gpu=False, model_type="cyto3")

        def eval_kwargs(diameter):
            # [0, 0] = grayscale; the stain is not a clean two-channel split.
            return {"diameter": diameter, "channels": [0, 0]}

    return model, eval_kwargs, version


def segment(model, eval_kwargs, image: np.ndarray, diameter: int):
    start = time.perf_counter()
    result = model.eval(image, **eval_kwargs(diameter))
    elapsed = time.perf_counter() - start
    masks = result[0]
    return masks, elapsed


def save_overlay(image: np.ndarray, masks: np.ndarray, path: Path) -> None:
    """Downscaled preview with instance boundaries drawn over the image."""
    from skimage.segmentation import find_boundaries

    boundaries = find_boundaries(masks, mode="outer")
    preview = image.copy()
    preview[boundaries] = [255, 0, 0]

    img = Image.fromarray(preview)
    w, h = img.size
    img = img.resize((w // PREVIEW_DOWNSCALE, h // PREVIEW_DOWNSCALE), Image.LANCZOS)
    img.save(path, optimize=True)


def object_stats(masks: np.ndarray) -> dict:
    labels = np.unique(masks)
    labels = labels[labels != 0]
    if labels.size == 0:
        return {"count": 0}
    areas = np.bincount(masks.ravel())[1:]
    areas = areas[areas > 0]
    diameters = 2 * np.sqrt(areas / np.pi)
    return {
        "count": int(labels.size),
        "coverage_pct": round(100 * float((masks > 0).mean()), 2),
        "diameter_median_px": round(float(np.median(diameters)), 1),
        "diameter_p10_px": round(float(np.percentile(diameters, 10)), 1),
        "diameter_p90_px": round(float(np.percentile(diameters, 90)), 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("images", nargs="+", type=Path)
    args = parser.parse_args()

    OUT_DIR.mkdir(exist_ok=True)

    model, eval_kwargs, version = load_model()
    print(f"cellpose {version}, CPU", flush=True)

    runs = []
    for image_path in args.images:
        image = np.array(Image.open(image_path).convert("RGB"))
        sample = image_path.parent.name
        print(f"\n{sample}/{image_path.name}  {image.shape[1]}x{image.shape[0]}", flush=True)

        for target, diameter in (("nuclei", NUCLEUS_DIAMETER_PX), ("cells", CELL_DIAMETER_PX)):
            masks, elapsed = segment(model, eval_kwargs, image, diameter)
            stats = object_stats(masks)

            preview = OUT_DIR / f"{sample}_{target}.png"
            save_overlay(image, masks, preview)

            run = {
                "sample": sample,
                "image": image_path.name,
                "target": target,
                "diameter_px": diameter,
                "seconds": round(elapsed, 1),
                "preview": preview.name,
                **stats,
            }
            runs.append(run)
            print(
                f"  {target:6} d={diameter:3}  {elapsed:6.1f}s  "
                f"{stats['count']:5} objektů  medián {stats.get('diameter_median_px')} px",
                flush=True,
            )

    metrics = OUT_DIR / "metrics.json"
    metrics.write_text(
        json.dumps({"cellpose_version": str(version), "device": "cpu", "runs": runs}, indent=2),
        encoding="utf-8",
    )
    print(f"\n-> {metrics}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
