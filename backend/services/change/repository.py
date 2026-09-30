"""
Change-detection persistence: change_runs, change_run_candidates, suppressed_candidates.
Legacy change_candidates (scene-level HEURISTIC) remains in backend.db.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, List, Optional

from backend.db import get_db


def ensure_change_schema() -> None:
    db = get_db()

    if "change_runs" not in db.table_names():
        db["change_runs"].create(
            {
                "run_id": str,
                "created_at": float,
                "aoi_geojson": str,
                "date_from": str,
                "date_to": str,
                "mode": str,  # pair | series
                "params_json": str,
                "pipeline_version": str,
                "status": str,  # pending | running | complete | failed
                "progress": float,
                "message": str,
                "provenance_json": str,
                "summary_json": str,
                "error": str,
            },
            pk="run_id",
            ignore=True,
        )

    if "change_run_candidates" not in db.table_names():
        db["change_run_candidates"].create(
            {
                "candidate_id": str,
                "run_id": str,
                "geometry_geojson": str,
                "area_m2": float,
                "change_type": str,
                "direction": str,
                "confidence": float,
                "confidence_label": str,
                "confidence_breakdown_json": str,
                "evidence_json": str,
                "before_scene_id": str,
                "after_scene_id": str,
                "earliest_scene_id": str,
                "earliest_date": str,
                "last_clear_before_date": str,
                "detection_window_days": float,
                "usable_fraction": float,
                "persistence_count": int,
                "suppression_reasons_json": str,
                "method_label": str,
                "review_status": str,
                "before_thumb_path": str,
                "after_thumb_path": str,
                "overlay_path": str,
                "low_temporal_support": bool,
                "skipped_scenes_json": str,
            },
            pk="candidate_id",
            ignore=True,
        )
        db["change_run_candidates"].create_index(["run_id"])
        db["change_run_candidates"].create_index(["change_type"])
        db["change_run_candidates"].create_index(["confidence_label"])

    if "suppressed_candidates" not in db.table_names():
        db["suppressed_candidates"].create(
            {
                "candidate_id": str,
                "run_id": str,
                "geometry_geojson": str,
                "area_m2": float,
                "change_type": str,
                "direction": str,
                "confidence": float,
                "confidence_label": str,
                "confidence_breakdown_json": str,
                "evidence_json": str,
                "before_scene_id": str,
                "after_scene_id": str,
                "earliest_scene_id": str,
                "earliest_date": str,
                "last_clear_before_date": str,
                "detection_window_days": float,
                "usable_fraction": float,
                "persistence_count": int,
                "suppression_reasons_json": str,
                "rejection_reason": str,
                "method_label": str,
                "review_status": str,
            },
            pk="candidate_id",
            ignore=True,
        )
        db["suppressed_candidates"].create_index(["run_id"])


class ChangeRepository:
    def __init__(self):
        ensure_change_schema()
        self.db = get_db()

    def create_run(self, payload: Dict[str, Any]) -> str:
        run_id = payload.get("run_id") or str(uuid.uuid4())
        row = {
            "run_id": run_id,
            "created_at": time.time(),
            "aoi_geojson": json.dumps(payload.get("aoi") or {}),
            "date_from": payload.get("date_from") or "",
            "date_to": payload.get("date_to") or "",
            "mode": payload.get("mode") or "pair",
            "params_json": json.dumps(payload.get("params") or {}),
            "pipeline_version": payload.get("pipeline_version") or "change-v1",
            "status": "pending",
            "progress": 0.0,
            "message": "",
            "provenance_json": "{}",
            "summary_json": "{}",
            "error": "",
        }
        self.db["change_runs"].insert(row, replace=True)
        return run_id

    def update_run(self, run_id: str, **fields: Any) -> None:
        allowed = {
            "status", "progress", "message", "provenance_json",
            "summary_json", "error",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        sets = ", ".join(f"{k} = ?" for k in updates)
        self.db.execute(
            f"UPDATE change_runs SET {sets} WHERE run_id = ?",
            [*updates.values(), run_id],
        )

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        try:
            return dict(self.db["change_runs"].get(run_id))
        except Exception:
            return None

    def insert_candidate(self, row: Dict[str, Any], suppressed: bool = False) -> None:
        table = "suppressed_candidates" if suppressed else "change_run_candidates"
        if "review_status" not in row:
            row["review_status"] = "pending"
        self.db[table].insert(row, replace=True)

    def list_candidates(
        self,
        run_id: str,
        *,
        change_type: Optional[str] = None,
        confidence_label: Optional[str] = None,
        review_status: Optional[str] = None,
        suppressed: bool = False,
    ) -> List[Dict[str, Any]]:
        table = "suppressed_candidates" if suppressed else "change_run_candidates"
        clauses = ["run_id = ?"]
        params: List[Any] = [run_id]
        if change_type:
            clauses.append("change_type = ?")
            params.append(change_type)
        if confidence_label:
            clauses.append("confidence_label = ?")
            params.append(confidence_label)
        if review_status and not suppressed:
            clauses.append("review_status = ?")
            params.append(review_status)
        where = " AND ".join(clauses)
        order = "confidence DESC" if not suppressed else "confidence DESC"
        return [dict(r) for r in self.db[table].rows_where(where, params, order_by=order)]

    def get_candidate(self, candidate_id: str) -> Optional[Dict[str, Any]]:
        for table in ("change_run_candidates", "suppressed_candidates"):
            try:
                row = self.db[table].get(candidate_id)
                if row:
                    d = dict(row)
                    d["_table"] = table
                    return d
            except Exception:
                continue
        return None
