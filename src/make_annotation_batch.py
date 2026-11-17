"""Build a batch of mask proposals to correct in the Cellpose GUI.

Phase 1 produces proposals; the human corrects them; the corrections become
the instance ground truth the project has never had, and the material for
fine-tuning Cellpose on this domain.

Images are cut into quadrants. A full frame is 4024x3036 and unwieldy to edit;
a quadrant is 2012x1518 with cells still ~120px across, the same framing the
earlier thesis annotations used.

Each quadrant yields three files:

    <name>.png          the crop, opened in the GUI
    <name>_seg.npy      the proposed masks, loaded automatically beside it
    <name>_overlay.jpg  a preview, for a quick look without the GUI

Run:  uv run python make_annotation_batch.py --samples sample_1_2122_23 --images 1 2
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from balf_pipeline import (  # noqa: E402
    CELL_DIAMETER_PX,
    instance_stats,
    load_or_train,
    save_overlay,
    segment,
)

Image.MAX_IMAGE_PIXELS = None

HF_DATASET = "Fido18246/BALF"
DEFAULT_OUT = Path(__file__).parent.parent / "annotation_batches"
MODEL_CACHE = Path(__file__).parent.parent / "models" / "semantic_hgb.joblib"

QUADRANTS = {"tl": (0, 0), "tr": (1, 0), "bl": (0, 1), "br": (1, 1)}


def fetch(sample: str, index: int, cache_dir: Path) -> Path:
    from huggingface_hub import hf_hub_download

    return Path(
        hf_hub_download(
            HF_DATASET,
            f"{sample}/2023_12_14_image_{index}.png",
            repo_type="dataset",
            local_dir=cache_dir,
        )
    )


def quadrants(image: np.ndarray, which: list[str]) -> dict[str, np.ndarray]:
    h, w = image.shape[:2]
    half_h, half_w = h // 2, w // 2
    out = {}
    for key in which:
        cx, cy = QUADRANTS[key]
        out[key] = image[cy * half_h : (cy + 1) * half_h, cx * half_w : (cx + 1) * half_w]
    return out


def write_seg(image: np.ndarray, masks: np.ndarray, stem: Path) -> None:
    """Write the GUI's <name>_seg.npy beside the image.

    Field layout copied from what cellpose.io.masks_flows_to_seg produces, so
    the GUI opens it as if Cellpose had just run.

    Flows carry no masks and would cost ~37MB per crop, so they are written as
    the empty structure the GUI itself falls back to (gui/io.py sets exactly
    this when flows cannot be read). Mask editing does not use them.
    """
    from skimage.segmentation import find_boundaries

    outlines = np.zeros_like(masks)
    boundaries = find_boundaries(masks, mode="inner")
    outlines[boundaries] = masks[boundaries]

    payload = {
        "outlines": outlines.astype(np.uint16),
        "masks": masks.astype(np.uint16),
        "chan_choose": [0, 0],
        "ismanual": np.zeros(int(masks.max()), dtype=bool),
        "filename": str(stem.with_suffix(".png")),
        "flows": [[], [], [], [], [[]]],
        "diameter": float(CELL_DIAMETER_PX),
    }
    np.save(stem.parent / f"{stem.name}_seg.npy", payload, allow_pickle=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", nargs="+", default=["sample_1_2122_23"])
    parser.add_argument("--images", nargs="+", type=int, default=[1])
    parser.add_argument("--quadrants", nargs="+", default=["tl"], choices=list(QUADRANTS))
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--cache", type=Path, default=Path("/tmp/balf_hf_cache"))
    args = parser.parse_args()

    from cellpose import models as cellpose_models

    out_dir = args.out / time.strftime("%Y-%m-%d")
    out_dir.mkdir(parents=True, exist_ok=True)

    semantic_model = load_or_train(MODEL_CACHE)
    cellpose_model = cellpose_models.CellposeModel(gpu=False)

    manifest = []
    for sample in args.samples:
        for index in args.images:
            source = fetch(sample, index, args.cache)
            full = np.array(Image.open(source).convert("RGB"))
            print(f"\n{sample}/image_{index}  {full.shape[1]}x{full.shape[0]}", flush=True)

            for key, crop in quadrants(full, args.quadrants).items():
                name = f"{sample}_image{index}_{key}"
                stem = out_dir / name

                start = time.perf_counter()
                result = segment(crop, semantic_model, cellpose_model)
                elapsed = time.perf_counter() - start

                Image.fromarray(crop).save(stem.with_suffix(".png"))
                write_seg(crop, result["masks"], stem)
                save_overlay(crop, result["masks"], out_dir / f"{name}_overlay.jpg")

                stats = instance_stats(result["masks"])
                manifest.append({"name": name, "sample": sample, "image": index,
                                 "quadrant": key, "seconds": round(elapsed, 1), **stats})
                print(
                    f"  {key}  {stats['count']:4} buněk  "
                    f"medián {stats['diameter_median_px']:6.1f} px  "
                    f"pokrytí {stats['coverage_pct']:5.1f}%  ({elapsed:.0f} s)",
                    flush=True,
                )

    (out_dir / "manifest.json").write_text(
        json.dumps({"dataset": HF_DATASET, "crops": manifest}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    total = sum(c["count"] for c in manifest)
    print(f"\n{len(manifest)} výřezů, {total} navržených buněk -> {out_dir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
