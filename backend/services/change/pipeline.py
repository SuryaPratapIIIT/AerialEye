"""
Change-detection pipeline orchestrator (REAL path) + in-memory array entrypoint for tests.
"""
from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np

from backend.services.change.config import load_change_config
from backend.services.change.provenance import Provenance
from backend.services.change.repository import ChangeRepository
from backend.services.change.selection import prefer_same_season_pair, select_scene_series
from backend.services.change.stages import (
    day_of_year,
    find_earliest_supporting_observation,
    stage_common_grid,
    stage_confidence,
    stage_extract_candidates,
    stage_indices,
    stage_quality_mask,
    stage_radiometry,
    stage_registration,
    stage_suppress,
    stage_type_candidates,
)
from backend.services.change.types import ChangeCandidate, SceneObservation

logger = logging.getLogger("aerialeye.change")

PROGRESS: Dict[str, Dict[str, Any]] = {}


def _set_progress(run_id: str, progress: float, message: str, status: str = "running") -> None:
    PROGRESS[run_id] = {"progress": progress, "message": message, "status": status}


def run_pair_from_observations(
    before: SceneObservation,
    after: SceneObservation,
    aoi_mask: Optional[np.ndarray],
    cfg: Optional[Dict[str, Any]] = None,
    *,
    series_indicators: Optional[List[Dict[str, Any]]] = None,
    persistence_counts: Optional[Dict[str, int]] = None,
    include_low_confidence: bool = False,
) -> Dict[str, Any]:
    """
    Core REAL pipeline on two SceneObservations with band arrays already loaded.
    Used by tests and by the DB-backed runner after chip mosaicking.
    """
    cfg = cfg or load_change_config()
    prov = Provenance(method_label="REAL", pipeline_version=cfg.get("pipeline_version", "change-v1"))

    if not before.georeferenced or not after.georeferenced:
        raise ValueError("REAL pipeline requires georeferenced observations; use HEURISTIC_LEGACY")

    same_sensor = (before.sensor or "").split("-")[0].lower() == (after.sensor or "").split("-")[0].lower()
    if not same_sensor and not cfg.get("allow_cross_sensor", False):
        return {
            "success": False,
            "error": "cross_sensor_pair_rejected",
            "provenance": prov.to_dict(),
            "candidates": [],
            "suppressed": [],
        }

    # Usable fraction gate
    min_u = float(cfg.get("min_usable_fraction", 0.6))
    if before.usable_fraction_aoi < min_u:
        return {
            "success": False,
            "error": f"before_unusable:{before.usable_fraction_aoi}",
            "provenance": prov.to_dict(),
            "candidates": [],
            "suppressed": [],
        }
    if after.usable_fraction_aoi < min_u:
        return {
            "success": False,
            "error": f"after_unusable:{after.usable_fraction_aoi}",
            "provenance": prov.to_dict(),
            "candidates": [],
            "suppressed": [],
        }

    doy_diff = abs(day_of_year(before.acquisition_datetime) - day_of_year(after.acquisition_datetime))
    doy_diff = min(doy_diff, 365 - doy_diff)

    grid = stage_common_grid(before, after, aoi_mask, cfg, prov)
    # Seed invalid from nan only for registration
    seed_inv = ~np.isfinite(grid.bands_before[next(iter(grid.bands_before))])
    grid, reg = stage_registration(grid, seed_inv, cfg, prov)
    quality = stage_quality_mask(grid, before.quality_source, after.quality_source, cfg, prov, before.sensor, after.sensor)

    if quality.usable_fraction < min_u:
        return {
            "success": False,
            "error": f"pair_usable_fraction={quality.usable_fraction:.3f}<{min_u}",
            "provenance": prov.to_dict(),
            "candidates": [],
            "suppressed": [],
            "registration": reg.__dict__,
            "usable_fraction": quality.usable_fraction,
        }

    radio = stage_radiometry(grid, quality.invalid, cfg, prov)
    # Apply norm
    grid.bands_after = radio.bands_after_norm
    indices = stage_indices(grid.bands_before, grid.bands_after, quality.invalid, cfg, prov, before.sensor, after.sensor)

    # Global illumination check: if almost all valid pixels shift uniformly with tiny structural change
    valid = ~quality.invalid
    if valid.sum() > 100:
        dbright = np.mean(
            [indices.delta.get("BSI", indices.delta["NDVI"])],
            axis=0,
        )
        # If score would be empty after normalisation for illumination-only, extraction handles it

    cands = stage_extract_candidates(
        indices, quality.invalid, grid, cfg, prov, before.scene_id, after.scene_id
    )
    cands = stage_type_candidates(cands, indices, quality.invalid, cfg, prov)

    # Default persistence: pair-only → 0 (single_observation) unless provided
    pcounts = persistence_counts or {c.candidate_id: 0 for c in cands}
    kept, suppressed = stage_suppress(
        cands, indices, quality, reg, cfg, prov,
        doy_diff=doy_diff, same_sensor=same_sensor, persistence_counts=pcounts,
    )
    kept = stage_confidence(kept, quality, reg, cfg, prov, doy_diff=doy_diff)

    # Move unclassified_low / low confidence to suppressed
    final_kept = []
    for c in kept:
        if c.rejected:
            suppressed.append(c)
            continue
        if c.confidence_label == "low" and not (
            include_low_confidence or cfg.get("return_low_confidence")
        ):
            c.rejection_reason = c.rejection_reason or "low_confidence"
            c.suppression_reasons = list(c.suppression_reasons) + ["low_confidence"]
            suppressed.append(c)
            continue
        final_kept.append(c)

    # Earliest observation
    for c in final_kept:
        if series_indicators:
            # Filter series entries for this candidate if keyed; else shared series
            find_earliest_supporting_observation(c, series_indicators, cfg, prov)
        else:
            c.earliest_scene_id = after.scene_id
            c.earliest_date = after.acquisition_datetime
            c.last_clear_before_date = before.acquisition_datetime
            c.low_temporal_support = True
            find_earliest_supporting_observation(
                c,
                [
                    {
                        "scene_id": before.scene_id,
                        "date": before.acquisition_datetime,
                        "usable_fraction": before.usable_fraction_aoi,
                        "indicator": 0.0,
                    },
                    {
                        "scene_id": after.scene_id,
                        "date": after.acquisition_datetime,
                        "usable_fraction": after.usable_fraction_aoi,
                        "indicator": 1.0,
                    },
                ],
                cfg,
                prov,
            )

    return {
        "success": True,
        "candidates": final_kept,
        "suppressed": suppressed,
        "provenance": prov.to_dict(),
        "registration": reg.__dict__,
        "radiometry": {"gains": radio.gains, "offsets": radio.offsets, "stable": radio.stable_pixel_count},
        "usable_fraction": quality.usable_fraction,
        "method_label": "REAL",
        "grid": grid,
        "indices": indices,
        "quality": quality,
    }


def render_candidate_thumbs(
    cand: ChangeCandidate,
    grid,
    out_dir: Path,
) -> ChangeCandidate:
    """Save before/after/overlay PNG crops."""
    out_dir.mkdir(parents=True, exist_ok=True)
    if cand.bbox_px is None or cand.mask_label is None:
        return cand
    r0, r1, c0, c1 = cand.bbox_px
    pad = 5
    r0, c0 = max(0, r0 - pad), max(0, c0 - pad)
    r1, c1 = min(grid.height, r1 + pad), min(grid.width, c1 + pad)

    def rgb_from(bands):
        r = bands.get("B04", bands.get("B03"))
        g = bands.get("B03", r)
        b = bands.get("B02", g)
        stack = np.stack([r[r0:r1, c0:c1], g[r0:r1, c0:c1], b[r0:r1, c0:c1]], axis=-1)
        # fixed stretch
        x = np.clip(stack / 0.3, 0, 1)
        return (x * 255).astype(np.uint8)

    before_rgb = rgb_from(grid.bands_before)
    after_rgb = rgb_from(grid.bands_after)
    overlay = after_rgb.copy()
    mask = cand.mask_label[r0:r1, c0:c1]
    if mask.shape[:2] == overlay.shape[:2]:
        overlay[mask] = [255, 40, 40]

    bid = cand.candidate_id[:8]
    bp = out_dir / f"{bid}_before.png"
    ap = out_dir / f"{bid}_after.png"
    op = out_dir / f"{bid}_overlay.png"
    cv2.imwrite(str(bp), cv2.cvtColor(before_rgb, cv2.COLOR_RGB2BGR))
    cv2.imwrite(str(ap), cv2.cvtColor(after_rgb, cv2.COLOR_RGB2BGR))
    cv2.imwrite(str(op), cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR))
    cand.before_thumb_path = str(bp)
    cand.after_thumb_path = str(ap)
    cand.overlay_path = str(op)
    return cand


def candidate_to_row(cand: ChangeCandidate, run_id: str) -> Dict[str, Any]:
    return {
        "candidate_id": cand.candidate_id,
        "run_id": run_id,
        "geometry_geojson": json.dumps(cand.geometry_geojson),
        "area_m2": cand.area_m2,
        "change_type": cand.change_type,
        "direction": cand.direction,
        "confidence": cand.confidence,
        "confidence_label": cand.confidence_label,
        "confidence_breakdown_json": json.dumps(cand.confidence_breakdown),
        "evidence_json": json.dumps(cand.evidence),
        "before_scene_id": cand.before_scene_id,
        "after_scene_id": cand.after_scene_id,
        "earliest_scene_id": cand.earliest_scene_id,
        "earliest_date": cand.earliest_date,
        "last_clear_before_date": cand.last_clear_before_date,
        "detection_window_days": cand.detection_window_days,
        "usable_fraction": cand.usable_fraction,
        "persistence_count": cand.persistence_count,
        "suppression_reasons_json": json.dumps(cand.suppression_reasons),
        "method_label": cand.method_label,
        "review_status": "pending",
        "before_thumb_path": cand.before_thumb_path,
        "after_thumb_path": cand.after_thumb_path,
        "overlay_path": cand.overlay_path,
        "low_temporal_support": cand.low_temporal_support,
        "skipped_scenes_json": json.dumps(cand.skipped_scenes),
    }


def persist_results(
    run_id: str,
    result: Dict[str, Any],
    out_dir: Optional[Path] = None,
    repo: Optional[ChangeRepository] = None,
) -> Dict[str, Any]:
    repo = repo or ChangeRepository()
    out_dir = out_dir or Path("data/change_runs") / run_id
    grid = result.get("grid")
    kept_rows = []
    for c in result.get("candidates") or []:
        if grid is not None:
            render_candidate_thumbs(c, grid, out_dir)
        row = candidate_to_row(c, run_id)
        repo.insert_candidate(row, suppressed=False)
        kept_rows.append(row)
    for c in result.get("suppressed") or []:
        row = candidate_to_row(c, run_id)
        row["rejection_reason"] = c.rejection_reason or (
            c.suppression_reasons[-1] if c.suppression_reasons else "suppressed"
        )
        # suppressed table may not have all columns
        slim = {k: row[k] for k in row if k not in ("before_thumb_path", "after_thumb_path", "overlay_path", "low_temporal_support", "skipped_scenes_json")}
        slim["rejection_reason"] = row["rejection_reason"]
        try:
            repo.insert_candidate(slim, suppressed=True)
        except Exception:
            repo.insert_candidate(row, suppressed=True)

    summary = {
        "n_candidates": len(result.get("candidates") or []),
        "n_suppressed": len(result.get("suppressed") or []),
        "usable_fraction": result.get("usable_fraction"),
        "method_label": result.get("method_label"),
    }
    repo.update_run(
        run_id,
        status="complete",
        progress=1.0,
        message="complete",
        provenance_json=json.dumps(result.get("provenance") or {}),
        summary_json=json.dumps(summary),
    )
    return summary


def execute_change_run(
    run_id: str,
    *,
    aoi: Any,
    date_from: str,
    date_to: str,
    mode: str = "pair",
    before_scene_id: Optional[str] = None,
    after_scene_id: Optional[str] = None,
    sensor: Optional[str] = None,
    include_low_confidence: bool = False,
    band_loader: Optional[Callable[[str], Dict[str, np.ndarray]]] = None,
    cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Full DB-backed run. `band_loader(scene_id) -> dict of logical bands` must be provided
    for REAL data; tests call `run_pair_from_observations` directly.
    """
    cfg = cfg or load_change_config()
    repo = ChangeRepository()
    _set_progress(run_id, 0.05, "selecting scenes")
    repo.update_run(run_id, status="running", progress=0.05, message="selecting scenes")

    try:
        scenes, unusable = select_scene_series(aoi, date_from, date_to, sensor=sensor, cfg=cfg)
        _set_progress(run_id, 0.15, f"scenes={len(scenes)} unusable={len(unusable)}")

        if mode == "pair":
            if before_scene_id and after_scene_id:
                before = next((s for s in scenes if s.scene_id == before_scene_id), None)
                after = next((s for s in scenes if s.scene_id == after_scene_id), None)
                # Also allow loading unusable-filtered scenes by id from repo
                if before is None or after is None:
                    from backend.repository import GeoRepository
                    geo = GeoRepository()
                    for sid, slot in ((before_scene_id, "before"), (after_scene_id, "after")):
                        row = geo.get_scene(sid)
                        if not row:
                            raise ValueError(f"scene not found: {sid}")
                        obs = SceneObservation(
                            scene_id=sid,
                            sensor=row.get("sensor") or "Sentinel-2",
                            acquisition_datetime=row.get("acquisition_datetime") or "",
                            georeferenced=bool(row.get("georeferenced")),
                            source_type=row.get("source_type") or "REAL",
                            minlon=row["minlon"], minlat=row["minlat"],
                            maxlon=row["maxlon"], maxlat=row["maxlat"],
                            usable_fraction_aoi=0.9,
                            quality_source="scl" if row.get("cloud_mask_available") else "none",
                            resolution_m=float(row.get("resolution_m") or 10.0),
                        )
                        if slot == "before":
                            before = obs
                        else:
                            after = obs
            else:
                pair = prefer_same_season_pair(scenes, cfg)
                if not pair:
                    raise ValueError("Need at least 2 usable scenes for pair mode")
                before, after = pair

            if band_loader is None:
                raise ValueError("band_loader required for DB-backed REAL runs")
            before.bands = band_loader(before.scene_id)
            after.bands = band_loader(after.scene_id)
            # Simple full-true AOI mask matching band shape
            ref = next(iter(before.bands.values()))
            aoi_mask = np.ones(ref.shape[:2], dtype=bool)

            _set_progress(run_id, 0.3, "running pair pipeline")
            result = run_pair_from_observations(
                before, after, aoi_mask, cfg,
                include_low_confidence=include_low_confidence,
            )
            if not result.get("success"):
                repo.update_run(
                    run_id, status="failed", progress=1.0,
                    message=result.get("error", "failed"),
                    error=result.get("error", ""),
                    provenance_json=json.dumps(result.get("provenance") or {}),
                )
                _set_progress(run_id, 1.0, result.get("error", "failed"), "failed")
                return result

            summary = persist_results(run_id, result)
            summary["unusable_scenes"] = unusable
            summary["before_scene_id"] = before.scene_id
            summary["after_scene_id"] = after.scene_id
            _set_progress(run_id, 1.0, "complete", "complete")
            return {"success": True, "run_id": run_id, **summary, "provenance": result.get("provenance")}

        # Series mode: consecutive same-season preferred pairs
        _set_progress(run_id, 0.2, "series mode")
        all_kept = []
        all_supp = []
        prov_all = []
        if band_loader is None:
            raise ValueError("band_loader required")
        for i in range(len(scenes) - 1):
            b, a = scenes[i], scenes[i + 1]
            b.bands = band_loader(b.scene_id)
            a.bands = band_loader(a.scene_id)
            ref = next(iter(b.bands.values()))
            result = run_pair_from_observations(
                b, a, np.ones(ref.shape[:2], dtype=bool), cfg,
                include_low_confidence=include_low_confidence,
            )
            if result.get("success"):
                all_kept.extend(result["candidates"])
                all_supp.extend(result["suppressed"])
                prov_all.append(result["provenance"])
            _set_progress(run_id, 0.2 + 0.7 * (i + 1) / max(len(scenes) - 1, 1), f"pair {i+1}")

        merged = {
            "success": True,
            "candidates": all_kept,
            "suppressed": all_supp,
            "provenance": {"pairs": prov_all},
            "method_label": "REAL",
            "usable_fraction": None,
            "grid": None,
        }
        # render skipped without grid
        summary = persist_results(run_id, merged)
        summary["unusable_scenes"] = unusable
        _set_progress(run_id, 1.0, "complete", "complete")
        return {"success": True, "run_id": run_id, **summary}

    except Exception as exc:
        logger.exception("change run failed")
        repo.update_run(run_id, status="failed", progress=1.0, message=str(exc), error=str(exc))
        _set_progress(run_id, 1.0, str(exc), "failed")
        return {"success": False, "run_id": run_id, "error": str(exc)}
