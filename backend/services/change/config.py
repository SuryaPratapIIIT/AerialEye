"""Load and validate change: section from config.yaml."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.yaml"

_DEFAULTS: Dict[str, Any] = {
    "pipeline_version": "change-v1",
    "min_usable_fraction": 0.6,
    "min_overlap": 0.5,
    "min_polygon_usable_fraction": 0.7,
    "target_resolution_m": 10.0,
    "max_shift_px": 5.0,
    "min_shift_px": 0.1,
    "min_registration_correlation": 0.3,
    "reject_poor_registration": False,
    "mask_dilation_px": 3,
    "blue_haze_threshold": 0.25,
    "brightness_outlier_sigma": 3.0,
    "no_mask_confidence_cap": 0.5,
    "irmad_iterations": 4,
    "irmad_exclude_pct": 0.2,
    "min_stable_pixels": 500,
    "sigma_k": 3.0,
    "abs_min_ndvi": 0.08,
    "abs_min_ndbi": 0.08,
    "abs_min_mndwi": 0.10,
    "abs_min_bsi": 0.08,
    "water_mndwi_threshold": 0.0,
    "builtup_ndbi_threshold": 0.05,
    "vegetation_ndvi_threshold": 0.3,
    "min_area_m2": 400.0,
    "morph_open_px": 1,
    "morph_close_px": 2,
    "edge_alignment_threshold": 0.55,
    "compactness_min": 0.15,
    "score_weights": {"ndvi": 0.25, "ndbi": 0.30, "mndwi": 0.20, "bsi": 0.15, "structural": 0.10},
    "unclassified_confidence_min": 0.75,
    "report_seasonal": False,
    "season_window_days": 45,
    "prefer_same_season": True,
    "opposite_season_doy_diff": 90,
    "min_persistence_obs": 1,
    "cloud_proximity_radius_px": 15,
    "cloud_neighbourhood_mask_frac": 0.35,
    "allow_cross_sensor": False,
    "cross_sensor_confidence_cap": 0.55,
    "phenology_ndvi_only_as_seasonal": True,
    "confidence_weights": {
        "usable_fraction": 0.15,
        "magnitude_sigma": 0.25,
        "persistence": 0.15,
        "registration": 0.10,
        "rule_consistency": 0.15,
        "shape": 0.10,
        "same_season": 0.10,
    },
    "confidence_penalties": {
        "no_mask": 0.7,
        "single_observation": 0.75,
        "cloud_proximity": 0.8,
        "poor_registration": 0.7,
        "opposite_season": 0.85,
    },
    "high_confidence": 0.75,
    "medium_confidence": 0.5,
    "return_low_confidence": False,
    "band_maps": {
        "Sentinel-2": {
            "B02": "B02", "B03": "B03", "B04": "B04",
            "B08": "B08", "B11": "B11", "B12": "B12", "SCL": "SCL",
        },
        "Landsat": {
            "B02": "SR_B2", "B03": "SR_B3", "B04": "SR_B4",
            "B08": "SR_B5", "B11": "SR_B6", "B12": "SR_B7", "SCL": "QA_PIXEL",
        },
    },
}


def load_change_config(path: Optional[str] = None) -> Dict[str, Any]:
    cfg_path = Path(path) if path else CONFIG_PATH
    data: Dict[str, Any] = {}
    if cfg_path.exists():
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    change = dict(_DEFAULTS)
    change.update(data.get("change") or {})
    # deep-merge nested dicts
    for key in ("score_weights", "confidence_weights", "confidence_penalties", "band_maps"):
        if key in (data.get("change") or {}):
            merged = dict(_DEFAULTS.get(key, {}))
            incoming = data["change"][key]
            if isinstance(incoming, dict):
                if key == "band_maps":
                    merged.update(incoming)
                else:
                    merged.update(incoming)
            change[key] = merged
    return change


def band_map_for_sensor(cfg: Dict[str, Any], sensor: str) -> Dict[str, str]:
    maps = cfg.get("band_maps") or {}
    for key, mapping in maps.items():
        if key.lower() in (sensor or "").lower() or (sensor or "").lower() in key.lower():
            return dict(mapping)
    # default Sentinel-2 logical names
    return dict(maps.get("Sentinel-2") or _DEFAULTS["band_maps"]["Sentinel-2"])
