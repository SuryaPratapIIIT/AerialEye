"""
AerialEye Ingestion Service
Accepts image/GeoTIFF files, extracts metadata, generates embeddings,
and registers into the SQLite + FAISS index.

Idempotent: SHA256 checksum deduplication prevents double-ingestion.
"""
import base64
import hashlib
import io
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ExifTags

from backend.db import get_db, insert_scene, insert_embedding, scene_exists
from backend.services.embedding_service import embed_image, add_to_index

logger = logging.getLogger("aerialeye.ingestion")

ASSET_STORE = Path(__file__).parent.parent.parent / "data" / "assets"
ASSET_STORE.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ingest_file(
    file_bytes: bytes,
    filename: str,
    sensor: str = "unknown",
    acquisition_time: Optional[str] = None,
    label: str = "REAL",
    tags: Optional[List[str]] = None,
    bbox: Optional[List[float]] = None,
    crs: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Ingest a single image file into the AerialEye index.
    Returns a status dict.
    """
    asset_id = _sha256(file_bytes)
    db = get_db()

    # --- Deduplication ---
    existing = _scene_exists_fast(db, asset_id)
    if existing:
        logger.info("Scene %s already indexed (dedup). Skipping.", asset_id)
        return {
            "status": "skipped",
            "asset_id": asset_id,
            "reason": "Already ingested (checksum match)",
        }

    # --- Save file to asset store ---
    suffix = Path(filename).suffix.lower() or ".jpg"
    stored_path = ASSET_STORE / f"{asset_id}{suffix}"
    stored_path.write_bytes(file_bytes)

    # --- Extract metadata ---
    meta = _extract_metadata(stored_path, file_bytes, filename, sensor, acquisition_time, bbox, crs)
    meta["asset_id"] = asset_id
    meta["label"] = label
    meta["tags"] = json.dumps(tags or [])
    meta["ingestion_ts"] = time.time()
    meta["processing_version"] = "aerialeye-v1"

    # --- Quality assessment ---
    quality = _assess_quality(stored_path)
    meta["quality_score"] = quality["score"]
    meta["cloud_cover"] = quality.get("cloud_cover", -1.0)

    # --- Thumbnail ---
    meta["thumbnail_b64"] = _generate_thumbnail(stored_path)

    # --- Persist to DB ---
    insert_scene(db, meta)

    # --- Generate embedding and add to FAISS ---
    vec, embed_label = embed_image(str(stored_path))
    faiss_pos = -1
    if vec is not None:
        faiss_pos = add_to_index(vec, {"asset_id": asset_id, "scene_id": meta["scene_id"]})
        embed_record = {
            "embed_id": str(uuid.uuid4()),
            "asset_id": asset_id,
            "tile_index": 0,
            "model_name": "clip-vit-base-patch32",
            "model_version": "openai/clip-vit-base-patch32",
            "faiss_index_pos": faiss_pos,
            "created_ts": time.time(),
        }
        insert_embedding(db, embed_record)

    logger.info(
        "Ingested asset_id=%s scene_id=%s quality=%.2f faiss_pos=%d",
        asset_id, meta["scene_id"], meta["quality_score"], faiss_pos,
    )

    return {
        "status": "ingested",
        "asset_id": asset_id,
        "scene_id": meta["scene_id"],
        "quality_score": meta["quality_score"],
        "embedding_available": vec is not None,
        "faiss_position": faiss_pos,
        "label": label,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:32]


def _scene_exists_fast(db, asset_id: str) -> bool:
    try:
        row = db.execute("SELECT asset_id FROM scenes WHERE asset_id = ?", [asset_id]).fetchone()
        return row is not None
    except Exception:
        return False


def _extract_metadata(
    path: Path,
    file_bytes: bytes,
    filename: str,
    sensor: str,
    acquisition_time: Optional[str],
    bbox: Optional[List[float]] = None,
    crs: Optional[str] = None,
) -> Dict[str, Any]:
    meta: Dict[str, Any] = {
        "scene_id": _make_scene_id(filename),
        "source": filename,
        "sensor": sensor,
        "acquisition_time": acquisition_time or _guess_acquisition_time(filename),
        "crs": crs or "pixel",
        "bbox": json.dumps(bbox) if bbox else "[]",
        "resolution": 0.0,
        "bands": json.dumps(["R", "G", "B"]),
        "file_path": str(path),
    }

    # Try rasterio for GeoTIFF
    if path.suffix.lower() in (".tif", ".tiff"):
        try:
            import rasterio

            with rasterio.open(str(path)) as src:
                if not crs:
                    meta["crs"] = str(src.crs) if src.crs else "unknown"
                if not bbox:
                    bounds = src.bounds
                    meta["bbox"] = json.dumps([bounds.left, bounds.bottom, bounds.right, bounds.top])
                meta["resolution"] = float(src.res[0]) if src.res else 0.0
                meta["bands"] = json.dumps(list(range(1, src.count + 1)))
                meta["sensor"] = sensor or "GeoTIFF"
        except Exception as exc:
            logger.debug("rasterio metadata extraction failed: %s", exc)

    # Try EXIF for JPEG
    if path.suffix.lower() in (".jpg", ".jpeg"):
        try:
            img = Image.open(str(path))
            exif_data = img._getexif() or {}
            for tag_id, value in exif_data.items():
                tag = ExifTags.TAGS.get(tag_id, tag_id)
                if tag == "DateTimeOriginal" and not acquisition_time:
                    meta["acquisition_time"] = str(value).replace(":", "-", 2)
        except Exception:
            pass

    return meta


def _guess_acquisition_time(filename: str) -> str:
    """Try to parse a date from the filename, else return a demo date."""
    import re
    patterns = [
        r"(\d{4}-\d{2}-\d{2})",
        r"(\d{4}\d{2}\d{2})",
    ]
    for pat in patterns:
        m = re.search(pat, filename)
        if m:
            raw = m.group(1).replace("-", "")
            if len(raw) == 8:
                return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}T00:00:00Z"
    # Fallback: use file modification time or current time
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _make_scene_id(filename: str) -> str:
    stem = Path(filename).stem[:40]
    return f"scene_{stem}_{int(time.time())}"


def _assess_quality(path: Path) -> Dict[str, Any]:
    """
    Compute quality score (0-1) using:
    - Laplacian variance (sharpness)
    - Brightness distribution
    Returns score and estimated cloud_cover.
    """
    try:
        img = cv2.imread(str(path))
        if img is None:
            return {"score": 0.5, "cloud_cover": -1.0}

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Sharpness: Laplacian variance
        lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        # Normalize: > 500 = very sharp, < 10 = very blurry
        sharpness = min(1.0, lap_var / 500.0)

        # Brightness
        mean_brightness = float(gray.mean()) / 255.0
        # Penalize near-white (clouds) and near-black
        brightness_score = 1.0 - abs(mean_brightness - 0.45) * 2.0
        brightness_score = max(0.0, min(1.0, brightness_score))

        # Cloud heuristic: high mean brightness in BGR = likely cloud/haze
        cloud_cover = max(0.0, min(1.0, (mean_brightness - 0.6) * 2.5)) if mean_brightness > 0.6 else 0.0

        score = 0.6 * sharpness + 0.4 * brightness_score
        return {"score": round(score, 3), "cloud_cover": round(cloud_cover, 3)}
    except Exception as exc:
        logger.debug("Quality assessment failed: %s", exc)
        return {"score": 0.5, "cloud_cover": -1.0}


def _generate_thumbnail(path: Path, size: Tuple[int, int] = (256, 256)) -> str:
    """Generate a base64-encoded JPEG thumbnail."""
    try:
        img = Image.open(str(path)).convert("RGB")
        img.thumbnail(size, Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception as exc:
        logger.debug("Thumbnail generation failed: %s", exc)
        return ""
