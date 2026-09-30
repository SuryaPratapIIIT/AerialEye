"""
AerialEye Review Service
Manages analyst decisions (Confirm / Reject / Needs Review) with audit trail.
All decisions are persisted in SQLite.
"""
import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from backend.db import (
    get_db,
    list_change_candidates,
    get_change_candidate,
    get_scene,
    upsert_analyst_decision,
    get_decision_for_candidate,
    list_decisions,
)

logger = logging.getLogger("aerialeye.review")

VALID_STATUSES = {"CONFIRMED", "REJECTED", "NEEDS_REVIEW", "NEW"}


def get_review_queue(
    status_filter: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Return the analyst review queue.
    Each item includes the change candidate + current decision status.
    """
    db = get_db()
    candidates = list_change_candidates(db, limit=limit)
    decisions_map = {d["candidate_id"]: d for d in list_decisions(db)}

    items = []
    for c in candidates:
        decision = decisions_map.get(c["candidate_id"])
        current_status = decision["status"] if decision else "NEW"

        if status_filter and current_status != status_filter:
            continue

        scene_before = get_scene(db, c["scene_before"])
        scene_after = get_scene(db, c["scene_after"])

        items.append({
            "candidate_id": c["candidate_id"],
            "status": current_status,
            "change_score": c["change_score"],
            "confidence": c["confidence"],
            "change_type": c["change_type"],
            "earliest_obs": c.get("earliest_obs", ""),
            "quality_flags": _parse_json(c.get("quality_flags", "[]")),
            "method": c.get("method", "HEURISTIC"),
            "label": c.get("method", "HEURISTIC"),
            "processing_ts": c["processing_ts"],
            "change_map_b64": c.get("change_map_b64", ""),
            "scene_before": _format_scene_ref(scene_before),
            "scene_after": _format_scene_ref(scene_after),
            "decision": {
                "notes": decision.get("notes", "") if decision else "",
                "analyst_id": decision.get("analyst_id", "") if decision else "",
                "timestamp": decision.get("timestamp", 0) if decision else 0,
            } if decision else None,
        })

    return {
        "items": items,
        "total": len(items),
        "status_filter": status_filter,
    }


def submit_decision(
    candidate_id: str,
    status: str,
    notes: str = "",
    analyst_id: str = "anonymous",
) -> Dict[str, Any]:
    """
    Persist an analyst decision for a change candidate.
    status must be one of: CONFIRMED | REJECTED | NEEDS_REVIEW
    """
    if status not in {"CONFIRMED", "REJECTED", "NEEDS_REVIEW"}:
        return {
            "success": False,
            "error": f"Invalid status '{status}'. Must be CONFIRMED, REJECTED, or NEEDS_REVIEW.",
        }

    db = get_db()
    candidate = get_change_candidate(db, candidate_id)
    if not candidate:
        return {"success": False, "error": f"Candidate '{candidate_id}' not found."}

    # Build evidence snapshot at time of decision
    scene_before = get_scene(db, candidate["scene_before"])
    scene_after = get_scene(db, candidate["scene_after"])
    evidence_snapshot = json.dumps({
        "candidate_id": candidate_id,
        "change_score": candidate["change_score"],
        "confidence": candidate["confidence"],
        "change_type": candidate["change_type"],
        "quality_flags": _parse_json(candidate.get("quality_flags", "[]")),
        "scene_before_asset_id": candidate["scene_before"],
        "scene_after_asset_id": candidate["scene_after"],
        "scene_before_source": scene_before.get("source", "") if scene_before else "",
        "scene_after_source": scene_after.get("source", "") if scene_after else "",
        "processing_version": "aerialeye-v1",
        "decision_model": "human",
    })

    decision = {
        "decision_id": str(uuid.uuid4()),
        "candidate_id": candidate_id,
        "status": status,
        "notes": notes,
        "analyst_id": analyst_id,
        "timestamp": time.time(),
        "evidence_snapshot": evidence_snapshot,
    }

    upsert_analyst_decision(db, decision)

    logger.info(
        "Decision recorded: candidate=%s status=%s analyst=%s",
        candidate_id, status, analyst_id,
    )

    return {
        "success": True,
        "decision_id": decision["decision_id"],
        "candidate_id": candidate_id,
        "status": status,
        "analyst_id": analyst_id,
        "timestamp": decision["timestamp"],
    }


def get_candidate_detail(candidate_id: str) -> Dict[str, Any]:
    """Return full detail for a single candidate including provenance."""
    db = get_db()
    candidate = get_change_candidate(db, candidate_id)
    if not candidate:
        return {"success": False, "error": "Candidate not found"}

    scene_before = get_scene(db, candidate["scene_before"])
    scene_after = get_scene(db, candidate["scene_after"])
    decision = get_decision_for_candidate(db, candidate_id)

    return {
        "success": True,
        "candidate_id": candidate_id,
        "change_score": candidate["change_score"],
        "confidence": candidate["confidence"],
        "change_type": candidate["change_type"],
        "earliest_obs": candidate.get("earliest_obs", ""),
        "quality_flags": _parse_json(candidate.get("quality_flags", "[]")),
        "change_map_b64": candidate.get("change_map_b64", ""),
        "method": candidate.get("method", "HEURISTIC"),
        "label": candidate.get("method", "HEURISTIC"),
        "provenance": {
            "processing_ts": candidate["processing_ts"],
            "processing_version": "aerialeye-v1",
            "change_detection_method": "OpenCV pixel-level diff + ORB alignment + histogram normalization",
            "model": "HEURISTIC — no deep learning model for change detection",
        },
        "scene_before": _format_scene_detail(scene_before),
        "scene_after": _format_scene_detail(scene_after),
        "decision": decision,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_scene_ref(scene: Optional[dict]) -> Optional[dict]:
    if not scene:
        return None
    return {
        "asset_id": scene.get("asset_id", ""),
        "scene_id": scene.get("scene_id", ""),
        "source": scene.get("source", ""),
        "sensor": scene.get("sensor", "unknown"),
        "acquisition_time": scene.get("acquisition_time", ""),
        "quality_score": scene.get("quality_score", 0),
        "cloud_cover": scene.get("cloud_cover", -1),
        "thumbnail_b64": scene.get("thumbnail_b64", ""),
        "label": scene.get("label", "DEMO"),
    }


def _format_scene_detail(scene: Optional[dict]) -> Optional[dict]:
    if not scene:
        return None
    ref = _format_scene_ref(scene)
    ref.update({
        "crs": scene.get("crs", ""),
        "bbox": _parse_json(scene.get("bbox", "[]")),
        "resolution": scene.get("resolution", 0),
        "bands": _parse_json(scene.get("bands", "[]")),
        "ingestion_ts": scene.get("ingestion_ts", 0),
        "processing_version": scene.get("processing_version", ""),
        "file_path": scene.get("file_path", ""),
    })
    return ref


def _parse_json(v: str) -> Any:
    try:
        return json.loads(v)
    except Exception:
        return []
