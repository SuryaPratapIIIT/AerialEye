import os
import re
import json
import uuid
import time
import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

import yaml
import rasterio
from rasterio.windows import Window
import numpy as np
from pyproj import Transformer
from shapely.geometry import box
import cv2

from backend.repository import GeoRepository

logger = logging.getLogger("aerialeye.geospatial_ingest")

PIPELINE_VERSION = "geospatial-v1"


def stable_tile_id(scene_id: str, row: int, col: int) -> int:
    """Deterministic positive int64 suitable for FAISS IndexIDMap2."""
    digest = hashlib.md5(f"{scene_id}:{row}:{col}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & 0x7FFFFFFFFFFFFFFF


def infer_source_type(meta: Dict[str, Any], files: List[Path]) -> str:
    paths = " ".join(str(f).lower() for f in files)
    name = str(meta.get("scene_name", meta.get("scene_id", ""))).lower()
    if "demo" in paths or "demo" in name or re.search(r"site0\d", name) or re.search(r"site0\d", paths):
        return "DEMO"
    if not meta.get("georeferenced"):
        return "LEGACY"
    if "whatsapp" in paths or "whatsapp" in name:
        return "LEGACY"
    return "REAL"

@dataclass
class IngestionConfig:
    tile_size: int
    overlap: int
    edge_tiles: str
    min_valid_fraction: float
    nodata_fraction_threshold: float
    scl_masks: dict
    qa_masks: dict

def load_config(path: str = "config.yaml") -> IngestionConfig:
    with open(path, "r") as f:
        data = yaml.safe_load(f)
    ingest = data.get("ingestion", {})
    masks = data.get("masks", {})
    return IngestionConfig(
        tile_size=ingest.get("tile_size", 256),
        overlap=ingest.get("overlap", 32),
        edge_tiles=ingest.get("edge_tiles", "drop"),
        min_valid_fraction=ingest.get("min_valid_fraction", 0.5),
        nodata_fraction_threshold=ingest.get("nodata_fraction_threshold", 0.5),
        scl_masks=masks.get("sentinel2_scl", {}),
        qa_masks=masks.get("landsat_qa", {})
    )

def discover_files(folder: Path) -> List[Path]:
    extensions = {".tif", ".tiff", ".jpg", ".jpeg", ".png"}
    return [p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in extensions]

def group_into_scenes(files: List[Path]) -> Dict[str, List[Path]]:
    scenes = {}
    for f in files:
        stem = f.stem
        # Basic heuristic for S2: S2A_MSIL2A_20240315T053641_...
        # Just use the part before the band name or the whole stem if single file
        # S2 usually has _B02.tif, Landsat has _B2.TIF
        match = re.search(r'^(.*?)_(B\d+|SCL|QA_PIXEL)$', stem, re.IGNORECASE)
        if match:
            scene_id = match.group(1)
        else:
            scene_id = stem
            
        if scene_id not in scenes:
            scenes[scene_id] = []
        scenes[scene_id].append(f)
    return scenes

def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def extract_metadata(scene_name: str, files: List[Path]) -> Dict[str, Any]:
    # Determine primary file (multi-band or B04/B02)
    primary = files[0]
    for f in files:
        if "B04" in f.name.upper() or "B4" in f.name.upper() or len(files) == 1:
            primary = f
            break
            
    is_georef = primary.suffix.lower() in [".tif", ".tiff"]
    
    # Try to parse sensor from name
    sensor = "unknown"
    name_upper = scene_name.upper()
    if name_upper.startswith("S2") or name_upper.startswith("SENTINEL-2"):
        sensor = "Sentinel-2"
    elif name_upper.startswith("LC") or name_upper.startswith("LANDSAT"):
        sensor = "Landsat"
    elif name_upper.startswith("S1"):
        sensor = "Sentinel-1"
        
    # Date
    acquisition = ""
    date_source = ""
    date_match = re.search(r'(\d{8}T\d{6}|\d{8})', name_upper)
    if date_match:
        raw = date_match.group(1)
        if "T" in raw:
            acquisition = f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}T{raw[9:11]}:{raw[11:13]}:{raw[13:15]}Z"
        else:
            acquisition = f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}T00:00:00Z"
        date_source = "filename"
    
    meta = {
        "scene_name": scene_name,
        "sensor": sensor,
        "product_level": "unknown",
        "acquisition_datetime": acquisition,
        "date_source": date_source,
        "georeferenced": is_georef,
        "primary_path": primary,
        "crs": "pixel",
        "transform_json": "[]",
        "width": 0,
        "height": 0,
        "resolution_m": 0.0,
        "bounds_native_json": "[]",
        "minlon": 0.0, "minlat": 0.0, "maxlon": 0.0, "maxlat": 0.0,
        "band_names_json": "[]",
        "nodata": None,
        "cloud_mask_available": False,
        "scl_path": None,
        "qa_path": None
    }
    
    if is_georef:
        try:
            with rasterio.open(str(primary)) as src:
                meta["crs"] = src.crs.to_string() if src.crs else "unknown"
                meta["transform_json"] = json.dumps([src.transform.a, src.transform.b, src.transform.c, 
                                                     src.transform.d, src.transform.e, src.transform.f])
                meta["width"] = src.width
                meta["height"] = src.height
                meta["resolution_m"] = float(src.res[0])
                meta["bounds_native_json"] = json.dumps([src.bounds.left, src.bounds.bottom, src.bounds.right, src.bounds.top])
                meta["nodata"] = src.nodata
                meta["band_names_json"] = json.dumps(list(src.descriptions) if any(src.descriptions) else [str(i) for i in range(1, src.count+1)])
                
                # Try tags for date
                tags = src.tags()
                if not acquisition:
                    for t in ["TIFFTAG_DATETIME", "DATETIME", "SENSING_TIME"]:
                        if t in tags:
                            meta["acquisition_datetime"] = tags[t]
                            meta["date_source"] = "tags"
                            break
                
                # Transform bounds to EPSG:4326
                if src.crs and src.crs.to_epsg() != 4326:
                    transformer = Transformer.from_crs(src.crs, "epsg:4326", always_xy=True)
                    xs = [src.bounds.left, src.bounds.right]
                    ys = [src.bounds.bottom, src.bounds.top]
                    lons, lats = transformer.transform([xs[0], xs[1], xs[1], xs[0]], [ys[0], ys[0], ys[1], ys[1]])
                    meta["minlon"], meta["maxlon"] = min(lons), max(lons)
                    meta["minlat"], meta["maxlat"] = min(lats), max(lats)
                else:
                    meta["minlon"], meta["maxlon"] = src.bounds.left, src.bounds.right
                    meta["minlat"], meta["maxlat"] = src.bounds.bottom, src.bounds.top
        except Exception as e:
            logger.warning(f"Failed to read raster metadata for {primary}: {e}")
            
    # Check for masks
    for f in files:
        if "SCL" in f.name.upper():
            meta["scl_path"] = f
            meta["cloud_mask_available"] = True
        if "QA_PIXEL" in f.name.upper():
            meta["qa_path"] = f
            meta["cloud_mask_available"] = True
            
    # Fallback date
    if not meta["acquisition_datetime"]:
        mtime = os.path.getmtime(str(primary))
        meta["acquisition_datetime"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(mtime))
        meta["date_source"] = "fallback"

    if "L2A" in name_upper:
        meta["product_level"] = "L2A"
    elif "L1C" in name_upper:
        meta["product_level"] = "L1C"

    # Deterministic scene_id
    id_str = f"{meta['sensor']}_{scene_name}_{meta['acquisition_datetime']}"
    meta["scene_id"] = hashlib.sha256(id_str.encode()).hexdigest()[:32]
    
    return meta

def compute_quality_mask(scl_window, config: IngestionConfig, sensor: str):
    if scl_window is None:
        return None, "none"
        
    mask = np.zeros_like(scl_window, dtype=np.uint8) # 0=valid, 1=cloud, 2=shadow, 3=snow
    if sensor == "Sentinel-2":
        clouds = config.scl_masks.get("cloud", [8,9]) + config.scl_masks.get("cirrus", [10])
        shadows = config.scl_masks.get("cloud_shadow", [3])
        snow = config.scl_masks.get("snow", [11])
        
        mask[np.isin(scl_window, clouds)] = 1
        mask[np.isin(scl_window, shadows)] = 2
        mask[np.isin(scl_window, snow)] = 3
        return mask, "scl"
    elif sensor == "Landsat":
        cloud_bit = config.qa_masks.get("cloud_bit", 3)
        shadow_bit = config.qa_masks.get("cloud_shadow_bit", 4)
        snow_bit = config.qa_masks.get("snow_bit", 5)
        
        mask[(scl_window & (1 << cloud_bit)) > 0] = 1
        mask[(scl_window & (1 << shadow_bit)) > 0] = 2
        mask[(scl_window & (1 << snow_bit)) > 0] = 3
        return mask, "qa_pixel"
        
    return None, "none"

def normalize_rgb(img_array):
    out = np.zeros_like(img_array, dtype=np.uint8)
    for i in range(img_array.shape[0]):
        band = img_array[i].astype(float)
        p2, p98 = np.percentile(band[band > 0] if np.any(band > 0) else band, (2, 98))
        if p98 > p2:
            band = np.clip((band - p2) / (p98 - p2) * 255.0, 0, 255)
        out[i] = band.astype(np.uint8)
    return out

def generate_legacy_tile(meta: Dict[str, Any], output_dir: Path) -> List[Dict[str, Any]]:
    """One tile per non-georeferenced JPG/PNG using the preview image as chip."""
    scene_id = meta["scene_id"]
    primary = Path(meta["primary_path"])
    scene_dir = output_dir / scene_id
    scene_dir.mkdir(parents=True, exist_ok=True)

    tile_id = stable_tile_id(scene_id, 0, 0)
    preview_path = scene_dir / f"{tile_id}.png"
    chip_path = scene_dir / f"{tile_id}.npy"

    try:
        from PIL import Image

        img = Image.open(primary).convert("RGB")
        arr = np.asarray(img)
        img.save(str(preview_path))
        # Store HWC uint8 so embedder can use preview path for LEGACY
        np.save(str(chip_path), arr)
        h, w = arr.shape[:2]
    except Exception as exc:
        logger.warning("Failed to create LEGACY tile for %s: %s", scene_id, exc)
        return []

    return [
        {
            "tile_id": tile_id,
            "scene_id": scene_id,
            "row": 0,
            "col": 0,
            "window_json": json.dumps([0, 0, w, h]),
            "footprint_wkt": "POLYGON EMPTY",
            "minlon": 0.0,
            "minlat": 0.0,
            "maxlon": 0.0,
            "maxlat": 0.0,
            "centroid_lon": 0.0,
            "centroid_lat": 0.0,
            "nodata_fraction": 0.0,
            "cloud_fraction": -1.0,  # unknown; search treats via null_cloud_fraction / NULL updates
            "shadow_fraction": 0.0,
            "snow_fraction": 0.0,
            "valid_fraction": 1.0,
            "quality_source": "legacy_rgb",
            "preview_path": str(preview_path),
            "chip_path": str(chip_path),
            "mask_path": "",
            "embedded": False,
            "superseded": False,
        }
    ]


def generate_tiles(meta: Dict[str, Any], config: IngestionConfig, output_dir: Path) -> List[Dict[str, Any]]:
    if not meta["georeferenced"]:
        return generate_legacy_tile(meta, output_dir)

    primary_path = meta["primary_path"]
    scene_id = meta["scene_id"]
    tile_size = config.tile_size
    step = tile_size - config.overlap

    tiles = []

    scene_dir = output_dir / scene_id
    scene_dir.mkdir(parents=True, exist_ok=True)

    with rasterio.open(str(primary_path)) as src:
        width, height = src.width, src.height
        transformer = None
        if src.crs and src.crs.to_epsg() != 4326:
            transformer = Transformer.from_crs(src.crs, "epsg:4326", always_xy=True)
            
        scl_src = None
        if meta["scl_path"]:
            scl_src = rasterio.open(str(meta["scl_path"]))
        elif meta["qa_path"]:
            scl_src = rasterio.open(str(meta["qa_path"]))
            
        try:
            for row, y in enumerate(range(0, height, step)):
                for col, x in enumerate(range(0, width, step)):
                    win = Window(x, y, tile_size, tile_size)
                    # Check edge
                    actual_w = min(tile_size, width - x)
                    actual_h = min(tile_size, height - y)
                    
                    if config.edge_tiles == "drop" and (actual_w < tile_size * config.min_valid_fraction or actual_h < tile_size * config.min_valid_fraction):
                        continue
                        
                    data = src.read(window=win)
                    
                    # Nodata check
                    nodata_val = src.nodata if src.nodata is not None else 0
                    nodata_mask = (data[0] == nodata_val)
                    nodata_frac = float(np.sum(nodata_mask) / (win.width * win.height))
                    
                    if nodata_frac > config.nodata_fraction_threshold:
                        continue
                        
                    # Geometry
                    win_bounds = rasterio.windows.bounds(win, src.transform)
                    poly = box(*win_bounds)
                    if transformer:
                        coords = list(poly.exterior.coords)
                        xs, ys = zip(*coords)
                        lons, lats = transformer.transform(xs, ys)
                        poly_wgs84 = box(min(lons), min(lats), max(lons), max(lats))
                    else:
                        poly_wgs84 = poly
                        
                    bounds = poly_wgs84.bounds
                    
                    # Mask
                    cloud_frac, shadow_frac, snow_frac, valid_frac = 0.0, 0.0, 0.0, 1.0 - nodata_frac
                    quality_source = "none"
                    mask_chip = None
                    if scl_src:
                        # Reproject window bounds to SCL src if needed (simplification: assuming same grid for now or use VRT)
                        # Read SCL
                        scl_win = Window(x, y, tile_size, tile_size) # Assumes same res. In real S2, SCL is 20m, B04 is 10m.
                        # For a robust pipeline, rasterio.vrt.WarpedVRT is better, but we do naive read if same shape, or resample
                        # We will just attempt to read a matching geographic window
                        scl_win = rasterio.windows.from_bounds(*win_bounds, transform=scl_src.transform)
                        scl_data = scl_src.read(1, window=scl_win, out_shape=(1, actual_h, actual_w), resampling=rasterio.enums.Resampling.nearest)
                        
                        mask, quality_source = compute_quality_mask(scl_data, config, meta["sensor"])
                        if mask is not None:
                            cloud_frac = float(np.sum(mask == 1) / mask.size)
                            shadow_frac = float(np.sum(mask == 2) / mask.size)
                            snow_frac = float(np.sum(mask == 3) / mask.size)
                            valid_frac = float(np.sum(mask == 0) / mask.size) - nodata_frac
                            mask_chip = mask

                    tile_id = stable_tile_id(scene_id, row, col)

                    # Save artifacts (filenames use stable integer tile_id)
                    preview_path = scene_dir / f"{tile_id}.png"
                    chip_path = scene_dir / f"{tile_id}.npy"
                    mask_path = scene_dir / f"{tile_id}_mask.npy" if mask_chip is not None else None

                    # RGB for preview (assume first 3 bands are RGB or just 1 band grayscale)
                    rgb = data[:3] if data.shape[0] >= 3 else data
                    rgb_norm = normalize_rgb(rgb)
                    # Transpose for cv2 (C, H, W) -> (H, W, C)
                    rgb_norm = np.transpose(rgb_norm, (1, 2, 0))
                    if rgb_norm.shape[2] == 3:
                        rgb_norm = cv2.cvtColor(rgb_norm, cv2.COLOR_RGB2BGR)
                    cv2.imwrite(str(preview_path), rgb_norm)

                    np.save(str(chip_path), data)
                    if mask_path:
                        np.save(str(mask_path), mask_chip)

                    tiles.append({
                        "tile_id": tile_id,
                        "scene_id": scene_id,
                        "row": row,
                        "col": col,
                        "window_json": json.dumps([x, y, win.width, win.height]),
                        "footprint_wkt": poly_wgs84.wkt,
                        "minlon": bounds[0],
                        "minlat": bounds[1],
                        "maxlon": bounds[2],
                        "maxlat": bounds[3],
                        "centroid_lon": poly_wgs84.centroid.x,
                        "centroid_lat": poly_wgs84.centroid.y,
                        "nodata_fraction": nodata_frac,
                        "cloud_fraction": cloud_frac,
                        "shadow_fraction": shadow_frac,
                        "snow_fraction": snow_frac,
                        "valid_fraction": max(0.0, valid_frac),
                        "quality_source": quality_source,
                        "preview_path": str(preview_path),
                        "chip_path": str(chip_path),
                        "mask_path": str(mask_path) if mask_path else "",
                        "embedded": False,
                        "superseded": False,
                    })
        finally:
            if scl_src:
                scl_src.close()
                
    return tiles

def persist_scene(meta: Dict[str, Any], files: List[Path], tiles: List[Dict[str, Any]], repo: GeoRepository):
    source_type = meta.get("source_type") or infer_source_type(meta, files)
    # Scene
    scene = {
        "scene_id": meta["scene_id"],
        "sensor": meta["sensor"],
        "product_level": meta["product_level"],
        "acquisition_datetime": meta["acquisition_datetime"],
        "date_source": meta["date_source"],
        "crs": meta["crs"],
        "transform_json": meta["transform_json"],
        "width": meta["width"],
        "height": meta["height"],
        "resolution_m": meta["resolution_m"],
        "bounds_native_json": meta["bounds_native_json"],
        "minlon": meta["minlon"],
        "minlat": meta["minlat"],
        "maxlon": meta["maxlon"],
        "maxlat": meta["maxlat"],
        "band_names_json": meta["band_names_json"],
        "nodata": meta["nodata"] if meta["nodata"] is not None else -9999.0,
        "georeferenced": meta["georeferenced"],
        "cloud_mask_available": meta["cloud_mask_available"],
        "ingested_at": time.time(),
        "pipeline_version": PIPELINE_VERSION,
        "source_type": source_type,
    }

    repo.insert_scene(scene)
    
    # Files
    scene_files = []
    for f in files:
        scene_files.append({
            "id": str(uuid.uuid4()),
            "scene_id": meta["scene_id"],
            "path": str(f),
            "band_role": f.stem,
            "sha256": compute_sha256(f),
            "size_bytes": os.path.getsize(f)
        })
    repo.insert_scene_files(scene_files)
    
    # Tiles
    repo.insert_tiles(tiles)
    
    # Provenance JSON
    prov_dir = Path("data/provenance")
    prov_dir.mkdir(parents=True, exist_ok=True)
    prov = {
        "scene": scene,
        "files": scene_files,
        "tiles_count": len(tiles),
        "versions": {
            "pipeline": PIPELINE_VERSION,
            "rasterio": rasterio.__version__
        }
    }
    with open(prov_dir / f"{meta['scene_id']}.json", "w") as f:
        json.dump(prov, f, indent=2)

def process_folder(folder: str, config_path: str = "config.yaml"):
    config = load_config(config_path)
    repo = GeoRepository()
    
    raw_dir = Path(folder)
    out_dir = Path("data/tiles")
    
    files = discover_files(raw_dir)
    scenes = group_into_scenes(files)
    
    results = {"new": 0, "skipped": 0, "failed": 0, "tiles": 0}
    
    for scene_name, scene_files in scenes.items():
        started_at = time.time()
        try:
            meta = extract_metadata(scene_name, scene_files)
            scene_id = meta["scene_id"]
            
            # Idempotency / Incremental check
            existing = repo.get_scene(scene_id)
            if existing:
                # Check hashes
                old_files = repo.get_scene_files(scene_id)
                old_hashes = {f["path"]: f["sha256"] for f in old_files}
                changed = False
                for f in scene_files:
                    path_str = str(f)
                    if path_str not in old_hashes or compute_sha256(f) != old_hashes[path_str]:
                        changed = True
                        break
                if not changed:
                    logger.info(f"Skipping {scene_name} (already ingested)")
                    results["skipped"] += 1
                    continue
                else:
                    logger.info(f"Re-ingesting {scene_name} (files changed)")
                    # Soft-delete so FAISS IDs are filtered at query time (no index rebuild)
                    repo.mark_scene_tiles_superseded(scene_id)

            meta["source_type"] = infer_source_type(meta, scene_files)
            tiles = generate_tiles(meta, config, out_dir)
            persist_scene(meta, scene_files, tiles, repo)
            
            repo.log_ingestion({
                "id": str(uuid.uuid4()),
                "scene_id": scene_id,
                "started_at": started_at,
                "finished_at": time.time(),
                "status": "complete",
                "tiles_created": len(tiles),
                "warnings_json": "[]",
                "error": ""
            })
            results["new"] += 1
            results["tiles"] += len(tiles)
            
        except Exception as e:
            logger.exception(f"Failed to process {scene_name}")
            repo.log_ingestion({
                "id": str(uuid.uuid4()),
                "scene_id": scene_name,
                "started_at": started_at,
                "finished_at": time.time(),
                "status": "failed",
                "tiles_created": 0,
                "warnings_json": "[]",
                "error": str(e)
            })
            results["failed"] += 1
            
    return results
