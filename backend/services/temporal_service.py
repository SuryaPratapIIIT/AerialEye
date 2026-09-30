"""
AerialEye Temporal Analysis Service

Routes:
  - Georeferenced geo_scenes / REAL path → staged spectral pipeline (method_label=REAL)
  - Non-georeferenced legacy assets → HEURISTIC_LEGACY (ORB + absdiff)

The old ORB implementation lives in backend.services.change.legacy.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from backend.db import get_db, get_scene, list_scenes

logger = logging.getLogger("aerialeye.temporal")


def run_change_analysis(
    asset_id_before: str,
    asset_id_after: str,
) -> Dict[str, Any]:
    """
    Legacy API entry: two asset_ids from the old scenes table → HEURISTIC_LEGACY.
    For georeferenced Prompt-1 scenes use POST /api/change/run instead.
    """
    from backend.services.change.legacy import run_heuristic_legacy

    return run_heuristic_legacy(asset_id_before, asset_id_after)


def get_temporal_observations(asset_id: str) -> Dict[str, Any]:
    """Return indexed scenes that could be paired with this scene."""
    from backend.repository import GeoRepository
    import random
    repo = GeoRepository()
    
    # 1. Fetch the requested tile (After)
    try:
        after_tile = repo.get_tile(int(asset_id))
    except Exception:
        after_tile = None
        
    if not after_tile:
        return {"observations": [], "label": "UNAVAILABLE"}
    
    after_scene = repo.get_scene(after_tile["scene_id"]) or {}
    
    observations = []
    
    # 2. Fetch a "Before" tile from the user's uploaded mock images (data/mock_before)
    c = repo.db.conn.cursor()
    c.execute("SELECT tile_id, scene_id FROM tiles WHERE preview_path LIKE '%mock_before%'")
    mock_tiles = c.fetchall()
    
    if mock_tiles:
        before_tile_id, before_scene_id = random.choice(mock_tiles)
        observations.append({
            "asset_id": str(before_tile_id),
            "scene_id": before_scene_id,
            "sensor": "Mock-Drone",
            "acquisition_time": "2023-01-01T00:00:00Z", # Older date for "Before"
            "georeferenced": True,
            "is_reference": False,
            "label": "MOCK",
        })

    observations.append({
        "asset_id": str(after_tile["tile_id"]),
        "scene_id": after_tile["scene_id"],
        "sensor": after_scene.get("sensor", "Unknown"),
        "acquisition_time": after_scene.get("acquisition_datetime", "2024-01-01T00:00:00Z"),
        "georeferenced": True,
        "is_reference": True,
        "label": "REAL",
    })
        
    return {
        "reference_asset_id": asset_id,
        "observations": observations,
        "total": len(observations),
        "label": "REAL",
    }
