"""
Tile -> RGB model input preparation.

Stretch (documented, fixed):
  1. Select RGB bands (Sentinel-2: B04/B03/B02; Landsat: 4/3/2; else first 3 or RGB as-is).
  2. Divide by reflectance_scale (default 10000 for S2 L2A-style uint16).
  3. Clip to [0, reflectance_clip] (default 0.3).
  4. Apply gamma (default 1.0 / 0.8 ≈ brighten midtones).
  5. Resize to model input size (default 224).
  6. Mask nodata pixels to black (0).

Legacy (georeferenced=False / source_type=LEGACY): use preview JPG/PNG directly.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger("aerialeye.tile_image")

DEFAULT_INPUT_SIZE = 224
REFLECTANCE_SCALE = 10000.0
REFLECTANCE_CLIP = 0.3
GAMMA = 0.8  # output = (x)^gamma after normalize to 0-1 stretch domain


def _find_band_indices(band_names: Optional[list], sensor: str) -> Tuple[int, int, int]:
    """Return 0-based indices for R,G,B within a chip array."""
    names = [str(b).upper() if b else "" for b in (band_names or [])]
    sensor_l = (sensor or "").lower()

    def idx_of(*cands):
        for c in cands:
            for i, n in enumerate(names):
                if c in n or n == c:
                    return i
        return None

    if "sentinel" in sensor_l or any("B0" in n for n in names):
        r = idx_of("B04", "B4", "RED")
        g = idx_of("B03", "B3", "GREEN")
        b = idx_of("B02", "B2", "BLUE")
        if None not in (r, g, b):
            return int(r), int(g), int(b)

    if "landsat" in sensor_l:
        r = idx_of("B4", "B04", "RED", "SR_B4")
        g = idx_of("B3", "B03", "GREEN", "SR_B3")
        b = idx_of("B2", "B02", "BLUE", "SR_B2")
        if None not in (r, g, b):
            return int(r), int(g), int(b)

    # Generic: first 3 bands
    return 0, 1, 2


def apply_reflectance_stretch(
    rgb: np.ndarray,
    scale: float = REFLECTANCE_SCALE,
    clip: float = REFLECTANCE_CLIP,
    gamma: float = GAMMA,
) -> np.ndarray:
    """
    rgb: float or int array HxWx3 or 3xHxW.
    Returns uint8 HxWx3.
    """
    arr = np.asarray(rgb, dtype=np.float32)
    if arr.ndim == 3 and arr.shape[0] in (1, 3, 4) and arr.shape[-1] not in (1, 3, 4):
        arr = np.transpose(arr, (1, 2, 0))
    if arr.shape[-1] > 3:
        arr = arr[..., :3]
    if arr.shape[-1] == 1:
        arr = np.repeat(arr, 3, axis=-1)

    # If already 0-255-ish uint range stored as float
    mx = float(np.nanmax(arr)) if arr.size else 0.0
    if mx <= 1.5:
        # Already reflectance-like 0-1
        refl = arr
    elif mx <= 255.0:
        # Display RGB — mild stretch only
        refl = arr / 255.0
        out = np.clip(refl, 0, 1)
        if gamma and gamma != 1.0:
            out = np.power(out, gamma)
        return (out * 255.0).astype(np.uint8)
    else:
        refl = arr / float(scale)

    out = np.clip(refl, 0.0, clip) / max(clip, 1e-6)
    if gamma and gamma != 1.0:
        out = np.power(out, gamma)
    return (out * 255.0).astype(np.uint8)


def load_tile_rgb(
    tile: Dict[str, Any],
    input_size: int = DEFAULT_INPUT_SIZE,
    reflectance_scale: float = REFLECTANCE_SCALE,
    reflectance_clip: float = REFLECTANCE_CLIP,
    gamma: float = GAMMA,
) -> Optional[np.ndarray]:
    """
    Build model-ready RGB uint8 HxWx3 from a tile row.
    Returns None if the chip/preview cannot be loaded.
    """
    georeferenced = bool(tile.get("georeferenced", True))
    source_type = (tile.get("source_type") or "").upper()
    use_preview = (not georeferenced) or source_type == "LEGACY" or source_type == "DEMO"

    preview_path = tile.get("preview_path") or ""
    chip_path = tile.get("chip_path") or ""

    rgb: Optional[np.ndarray] = None

    if use_preview and preview_path and Path(preview_path).exists():
        img = cv2.imread(preview_path, cv2.IMREAD_COLOR)
        if img is not None:
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    elif chip_path and Path(chip_path).exists():
        chip = np.load(chip_path)
        # chip may be CHW multi-band or HWC RGB
        if chip.ndim == 3 and chip.shape[-1] in (3, 4) and chip.shape[0] > 4:
            # HWC
            rgb = apply_reflectance_stretch(
                chip[..., :3], scale=reflectance_scale, clip=reflectance_clip, gamma=gamma
            )
        else:
            band_names = []
            try:
                import json

                band_names = json.loads(tile.get("band_names_json") or "[]")
            except Exception:
                band_names = []
            r, g, b = _find_band_indices(band_names, tile.get("sensor", ""))
            if chip.ndim == 2:
                stacked = np.stack([chip, chip, chip], axis=0)
            else:
                # CHW
                bands = chip.shape[0]
                ri = min(r, bands - 1)
                gi = min(g, bands - 1)
                bi = min(b, bands - 1)
                stacked = np.stack([chip[ri], chip[gi], chip[bi]], axis=0)
            rgb = apply_reflectance_stretch(
                stacked, scale=reflectance_scale, clip=reflectance_clip, gamma=gamma
            )
    elif preview_path and Path(preview_path).exists():
        img = cv2.imread(preview_path, cv2.IMREAD_COLOR)
        if img is not None:
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    if rgb is None:
        logger.warning("Could not load RGB for tile_id=%s", tile.get("tile_id"))
        return None

    # Mask nodata if mask_path present
    mask_path = tile.get("mask_path") or ""
    if mask_path and Path(mask_path).exists():
        try:
            mask = np.load(mask_path)
            if mask.shape[:2] == rgb.shape[:2]:
                # mask: 0=valid; anything else or nodata → black
                invalid = mask != 0
                rgb = rgb.copy()
                rgb[invalid] = 0
        except Exception as exc:
            logger.debug("Mask apply failed for tile %s: %s", tile.get("tile_id"), exc)

    if input_size and (rgb.shape[0] != input_size or rgb.shape[1] != input_size):
        rgb = cv2.resize(rgb, (input_size, input_size), interpolation=cv2.INTER_AREA)

    return rgb.astype(np.uint8)


def load_image_file_rgb(path: str, input_size: int = DEFAULT_INPUT_SIZE) -> Optional[np.ndarray]:
    """Load an arbitrary uploaded image as model RGB."""
    p = Path(path)
    if not p.exists():
        return None
    if p.suffix.lower() == ".npy":
        arr = np.load(str(p))
        if arr.ndim == 3 and arr.shape[0] in (1, 3, 4):
            arr = np.transpose(arr, (1, 2, 0))
        rgb = apply_reflectance_stretch(arr[..., :3] if arr.shape[-1] >= 3 else arr)
    else:
        img = cv2.imread(str(p), cv2.IMREAD_COLOR)
        if img is None:
            return None
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    if input_size:
        rgb = cv2.resize(rgb, (input_size, input_size), interpolation=cv2.INTER_AREA)
    return rgb.astype(np.uint8)
