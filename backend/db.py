"""
AerialEye Database Layer
SQLite-based metadata registry using sqlite-utils.
All data is persisted to data/aerialeye.db.
"""
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlite_utils import Database

logger = logging.getLogger("aerialeye.db")

DB_PATH = Path(__file__).parent.parent / "data" / "aerialeye.db"


def get_db() -> Database:
    """Return (and auto-initialize) the singleton SQLite database."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = Database(str(DB_PATH))
    _ensure_schema(db)
    return db


def _ensure_schema(db: Database) -> None:
    """Create tables if they don't exist. Safe to call multiple times."""
    if "scenes" not in db.table_names():
        db["scenes"].create(
            {
                "asset_id": str,  # primary key, SHA256 of file content
                "scene_id": str,  # human-readable scene identifier
                "source": str,  # filename or 'demo'
                "sensor": str,  # e.g. 'Sentinel-2', 'YOLO-demo', 'unknown'
                "acquisition_time": str,  # ISO 8601 or estimated
                "crs": str,  # e.g. 'EPSG:4326' or 'pixel'
                "bbox": str,  # JSON [minx, miny, maxx, maxy]
                "resolution": float,  # meters/pixel, 0 if unknown
                "bands": str,  # JSON list, e.g. ['R','G','B']
                "cloud_cover": float,  # 0-1 estimated, -1 if unknown
                "quality_score": float,  # 0-1 computed (sharpness/brightness)
                "file_path": str,  # absolute path on disk
                "thumbnail_b64": str,  # base64 JPEG thumbnail (small)
                "ingestion_ts": float,  # unix timestamp
                "processing_version": str,
                "label": str,  # REAL | HEURISTIC | DEMO
                "tags": str,  # JSON list of free-form tags
            },
            pk="asset_id",
            ignore=True,
        )

    if "embeddings" not in db.table_names():
        db["embeddings"].create(
            {
                "embed_id": str,
                "asset_id": str,  # FK -> scenes.asset_id
                "tile_index": int,  # 0 for whole-image
                "model_name": str,
                "model_version": str,
                "faiss_index_pos": int,  # position in FAISS flat index
                "created_ts": float,
            },
            pk="embed_id",
            ignore=True,
        )

    if "change_candidates" not in db.table_names():
        db["change_candidates"].create(
            {
                "candidate_id": str,
                "scene_before": str,  # FK -> scenes.asset_id
                "scene_after": str,  # FK -> scenes.asset_id
                "change_score": float,  # 0-1
                "confidence": float,  # 0-1
                "change_type": str,  # 'construction' | 'clearance' | etc.
                "earliest_obs": str,  # asset_id of earliest supporting obs
                "change_map_b64": str,  # base64 JPEG of change overlay
                "quality_flags": str,  # JSON list of warnings
                "method": str,  # REAL | HEURISTIC | DEMO
                "processing_ts": float,
            },
            pk="candidate_id",
            ignore=True,
        )

    if "analyst_decisions" not in db.table_names():
        db["analyst_decisions"].create(
            {
                "decision_id": str,
                "candidate_id": str,  # FK -> change_candidates.candidate_id
                "status": str,  # NEW | CONFIRMED | REJECTED | NEEDS_REVIEW
                "notes": str,
                "analyst_id": str,  # session-level; no auth in this impl
                "timestamp": float,
                "evidence_snapshot": str,  # JSON snapshot at time of decision
            },
            pk="decision_id",
            ignore=True,
        )


# ---------------------------------------------------------------------------
# Scene helpers
# ---------------------------------------------------------------------------

def scene_exists(db: Database, asset_id: str) -> bool:
    return db["scenes"].get(asset_id) is not None if asset_id in [r["asset_id"] for r in db["scenes"].rows] else False


def insert_scene(db: Database, scene: Dict[str, Any]) -> None:
    db["scenes"].insert(scene, replace=True)


def get_scene(db: Database, asset_id: str) -> Optional[Dict[str, Any]]:
    try:
        return db["scenes"].get(asset_id)
    except Exception:
        return None


def list_scenes(
    db: Database,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    sensor: Optional[str] = None,
    min_quality: float = 0.0,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    where = ["quality_score >= :min_quality"]
    params: Dict[str, Any] = {"min_quality": min_quality}
    if date_from:
        where.append("acquisition_time >= :date_from")
        params["date_from"] = date_from
    if date_to:
        where.append("acquisition_time <= :date_to")
        params["date_to"] = date_to
    if sensor:
        where.append("sensor LIKE :sensor")
        params["sensor"] = f"%{sensor}%"
    
    where_clause = " AND ".join(where)
    return list(db["scenes"].rows_where(where_clause, params, order_by="acquisition_time DESC", limit=limit))


# ---------------------------------------------------------------------------
# Embedding helpers
# ---------------------------------------------------------------------------

def insert_embedding(db: Database, embed: Dict[str, Any]) -> None:
    db["embeddings"].insert(embed, replace=True)


def get_embedding_for_scene(db: Database, asset_id: str) -> Optional[Dict[str, Any]]:
    rows = list(db["embeddings"].rows_where("asset_id = ?", [asset_id], limit=1))
    return rows[0] if rows else None


def get_all_embeddings(db: Database) -> List[Dict[str, Any]]:
    return list(db["embeddings"].rows)


# ---------------------------------------------------------------------------
# Change candidate helpers
# ---------------------------------------------------------------------------

def insert_change_candidate(db: Database, candidate: Dict[str, Any]) -> None:
    db["change_candidates"].insert(candidate, replace=True)


def list_change_candidates(db: Database, limit: int = 50) -> List[Dict[str, Any]]:
    return list(db["change_candidates"].rows_where(order_by="processing_ts DESC", limit=limit))


def get_change_candidate(db: Database, candidate_id: str) -> Optional[Dict[str, Any]]:
    try:
        return db["change_candidates"].get(candidate_id)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Analyst decision helpers
# ---------------------------------------------------------------------------

def upsert_analyst_decision(db: Database, decision: Dict[str, Any]) -> None:
    # Remove old decision for same candidate (one active decision per candidate)
    db.execute("DELETE FROM analyst_decisions WHERE candidate_id = ?", [decision["candidate_id"]])
    db["analyst_decisions"].insert(decision)


def get_decision_for_candidate(db: Database, candidate_id: str) -> Optional[Dict[str, Any]]:
    rows = list(db["analyst_decisions"].rows_where("candidate_id = ?", [candidate_id], limit=1))
    return rows[0] if rows else None


def list_decisions(db: Database) -> List[Dict[str, Any]]:
    return list(db["analyst_decisions"].rows_where(order_by="timestamp DESC"))


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def get_index_stats(db: Database) -> Dict[str, Any]:
    scene_count = db.execute("SELECT COUNT(*) FROM scenes").fetchone()[0]
    embed_count = db.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
    candidate_count = db.execute("SELECT COUNT(*) FROM change_candidates").fetchone()[0]
    decision_count = db.execute("SELECT COUNT(*) FROM analyst_decisions").fetchone()[0]
    db_size_bytes = DB_PATH.stat().st_size if DB_PATH.exists() else 0
    return {
        "scene_count": scene_count,
        "embedding_count": embed_count,
        "change_candidate_count": candidate_count,
        "analyst_decision_count": decision_count,
        "db_size_bytes": db_size_bytes,
    }
