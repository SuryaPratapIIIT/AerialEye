"""Shared typed structures for the change pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


@dataclass
class SceneObservation:
    scene_id: str
    sensor: str
    acquisition_datetime: str
    georeferenced: bool
    source_type: str
    minlon: float
    minlat: float
    maxlon: float
    maxlat: float
    usable_fraction_aoi: float
    quality_source: str = "none"
    bands: Dict[str, np.ndarray] = field(default_factory=dict)  # logical B02..B12, SCL
    transform: Any = None  # affine
    crs: Any = None
    resolution_m: float = 10.0
    unusable_reason: Optional[str] = None


@dataclass
class CommonGrid:
    """Shared raster grid for a before/after pair (Stage 1 output)."""
    bands_before: Dict[str, np.ndarray]
    bands_after: Dict[str, np.ndarray]
    transform: Any
    crs: Any
    resolution_m: float
    overlap_fraction: float
    height: int
    width: int
    aoi_mask: np.ndarray  # bool, True = inside AOI


@dataclass
class RegistrationResult:
    shift_y: float
    shift_x: float
    correlation: float
    quality: str  # good | poor | skipped
    applied: bool


@dataclass
class QualityMaskResult:
    invalid: np.ndarray  # bool True = unknown / invalid (exclude from stats)
    usable_fraction: float
    no_product_mask: bool
    before_cloud: np.ndarray
    after_cloud: np.ndarray


@dataclass
class RadiometryResult:
    bands_after_norm: Dict[str, np.ndarray]
    gains: Dict[str, float]
    offsets: Dict[str, float]
    stable_pixel_count: int
    method: str  # irmad | histogram


@dataclass
class IndexStack:
    before: Dict[str, np.ndarray]
    after: Dict[str, np.ndarray]
    delta: Dict[str, np.ndarray]
    sigma: Dict[str, float]
    structural_diff: np.ndarray


@dataclass
class ChangeCandidate:
    candidate_id: str
    geometry_geojson: Dict[str, Any]
    area_m2: float
    change_type: str
    direction: str
    confidence: float
    confidence_label: str
    confidence_breakdown: Dict[str, Any]
    evidence: Dict[str, Any]
    before_scene_id: str
    after_scene_id: str
    earliest_scene_id: str = ""
    earliest_date: str = ""
    last_clear_before_date: str = ""
    detection_window_days: float = 0.0
    usable_fraction: float = 1.0
    persistence_count: int = 0
    suppression_reasons: List[str] = field(default_factory=list)
    method_label: str = "REAL"
    low_temporal_support: bool = False
    skipped_scenes: List[str] = field(default_factory=list)
    rejected: bool = False
    rejection_reason: str = ""
    mask_label: Optional[np.ndarray] = None  # binary region on grid
    bbox_px: Optional[Tuple[int, int, int, int]] = None  # r0,r1,c0,c1
    before_thumb_path: str = ""
    after_thumb_path: str = ""
    overlay_path: str = ""
