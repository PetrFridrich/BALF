"""Can an unsupervised nucleus map help instance segmentation of BALF cells?

Uses the 50 pixel-labelled images from the author's master's thesis
(background / cytoplasm / nucleus at 2012x1518) as ground truth, which the
BALF project itself does not have.

Three questions:

1. How well does unsupervised clustering recover nuclei and cytoplasm?
   This decides whether a synthetic nucleus channel is worth feeding to a
   segmentation model.
2. Does marker-controlled watershed, seeded from nuclei, split touching cells
   that Cellpose merges?
3. How often does one connected cytoplasm region hold several nuclei, and is
   that genuine multinucleation or merely cells in contact? Watershed splits
   both, and splitting a truly multinucleated cell is wrong.

Run:  uv run python run.py [--limit N]
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
MIN_NUCLEUS_AREA = 50
PREVIEW_MAX_WIDTH = 1400


def load_pair(name: str) -> tuple[np.ndarray, np.ndarray]:
    image = np.array(Image.open(THESIS / "Images_ALL" / f"{name}.png").convert("RGB"))
    labels = np.loadtxt(THESIS / "Labels_ALL" / f"{name}.txt", dtype=np.uint8)
    return image, labels


def cluster_three_ways(image: np.ndarray) -> np.ndarray:
    """Unsupervised 3-class map, relabelled so 0=background, 1=cytoplasm, 2=nucleus.

    The relabelling follows the thesis approach: order clusters by mean
    intensity, brightest first. Background is the brightest, nuclei the darkest.
    """
    from sklearn.cluster import MiniBatchKMeans

    flat = image.reshape(-1, 3).astype(np.float32)
    model = MiniBatchKMeans(n_clusters=3, n_init=5, random_state=0)
    assigned = model.fit_predict(flat)

    brightness = [flat[assigned == k].mean() for k in range(3)]
    order = np.argsort(brightness)[::-1]  # brightest cluster first
    remap = np.zeros(3, dtype=np.uint8)
    for rank, cluster in enumerate(order):
        remap[cluster] = rank

    return remap[assigned].reshape(image.shape[:2])


def iou(a: np.ndarray, b: np.ndarray) -> float:
    union = np.logical_or(a, b).sum()
    return round(float(np.logical_and(a, b).sum() / union), 3) if union else 0.0


def nuclei_per_region(labels: np.ndarray) -> dict[int, int]:
    """How many labelled nuclei sit inside each connected cytoplasm region."""
    bodies, _ = ndi.label(labels > BACKGROUND)
    nuclei, count = ndi.label(labels == NUCLEUS)
    if count == 0:
        return {}
    areas = ndi.sum(np.ones_like(nuclei), nuclei, range(1, count + 1))
    centres = ndi.center_of_mass(labels == NUCLEUS, nuclei, range(1, count + 1))

    per_region: dict[int, int] = {}
    for (y, x), area in zip(centres, areas):
        if area < MIN_NUCLEUS_AREA:
            continue
        region = bodies[int(y), int(x)]
        if region:
            per_region[region] = per_region.get(region, 0) + 1
    return per_region


def watershed_from_nuclei(labels: np.ndarray) -> np.ndarray:
    """Split cell bodies using labelled nuclei as markers."""
    from skimage.segmentation import watershed

    body = labels > BACKGROUND
    markers, _ = ndi.label(labels == NUCLEUS)
    # Distance transform gives the ridge watershed floods away from.
    distance = ndi.distance_transform_edt(body)
    return watershed(-distance, markers, mask=body)


def instance_stats(masks: np.ndarray) -> dict:
    ids = np.unique(masks)
    ids = ids[ids != 0]
    if ids.size == 0:
        return {"count": 0}
    areas = np.bincount(masks.ravel())
    areas = areas[1:][areas[1:] > 0]
    diameters = 2 * np.sqrt(areas / np.pi)
    return {
        "count": int(ids.size),
        "diameter_median_px": round(float(np.median(diameters)), 1),
        "diameter_p10_px": round(float(np.percentile(diameters, 10)), 1),
        "diameter_p90_px": round(float(np.percentile(diameters, 90)), 1),
    }


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
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    OUT_DIR.mkdir(exist_ok=True)
    names = sorted(p.stem for p in (THESIS / "Labels_ALL").glob("*.txt"))[: args.limit]
    print(f"{len(names)} snímků s anotací\n", flush=True)

    per_image = []
    multinucleation: dict[int, int] = {}

    for i, name in enumerate(names):
        image, labels = load_pair(name)

        start = time.perf_counter()
        clustered = cluster_three_ways(image)
        cluster_seconds = time.perf_counter() - start

        row = {
            "image": name,
            "cluster_seconds": round(cluster_seconds, 1),
            "iou_nucleus": iou(clustered == NUCLEUS, labels == NUCLEUS),
            "iou_cytoplasm": iou(clustered == CYTOPLASM, labels == CYTOPLASM),
            "iou_foreground": iou(clustered > BACKGROUND, labels > BACKGROUND),
        }

        counts = nuclei_per_region(labels)
        for n in counts.values():
            multinucleation[n] = multinucleation.get(n, 0) + 1

        masks = watershed_from_nuclei(labels)
        row["watershed"] = instance_stats(masks)
        row["cytoplasm_regions"] = len(counts)

        per_image.append(row)
        print(
            f"  [{i + 1:2}/{len(names)}] {name}  "
            f"IoU jádra {row['iou_nucleus']:.3f}  cytoplazma {row['iou_cytoplasm']:.3f}  "
            f"popředí {row['iou_foreground']:.3f}  "
            f"watershed {row['watershed']['count']:4} instancí "
            f"z {row['cytoplasm_regions']:4} oblastí",
            flush=True,
        )

        if i < 3:
            save_preview(image, masks, OUT_DIR / f"{name}_watershed.jpg")

    def mean(key: str) -> float:
        return round(float(np.mean([r[key] for r in per_image])), 3)

    total_regions = sum(multinucleation.values())
    multi_pct = (
        round(100 * sum(v for k, v in multinucleation.items() if k > 1) / total_regions, 1)
        if total_regions
        else 0.0
    )

    summary = {
        "images": len(names),
        "mean_iou_nucleus": mean("iou_nucleus"),
        "mean_iou_cytoplasm": mean("iou_cytoplasm"),
        "mean_iou_foreground": mean("iou_foreground"),
        "cytoplasm_regions_total": total_regions,
        "regions_with_multiple_nuclei_pct": multi_pct,
        "nuclei_per_region_histogram": {str(k): v for k, v in sorted(multinucleation.items())},
    }

    print("\n=== souhrn ===", flush=True)
    print(f"  IoU jádra (průměr):     {summary['mean_iou_nucleus']}", flush=True)
    print(f"  IoU cytoplazma:         {summary['mean_iou_cytoplasm']}", flush=True)
    print(f"  IoU popředí:            {summary['mean_iou_foreground']}", flush=True)
    print(f"  oblastí cytoplazmy:     {total_regions}", flush=True)
    print(f"  z toho s >1 jádrem:     {multi_pct} %", flush=True)

    (OUT_DIR / "metrics.json").write_text(
        json.dumps({"summary": summary, "per_image": per_image}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\n-> {OUT_DIR / 'metrics.json'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
