"""Cellpose baseline on BALF images, CPU only.

Two questions:

1. How long does a pretrained Cellpose model take on a full 4024x3036 image,
   and is the result usable?
2. Cellpose internally rescales an image so that objects are ~30px across.
   Does downscaling the image first and asking for diameter=30 give the same
   masks for a fraction of the cost?

Each run writes an overlay preview so segmentation quality can be judged by
eye, plus a metrics JSON.

Run:  uv run python run_baseline.py <image> [<image> ...]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

# Diameters measured on sample_1/image_1; see CLAUDE.md.
NUCLEUS_DIAMETER_PX = 69
CELL_DIAMETER_PX = 120

# What Cellpose rescales to internally.
NATIVE_DIAMETER_PX = 30

PREVIEW_MAX_WIDTH = 1200
OUT_DIR = Path(__file__).parent / "outputs"


@dataclass
class Strategy:
    """One way of presenting the image to the model."""

    name: str
    target: str  # what we are trying to segment
    diameter: int  # diameter passed to Cellpose
    prescale: float  # factor applied to the image before inference

    @property
    def label(self) -> str:
        return f"{self.name}"


STRATEGIES = [
    Strategy("cells_full", "cells", CELL_DIAMETER_PX, 1.0),
    Strategy(
        "cells_prescaled",
        "cells",
        NATIVE_DIAMETER_PX,
        NATIVE_DIAMETER_PX / CELL_DIAMETER_PX,
    ),
    Strategy("nuclei_full", "nuclei", NUCLEUS_DIAMETER_PX, 1.0),
    Strategy(
        "nuclei_prescaled",
        "nuclei",
        NATIVE_DIAMETER_PX,
        NATIVE_DIAMETER_PX / NUCLEUS_DIAMETER_PX,
    ),
]


def load_model():
    from cellpose import models

    import cellpose

    return models.CellposeModel(gpu=False), getattr(cellpose, "version", "unknown")


def resize_image(image: np.ndarray, factor: float) -> np.ndarray:
    if factor == 1.0:
        return image
    h, w = image.shape[:2]
    size = (max(1, int(round(w * factor))), max(1, int(round(h * factor))))
    return np.array(Image.fromarray(image).resize(size, Image.LANCZOS))


def upscale_masks(masks: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    """Nearest-neighbour back to full resolution so runs stay comparable."""
    if masks.shape == shape:
        return masks
    resized = Image.fromarray(masks.astype(np.int32), mode="I").resize(
        (shape[1], shape[0]), Image.NEAREST
    )
    return np.array(resized)


def save_overlay(image: np.ndarray, masks: np.ndarray, path: Path) -> None:
    from skimage.segmentation import find_boundaries

    preview = image.copy()
    preview[find_boundaries(masks, mode="outer")] = [255, 0, 0]

    img = Image.fromarray(preview)
    w, h = img.size
    if w > PREVIEW_MAX_WIDTH:
        scale = PREVIEW_MAX_WIDTH / w
        img = img.resize((PREVIEW_MAX_WIDTH, int(h * scale)), Image.LANCZOS)
    img.save(path, optimize=True)


def object_stats(masks: np.ndarray) -> dict:
    labels = np.unique(masks)
    labels = labels[labels != 0]
    if labels.size == 0:
        return {"count": 0, "coverage_pct": 0.0}
    areas = np.bincount(masks.ravel())
    areas = areas[1:][areas[1:] > 0]
    diameters = 2 * np.sqrt(areas / np.pi)
    return {
        "count": int(labels.size),
        "coverage_pct": round(100 * float((masks > 0).mean()), 2),
        "diameter_median_px": round(float(np.median(diameters)), 1),
        "diameter_p10_px": round(float(np.percentile(diameters, 10)), 1),
        "diameter_p90_px": round(float(np.percentile(diameters, 90)), 1),
    }


def agreement(a: np.ndarray, b: np.ndarray) -> float:
    """Foreground IoU between two label maps — cheap proxy for 'same result'."""
    fa, fb = a > 0, b > 0
    union = np.logical_or(fa, fb).sum()
    if union == 0:
        return 0.0
    return round(float(np.logical_and(fa, fb).sum() / union), 3)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument("--strategies", nargs="*", default=None)
    args = parser.parse_args()

    OUT_DIR.mkdir(exist_ok=True)
    strategies = [s for s in STRATEGIES if not args.strategies or s.name in args.strategies]

    model, version = load_model()
    print(f"cellpose {version}, CPU", flush=True)

    runs = []
    for image_path in args.images:
        image = np.array(Image.open(image_path).convert("RGB"))
        sample = image_path.parent.name
        h, w = image.shape[:2]
        print(f"\n{sample}/{image_path.name}  {w}x{h}", flush=True)

        masks_by_target: dict[str, dict[str, np.ndarray]] = {}

        for strategy in strategies:
            prepared = resize_image(image, strategy.prescale)

            start = time.perf_counter()
            masks = model.eval(prepared, diameter=strategy.diameter)[0]
            elapsed = time.perf_counter() - start

            masks = upscale_masks(masks, (h, w))
            stats = object_stats(masks)

            preview = OUT_DIR / f"{sample}_{strategy.name}.png"
            save_overlay(image, masks, preview)

            masks_by_target.setdefault(strategy.target, {})[strategy.name] = masks

            run = {
                "sample": sample,
                "image": image_path.name,
                "strategy": strategy.name,
                "target": strategy.target,
                "diameter_px": strategy.diameter,
                "prescale": round(strategy.prescale, 3),
                "inference_px": f"{prepared.shape[1]}x{prepared.shape[0]}",
                "seconds": round(elapsed, 1),
                "preview": preview.name,
                **stats,
            }
            runs.append(run)
            print(
                f"  {strategy.name:18} {run['inference_px']:>10}  {elapsed:7.1f}s  "
                f"{stats['count']:5} objektů  medián {stats.get('diameter_median_px')} px",
                flush=True,
            )

        # Does prescaling change the answer?
        for target, by_name in masks_by_target.items():
            full = by_name.get(f"{target}_full")
            pre = by_name.get(f"{target}_prescaled")
            if full is not None and pre is not None:
                iou = agreement(full, pre)
                print(f"  -> {target}: shoda popředí full vs prescaled IoU = {iou}", flush=True)
                runs.append(
                    {
                        "sample": sample,
                        "image": image_path.name,
                        "comparison": f"{target}_full_vs_prescaled",
                        "foreground_iou": iou,
                    }
                )

    metrics = OUT_DIR / "metrics.json"
    metrics.write_text(
        json.dumps(
            {
                "cellpose_version": str(version),
                "device": "cpu",
                "strategies": [asdict(s) for s in strategies],
                "runs": runs,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\n-> {metrics}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
