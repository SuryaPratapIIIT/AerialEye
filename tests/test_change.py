import pytest
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any

from backend.services.change.types import SceneObservation, ChangeCandidate
from backend.services.change.pipeline import run_pair_from_observations
from backend.services.change.config import load_change_config
from backend.services.change.stages import find_earliest_supporting_observation
from scipy.ndimage import shift

def generate_synthetic_scene(
    scene_id: str,
    date: str,
    shape: tuple = (100, 100),
    base_veg: bool = True,
    clouds: bool = False,
    cloud_shadows: bool = False,
    building_mask: np.ndarray = None,
    bare_mask: np.ndarray = None,
    water_mask: np.ndarray = None,
    illumination_shift: float = 0.0,
    shift_px: tuple = (0, 0),
    add_noise: bool = True,
) -> SceneObservation:
    if base_veg:
        b02 = np.full(shape, 0.05, dtype=np.float32)
        b03 = np.full(shape, 0.08, dtype=np.float32)
        b04 = np.full(shape, 0.06, dtype=np.float32)
        b08 = np.full(shape, 0.35, dtype=np.float32)
        b11 = np.full(shape, 0.15, dtype=np.float32)
    else:
        b02 = np.full(shape, 0.10, dtype=np.float32)
        b03 = np.full(shape, 0.15, dtype=np.float32)
        b04 = np.full(shape, 0.20, dtype=np.float32)
        b08 = np.full(shape, 0.25, dtype=np.float32)
        b11 = np.full(shape, 0.35, dtype=np.float32)

    scl = np.full(shape, 4, dtype=np.float32)

    if building_mask is not None:
        b02[building_mask] = 0.15
        b03[building_mask] = 0.15
        b04[building_mask] = 0.20
        b08[building_mask] = 0.25
        b11[building_mask] = 0.40
        scl[building_mask] = 5

    if bare_mask is not None:
        b02[bare_mask] = 0.12
        b03[bare_mask] = 0.18
        b04[bare_mask] = 0.25
        b08[bare_mask] = 0.30
        b11[bare_mask] = 0.40
        scl[bare_mask] = 5

    if water_mask is not None:
        b02[water_mask] = 0.05
        b03[water_mask] = 0.08
        b04[water_mask] = 0.04
        b08[water_mask] = 0.02
        b11[water_mask] = 0.01
        scl[water_mask] = 6

    if clouds:
        c_mask = np.zeros(shape, dtype=bool)
        c_mask[10:30, 10:30] = True
        b02[c_mask] = 0.8
        b03[c_mask] = 0.8
        b04[c_mask] = 0.8
        b08[c_mask] = 0.8
        b11[c_mask] = 0.8
        scl[c_mask] = 9

    if cloud_shadows:
        s_mask = np.zeros(shape, dtype=bool)
        s_mask[30:50, 10:30] = True
        b02[s_mask] *= 0.3
        b03[s_mask] *= 0.3
        b04[s_mask] *= 0.3
        b08[s_mask] *= 0.3
        b11[s_mask] *= 0.3
        scl[s_mask] = 3

    if add_noise:
        for b in (b02, b03, b04, b08, b11):
            noise = np.random.normal(0, 0.005, shape).astype(np.float32)
            b += noise

    for b in (b02, b03, b04, b08, b11):
        b += illumination_shift

    if shift_px != (0, 0):
        sy, sx = shift_px
        b02 = shift(b02, (sy, sx), mode='nearest')
        b03 = shift(b03, (sy, sx), mode='nearest')
        b04 = shift(b04, (sy, sx), mode='nearest')
        b08 = shift(b08, (sy, sx), mode='nearest')
        b11 = shift(b11, (sy, sx), mode='nearest')
        scl = shift(scl, (sy, sx), mode='nearest')

    bands = {"B02": b02, "B03": b03, "B04": b04, "B08": b08, "B11": b11, "SCL": scl}
    
    return SceneObservation(
        scene_id=scene_id,
        sensor="Sentinel-2",
        acquisition_datetime=date,
        georeferenced=True,
        source_type="REAL",
        minlon=0, minlat=0, maxlon=0.01, maxlat=0.01,
        usable_fraction_aoi=1.0 if not clouds else 0.8,
        quality_source="scl",
        bands=bands,
        resolution_m=10.0,
    )

def run_synthetic_pair(b: SceneObservation, a: SceneObservation, cfg_overrides=None):
    cfg = load_change_config()
    if cfg_overrides:
        cfg.update(cfg_overrides)
    aoi_mask = np.ones((100, 100), dtype=bool)
    return run_pair_from_observations(b, a, aoi_mask, cfg, include_low_confidence=True)

# 1. Planted building
def test_building_detected():
    b_mask = np.zeros((100, 100), dtype=bool)
    b_mask[40:60, 40:60] = True
    before = generate_synthetic_scene("T1", "2023-06-01T10:00:00Z", base_veg=True)
    after = generate_synthetic_scene("T2", "2023-06-15T10:00:00Z", base_veg=True, building_mask=b_mask)
    res = run_synthetic_pair(before, after)
    
    assert res["success"]
    assert len(res["candidates"]) == 1
    cand = res["candidates"][0]
    assert cand.change_type == "construction"

# 2. Planted bare soil
def test_clearance_detected():
    bare_mask = np.zeros((100, 100), dtype=bool)
    bare_mask[40:60, 40:60] = True
    before = generate_synthetic_scene("T1", "2023-06-01T10:00:00Z", base_veg=True)
    after = generate_synthetic_scene("T2", "2023-06-15T10:00:00Z", base_veg=True, bare_mask=bare_mask)
    res = run_synthetic_pair(before, after)
    
    assert res["success"]
    assert len(res["candidates"]) == 1
    cand = res["candidates"][0]
    assert cand.change_type == "clearance"

# 3. Water body
def test_water_increase_detected():
    w_mask = np.zeros((100, 100), dtype=bool)
    w_mask[40:60, 40:60] = True
    before = generate_synthetic_scene("T1", "2023-06-01T10:00:00Z", base_veg=True)
    after = generate_synthetic_scene("T2", "2023-06-15T10:00:00Z", base_veg=True, water_mask=w_mask)
    res = run_synthetic_pair(before, after)
    
    assert res["success"]
    assert len(res["candidates"]) == 1
    cand = res["candidates"][0]
    assert cand.change_type == "water_extent_increase"

# 4. Cloud over AFTER image excludes pixels
def test_cloud_masks_pixels():
    b_mask = np.zeros((100, 100), dtype=bool)
    b_mask[15:25, 15:25] = True  # This is under the cloud [10:30, 10:30]
    before = generate_synthetic_scene("T1", "2023-06-01T10:00:00Z", base_veg=True)
    after = generate_synthetic_scene("T2", "2023-06-15T10:00:00Z", base_veg=True, building_mask=b_mask, clouds=True)
    res = run_synthetic_pair(before, after)
    
    assert res["success"]
    assert len(res["candidates"]) == 0  # Should be masked out by cloud

# 5. Cloud shadow suppressed
def test_cloud_shadow_suppressed():
    before = generate_synthetic_scene("T1", "2023-06-01T10:00:00Z", base_veg=True)
    after = generate_synthetic_scene("T2", "2023-06-15T10:00:00Z", base_veg=True, clouds=True, cloud_shadows=True)
    res = run_synthetic_pair(before, after, {"cloud_proximity_radius_px": 5})
    
    assert res["success"]
    assert len(res["candidates"]) == 0
    # The shadow might be detected as clearance or unclassified, but gets suppressed
    found = False
    for c in res["suppressed"]:
        if "cloud_shadow_suspect" in c.suppression_reasons or "cloud_proximity" in c.suppression_reasons:
            found = True
    assert found

# 6. Global brightness shift
def test_illumination_shift_normalized():
    before = generate_synthetic_scene("T1", "2023-06-01T10:00:00Z", base_veg=True)
    after = generate_synthetic_scene("T2", "2023-06-15T10:00:00Z", base_veg=True, illumination_shift=0.1)
    res = run_synthetic_pair(before, after)
    
    assert res["success"]
    assert len(res["candidates"]) == 0

# 7. Opposite seasons suppressed
def test_opposite_season_suppressed():
    before = generate_synthetic_scene("T1", "2023-01-01T10:00:00Z", base_veg=True)
    after = generate_synthetic_scene("T2", "2023-07-01T10:00:00Z", base_veg=False) # Fake season change to bare
    res = run_synthetic_pair(before, after)
    
    assert res["success"]
    assert len(res["candidates"]) == 0
    found = any("opposite_season" in c.suppression_reasons for c in res["suppressed"])
    assert found

# 8. Subpixel / small shift corrected
def test_registration_correction():
    b_mask = np.zeros((100, 100), dtype=bool)
    b_mask[40:60, 40:60] = True
    before = generate_synthetic_scene("T1", "2023-06-01T10:00:00Z", base_veg=True, building_mask=b_mask)
    after = generate_synthetic_scene("T2", "2023-06-15T10:00:00Z", base_veg=True, building_mask=b_mask, shift_px=(2, 2))
    res = run_synthetic_pair(before, after)
    
    assert res["success"]
    # No new building change, and edge-only misregistration should be suppressed or corrected
    assert len(res["candidates"]) == 0
    assert res["registration"]["applied"] == True

# 9. Persistence
def test_single_observation_low_confidence():
    b_mask = np.zeros((100, 100), dtype=bool)
    b_mask[40:60, 40:60] = True
    before = generate_synthetic_scene("T1", "2023-06-01T10:00:00Z", base_veg=True)
    after = generate_synthetic_scene("T2", "2023-06-15T10:00:00Z", base_veg=True, building_mask=b_mask)
    
    cfg = load_change_config()
    aoi_mask = np.ones((100, 100), dtype=bool)
    
    # 0 persistence count
    res = run_pair_from_observations(before, after, aoi_mask, cfg, persistence_counts={}, include_low_confidence=True)
    assert len(res["candidates"]) == 1
    cand = res["candidates"][0]
    assert "single_observation" in cand.suppression_reasons
    score1 = cand.confidence
    
    # 1 persistence count
    res2 = run_pair_from_observations(before, after, aoi_mask, cfg, persistence_counts={cand.candidate_id: 1}, include_low_confidence=True)
    cand2 = res2["candidates"][0]
    assert "single_observation" not in cand2.suppression_reasons
    score2 = cand2.confidence
    assert score2 > score1

# 10. Earliest observation
def test_earliest_observation():
    cand = ChangeCandidate(
        candidate_id="test",
        geometry_geojson={},
        area_m2=1000,
        change_type="construction",
        direction="appearance",
        confidence=0.9,
        confidence_label="high",
        confidence_breakdown={},
        evidence={},
        before_scene_id="T1",
        after_scene_id="T6"
    )
    series = [
        {"scene_id": "T1", "date": "2023-01-01T00:00:00Z", "usable_fraction": 0.9, "indicator": 0.1},
        {"scene_id": "T2", "date": "2023-02-01T00:00:00Z", "usable_fraction": 0.9, "indicator": 0.15},
        {"scene_id": "T3", "date": "2023-03-01T00:00:00Z", "usable_fraction": 0.2, "indicator": 0.0}, # cloudy
        {"scene_id": "T4", "date": "2023-04-01T00:00:00Z", "usable_fraction": 0.9, "indicator": 0.8}, # changed
        {"scene_id": "T5", "date": "2023-05-01T00:00:00Z", "usable_fraction": 0.9, "indicator": 0.82},
        {"scene_id": "T6", "date": "2023-06-01T00:00:00Z", "usable_fraction": 0.9, "indicator": 0.85},
    ]
    cfg = load_change_config()
    find_earliest_supporting_observation(cand, series, cfg)
    
    assert cand.earliest_scene_id == "T4"
    assert "T3" in cand.skipped_scenes
    assert cand.last_clear_before_date == "2023-02-01T00:00:00Z"
    # window is T2 to T4 (days between 2023-02-01 and 2023-04-01)
    assert cand.detection_window_days == 59.0

# 11. Overlap reject
def test_overlap_reject():
    before = generate_synthetic_scene("T1", "2023-06-01T10:00:00Z", base_veg=True)
    after = generate_synthetic_scene("T2", "2023-06-15T10:00:00Z", base_veg=True)
    aoi_mask = np.zeros((100, 100), dtype=bool) # 0 overlap
    cfg = load_change_config()
    try:
        res = run_pair_from_observations(before, after, aoi_mask, cfg)
        assert False, "Should raise ValueError on overlap"
    except ValueError as e:
        assert "overlap" in str(e).lower()

# 12. Output schema
def test_output_schema():
    b_mask = np.zeros((100, 100), dtype=bool)
    b_mask[40:60, 40:60] = True
    before = generate_synthetic_scene("T1", "2023-06-01T10:00:00Z", base_veg=True)
    after = generate_synthetic_scene("T2", "2023-06-15T10:00:00Z", base_veg=True, building_mask=b_mask)
    res = run_synthetic_pair(before, after)
    
    assert res["success"]
    cand = res["candidates"][0]
    assert hasattr(cand, "geometry_geojson")
    assert hasattr(cand, "change_type")
    assert hasattr(cand, "confidence_breakdown")
    assert hasattr(cand, "earliest_scene_id")
    assert "provenance" in res

# 13. Determinism
def test_determinism():
    np.random.seed(42)
    b_mask = np.zeros((100, 100), dtype=bool)
    b_mask[40:60, 40:60] = True
    before = generate_synthetic_scene("T1", "2023-06-01T10:00:00Z", base_veg=True, add_noise=False)
    after = generate_synthetic_scene("T2", "2023-06-15T10:00:00Z", base_veg=True, building_mask=b_mask, add_noise=False)
    
    res1 = run_synthetic_pair(before, after)
    res2 = run_synthetic_pair(before, after)
    
    assert res1["candidates"][0].confidence == res2["candidates"][0].confidence
    assert res1["candidates"][0].area_m2 == res2["candidates"][0].area_m2
