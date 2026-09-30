"""
AerialEye Demo Data Seeder
Generates 5 synthetic demo satellite tiles (temporal variations of a base image)
and ingests them into the AerialEye index so all features are demonstrable
immediately after setup.

Run:
    python scripts/seed_demo_data.py

Label: DEMO — all data is synthetic.
"""
import sys
import os
import json
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

DEMO_DIR = Path("data") / "demo_tiles"
DEMO_DIR.mkdir(parents=True, exist_ok=True)

DEMO_SCENES = [
    {
        "filename": "site01_2022-01-15.jpg",
        "acquisition_time": "2022-01-15T10:00:00Z",
        "sensor": "Sentinel-2 (DEMO)",
        "description": "baseline: sparse settlement with vegetation",
        "params": {"brightness": 0.85, "contrast": 1.0, "add_buildings": 0, "blur": False},
    },
    {
        "filename": "site01_2022-06-20.jpg",
        "acquisition_time": "2022-06-20T10:00:00Z",
        "sensor": "Sentinel-2 (DEMO)",
        "description": "early construction activity detected",
        "params": {"brightness": 0.9, "contrast": 1.05, "add_buildings": 3, "blur": False},
    },
    {
        "filename": "site01_2023-01-10.jpg",
        "acquisition_time": "2023-01-10T10:00:00Z",
        "sensor": "Sentinel-2 (DEMO)",
        "description": "significant construction, vegetation clearance",
        "params": {"brightness": 0.95, "contrast": 1.1, "add_buildings": 8, "blur": False},
    },
    {
        "filename": "site01_2023-08-05.jpg",
        "acquisition_time": "2023-08-05T10:00:00Z",
        "sensor": "Sentinel-2 (DEMO)",
        "description": "cloud cover — reduced quality",
        "params": {"brightness": 1.3, "contrast": 0.8, "add_buildings": 8, "blur": True},
    },
    {
        "filename": "site02_2023-03-22.jpg",
        "acquisition_time": "2023-03-22T10:00:00Z",
        "sensor": "Landsat-8 (DEMO)",
        "description": "similar industrial site — different location",
        "params": {"brightness": 0.75, "contrast": 1.1, "add_buildings": 5, "hue_shift": 15, "blur": False},
    },
]


def generate_base_tile(size: int = 512) -> np.ndarray:
    """Generate a realistic-looking synthetic satellite tile."""
    img = np.zeros((size, size, 3), dtype=np.uint8)

    # Background: pale brown earth
    img[:, :] = [142, 163, 105]  # vegetation-ish green (BGR)

    rng = np.random.default_rng(42)

    # Soil patches
    for _ in range(30):
        x, y = rng.integers(0, size, 2)
        r = rng.integers(15, 60)
        color = [int(c) for c in rng.integers([80, 100, 60], [160, 180, 120])]
        cv2.circle(img, (x, y), r, color, -1)

    # Vegetation clusters (darker green)
    for _ in range(25):
        x, y = rng.integers(0, size, 2)
        r = rng.integers(10, 45)
        g_val = rng.integers(80, 130)
        cv2.circle(img, (x, y), r, [60, int(g_val), 50], -1)

    # Road network (grey lines)
    for _ in range(5):
        x1, y1 = rng.integers(0, size, 2)
        x2, y2 = rng.integers(0, size, 2)
        cv2.line(img, (x1, y1), (x2, y2), [130, 130, 130], rng.integers(2, 5))

    # Water body (blue patch)
    cv2.ellipse(img, (80, 80), (60, 40), 30, 0, 360, [160, 100, 50], -1)

    # Blur for realism
    img = cv2.GaussianBlur(img, (3, 3), 0)
    return img


def apply_params(img: np.ndarray, params: dict) -> np.ndarray:
    """Apply scene-specific transformations."""
    out = img.copy().astype(np.float32)
    size = img.shape[0]
    rng = np.random.default_rng(params.get("add_buildings", 0) + 1)

    # Brightness + contrast
    brightness = params.get("brightness", 1.0)
    contrast = params.get("contrast", 1.0)
    out = out * contrast * brightness
    out = np.clip(out, 0, 255).astype(np.uint8)

    # Add buildings (grey rectangles)
    n_buildings = params.get("add_buildings", 0)
    for _ in range(n_buildings):
        x = rng.integers(100, size - 100)
        y = rng.integers(100, size - 100)
        w = rng.integers(20, 60)
        h = rng.integers(20, 60)
        color = [int(c) for c in rng.integers(140, 200, 3)]
        cv2.rectangle(out, (x, y), (x + w, y + h), color, -1)
        # Shadow
        cv2.rectangle(out, (x + 5, y + h), (x + w + 5, y + h + 8), [60, 60, 60], -1)

    # Hue shift
    if "hue_shift" in params:
        hsv = cv2.cvtColor(out, cv2.COLOR_BGR2HSV).astype(np.int32)
        hsv[:, :, 0] = (hsv[:, :, 0] + params["hue_shift"]) % 180
        out = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

    # Cloud blur
    if params.get("blur"):
        out = cv2.GaussianBlur(out, (21, 21), 10)
        # White haze overlay
        haze = np.ones_like(out) * 220
        out = cv2.addWeighted(out, 0.6, haze, 0.4, 0)

    return out


def seed():
    print("AerialEye Demo Data Seeder")
    print("=" * 40)

    # Check for existing dummy.jpg to use as base
    dummy_path = Path("public") / "dummy.jpg"
    if dummy_path.exists():
        print(f"Using existing base image: {dummy_path}")
        base = cv2.imread(str(dummy_path))
        if base is None:
            base = generate_base_tile()
        else:
            base = cv2.resize(base, (512, 512))
    else:
        print("Generating synthetic base tile…")
        base = generate_base_tile()

    from backend.services.ingestion_service import ingest_file

    ingested = 0
    skipped = 0

    for scene_def in DEMO_SCENES:
        path = DEMO_DIR / scene_def["filename"]

        # Generate tile
        tile = apply_params(base, scene_def["params"])
        cv2.imwrite(str(path), tile)
        print(f"\n>> {scene_def['filename']} ({scene_def['description']})")

        # Ingest
        file_bytes = path.read_bytes()
        result = ingest_file(
            file_bytes=file_bytes,
            filename=scene_def["filename"],
            sensor=scene_def["sensor"],
            acquisition_time=scene_def["acquisition_time"],
            label="DEMO",
            tags=["demo", "synthetic", scene_def["sensor"].split(" ")[0].lower()],
        )

        if result["status"] == "ingested":
            print(f"   [OK] Ingested asset_id={result['asset_id'][:16]}... quality={result.get('quality_score', 0):.2f}")
            ingested += 1
        else:
            print(f"   [SKIP] Already indexed (duplicate)")
            skipped += 1

    print(f"\n{'='*40}")
    print(f"Done: {ingested} ingested, {skipped} skipped")
    print("You can now search for 'construction', 'vegetation', 'settlement' etc.")
    print("Use the Analyze page with site01 assets for temporal change analysis.")


if __name__ == "__main__":
    seed()
