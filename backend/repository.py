"""
AerialEye GeoRepository — Prompt 1 schema + Prompt 2 query/embedding helpers.
All tile/scene DB access for the geospatial pipeline goes through this layer.
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from backend.db import get_db


def ensure_geo_schema() -> None:
    db = get_db()

    if "geo_scenes" not in db.table_names():
        db["geo_scenes"].create(
            {
                "scene_id": str,
                "sensor": str,
                "product_level": str,
                "acquisition_datetime": str,
                "date_source": str,
                "crs": str,
                "transform_json": str,
                "width": int,
                "height": int,
                "resolution_m": float,
                "bounds_native_json": str,
                "minlon": float,
                "minlat": float,
                "maxlon": float,
                "maxlat": float,
                "band_names_json": str,
                "nodata": float,
                "georeferenced": bool,
                "cloud_mask_available": bool,
                "ingested_at": float,
                "pipeline_version": str,
                "source_type": str,  # REAL | LEGACY | DEMO
            },
            pk="scene_id",
            ignore=True,
        )
        db["geo_scenes"].create_index(["acquisition_datetime"])
        db["geo_scenes"].create_index(["sensor"])
        db["geo_scenes"].create_index(["source_type"])

    # Migrate source_type on existing DBs
    if "geo_scenes" in db.table_names():
        col_names = [c.name for c in db["geo_scenes"].columns]
        if "source_type" not in col_names:
            db["geo_scenes"].add_column("source_type", str)
        # Backfill NULL / empty source_type
        db.execute(
            "UPDATE geo_scenes SET source_type = 'REAL' "
            "WHERE (source_type IS NULL OR source_type = '') AND georeferenced = 1"
        )
        db.execute(
            "UPDATE geo_scenes SET source_type = 'LEGACY' "
            "WHERE (source_type IS NULL OR source_type = '') AND (georeferenced = 0 OR georeferenced IS NULL)"
        )
        # Heuristic: site01_*.jpg style demo files
        db.execute(
            "UPDATE geo_scenes SET source_type = 'DEMO' "
            "WHERE source_type != 'DEMO' AND ("
            "  scene_id LIKE '%site0%' OR scene_id LIKE '%demo%' "
            "  OR LOWER(scene_id) LIKE '%whatsapp%'"
            ")"
        )
        # Prefer DEMO for non-georef scenes whose primary path looks like demo tiles
        try:
            db.execute(
                """
                UPDATE geo_scenes SET source_type = 'DEMO'
                WHERE georeferenced = 0 AND source_type = 'LEGACY'
                  AND scene_id IN (
                    SELECT DISTINCT sf.scene_id FROM scene_files sf
                    WHERE LOWER(sf.path) LIKE '%demo%'
                       OR LOWER(sf.path) LIKE '%site0%'
                  )
                """
            )
        except Exception:
            pass

    if "tiles" not in db.table_names():
        db["tiles"].create(
            {
                "tile_id": int,
                "scene_id": str,
                "row": int,
                "col": int,
                "window_json": str,
                "footprint_wkt": str,
                "minlon": float,
                "minlat": float,
                "maxlon": float,
                "maxlat": float,
                "centroid_lon": float,
                "centroid_lat": float,
                "nodata_fraction": float,
                "cloud_fraction": float,
                "shadow_fraction": float,
                "snow_fraction": float,
                "valid_fraction": float,
                "quality_source": str,
                "preview_path": str,
                "chip_path": str,
                "mask_path": str,
                "embedded": bool,
                "superseded": bool,
            },
            pk="tile_id",
            ignore=True,
        )
        db["tiles"].add_foreign_key("scene_id", "geo_scenes", "scene_id")

        conn = db.conn
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS tiles_rtree USING rtree(
                id, minlon, maxlon, minlat, maxlat
            )
            """
        )
        cursor.execute(
            """
            CREATE TRIGGER IF NOT EXISTS tiles_rtree_insert AFTER INSERT ON tiles
            BEGIN
                INSERT INTO tiles_rtree(id, minlon, maxlon, minlat, maxlat)
                VALUES (new.tile_id, new.minlon, new.maxlon, new.minlat, new.maxlat);
            END;
            """
        )
        cursor.execute(
            """
            CREATE TRIGGER IF NOT EXISTS tiles_rtree_delete AFTER DELETE ON tiles
            BEGIN
                DELETE FROM tiles_rtree WHERE id = old.tile_id;
            END;
            """
        )
        cursor.execute(
            """
            CREATE TRIGGER IF NOT EXISTS tiles_rtree_update AFTER UPDATE ON tiles
            BEGIN
                DELETE FROM tiles_rtree WHERE id = old.tile_id;
                INSERT INTO tiles_rtree(id, minlon, maxlon, minlat, maxlat)
                VALUES (new.tile_id, new.minlon, new.maxlon, new.minlat, new.maxlat);
            END;
            """
        )
        conn.commit()

    # Migrate superseded column
    if "tiles" in db.table_names():
        tile_cols = [c.name for c in db["tiles"].columns]
        if "superseded" not in tile_cols:
            db["tiles"].add_column("superseded", bool)
            db.execute("UPDATE tiles SET superseded = 0 WHERE superseded IS NULL")

        # Ensure rtree exists even if tiles table pre-existed without it
        conn = db.conn
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS tiles_rtree USING rtree(
                id, minlon, maxlon, minlat, maxlat
            )
            """
        )
        cursor.execute(
            """
            CREATE TRIGGER IF NOT EXISTS tiles_rtree_insert AFTER INSERT ON tiles
            BEGIN
                INSERT INTO tiles_rtree(id, minlon, maxlon, minlat, maxlat)
                VALUES (new.tile_id, new.minlon, new.maxlon, new.minlat, new.maxlat);
            END;
            """
        )
        cursor.execute(
            """
            CREATE TRIGGER IF NOT EXISTS tiles_rtree_delete AFTER DELETE ON tiles
            BEGIN
                DELETE FROM tiles_rtree WHERE id = old.tile_id;
            END;
            """
        )
        cursor.execute(
            """
            CREATE TRIGGER IF NOT EXISTS tiles_rtree_update AFTER UPDATE ON tiles
            BEGIN
                DELETE FROM tiles_rtree WHERE id = old.tile_id;
                INSERT INTO tiles_rtree(id, minlon, maxlon, minlat, maxlat)
                VALUES (new.tile_id, new.minlon, new.maxlon, new.minlat, new.maxlat);
            END;
            """
        )
        conn.commit()

    if "tile_embeddings" not in db.table_names():
        db["tile_embeddings"].create(
            {
                "tile_id": int,
                "model_name": str,
                "model_version": str,
                "embedded_at": float,
            },
            pk=("tile_id", "model_name"),
            ignore=True,
        )
        try:
            db["tile_embeddings"].add_foreign_key("tile_id", "tiles", "tile_id")
        except Exception:
            pass

    if "scene_files" not in db.table_names():
        db["scene_files"].create(
            {
                "id": str,
                "scene_id": str,
                "path": str,
                "band_role": str,
                "sha256": str,
                "size_bytes": int,
            },
            pk="id",
            ignore=True,
        )
        try:
            db["scene_files"].add_foreign_key("scene_id", "geo_scenes", "scene_id")
        except Exception:
            pass

    if "ingestion_log" not in db.table_names():
        db["ingestion_log"].create(
            {
                "id": str,
                "scene_id": str,
                "started_at": float,
                "finished_at": float,
                "status": str,
                "tiles_created": int,
                "warnings_json": str,
                "error": str,
            },
            pk="id",
            ignore=True,
        )

    if "embed_skip_log" not in db.table_names():
        db["embed_skip_log"].create(
            {
                "id": str,
                "tile_id": int,
                "model_name": str,
                "reason": str,
                "skipped_at": float,
            },
            pk="id",
            ignore=True,
        )


class GeoRepository:
    def __init__(self):
        ensure_geo_schema()
        self.db = get_db()

    # ------------------------------------------------------------------
    # Scene / tile basic CRUD
    # ------------------------------------------------------------------

    def get_scene(self, scene_id: str) -> Optional[Dict[str, Any]]:
        try:
            return dict(self.db["geo_scenes"].get(scene_id))
        except Exception:
            return None

    def get_scene_files(self, scene_id: str) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.db["scene_files"].rows_where("scene_id = ?", [scene_id])]

    def get_ingestion_log(self, scene_id: str) -> Optional[Dict[str, Any]]:
        rows = list(
            self.db["ingestion_log"].rows_where(
                "scene_id = ?", [scene_id], order_by="started_at DESC", limit=1
            )
        )
        return dict(rows[0]) if rows else None

    def insert_scene(self, scene: Dict[str, Any]) -> None:
        if "source_type" not in scene or not scene["source_type"]:
            scene = dict(scene)
            if scene.get("georeferenced"):
                scene["source_type"] = "REAL"
            else:
                scene["source_type"] = "LEGACY"
        self.db["geo_scenes"].insert(scene, replace=True)

    def insert_scene_files(self, files: List[Dict[str, Any]]) -> None:
        if files:
            self.db["scene_files"].insert_all(files, replace=True)

    def insert_tiles(self, tiles: List[Dict[str, Any]]) -> None:
        if not tiles:
            return
        for t in tiles:
            if "superseded" not in t:
                t["superseded"] = False
        self.db["tiles"].insert_all(tiles, replace=True)

    def log_ingestion(self, log_entry: Dict[str, Any]) -> None:
        self.db["ingestion_log"].insert(log_entry, replace=True)

    def delete_scene_tiles(self, scene_id: str) -> None:
        """Hard-delete tiles for a scene (legacy). Prefer mark_scene_tiles_superseded."""
        self.db.execute("DELETE FROM tiles WHERE scene_id = ?", [scene_id])

    def mark_scene_tiles_superseded(self, scene_id: str) -> int:
        """Soft-delete tiles so FAISS IDs remain but search excludes them."""
        cur = self.db.execute(
            "UPDATE tiles SET superseded = 1 WHERE scene_id = ? AND (superseded IS NULL OR superseded = 0)",
            [scene_id],
        )
        return cur.rowcount if cur is not None else 0

    def get_tile(self, tile_id: int) -> Optional[Dict[str, Any]]:
        try:
            row = self.db["tiles"].get(tile_id)
            return dict(row) if row else None
        except Exception:
            return None

    def get_tiles_for_scene(self, scene_id: str, include_superseded: bool = False) -> List[Dict[str, Any]]:
        if include_superseded:
            rows = self.db["tiles"].rows_where("scene_id = ?", [scene_id])
        else:
            rows = self.db["tiles"].rows_where(
                "scene_id = ? AND (superseded IS NULL OR superseded = 0)", [scene_id]
            )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------

    def get_embedded_tile_ids(self, model_name: str) -> List[int]:
        rows = self.db["tile_embeddings"].rows_where("model_name = ?", [model_name])
        return [int(r["tile_id"]) for r in rows]

    def has_tile_embedding(self, tile_id: int, model_name: str) -> bool:
        rows = list(
            self.db["tile_embeddings"].rows_where(
                "tile_id = ? AND model_name = ?", [tile_id, model_name], limit=1
            )
        )
        return len(rows) > 0

    def insert_tile_embeddings(self, rows: List[Dict[str, Any]]) -> None:
        if rows:
            self.db["tile_embeddings"].insert_all(rows, replace=True)

    def mark_tiles_embedded(self, tile_ids: Sequence[int]) -> None:
        if not tile_ids:
            return
        placeholders = ",".join("?" * len(tile_ids))
        self.db.execute(
            f"UPDATE tiles SET embedded = 1 WHERE tile_id IN ({placeholders})",
            list(tile_ids),
        )

    def log_embed_skip(self, tile_id: int, model_name: str, reason: str) -> None:
        import uuid

        self.db["embed_skip_log"].insert(
            {
                "id": str(uuid.uuid4()),
                "tile_id": int(tile_id),
                "model_name": model_name,
                "reason": reason,
                "skipped_at": time.time(),
            },
            replace=True,
        )

    def count_tiles_pending_embed(
        self,
        model_name: str,
        min_valid_fraction: float = 0.5,
        exclude_cloudy_above: float = 0.8,
    ) -> int:
        sql = """
            SELECT COUNT(*) AS c FROM tiles t
            WHERE (t.superseded IS NULL OR t.superseded = 0)
              AND t.tile_id NOT IN (
                SELECT tile_id FROM tile_embeddings WHERE model_name = ?
              )
              AND COALESCE(t.valid_fraction, 1.0) >= ?
              AND (
                t.cloud_fraction IS NULL
                OR t.cloud_fraction <= ?
              )
        """
        row = list(self.db.query(sql, [model_name, min_valid_fraction, exclude_cloudy_above]))[0]
        return int(row["c"])

    def count_tiles_indexed(self, model_name: str) -> int:
        rows = list(
            self.db.query(
                "SELECT COUNT(*) AS c FROM tile_embeddings WHERE model_name = ?",
                [model_name],
            )
        )
        return int(rows[0]["c"]) if rows else 0

    def last_embed_time(self, model_name: str) -> Optional[float]:
        rows = list(
            self.db.query(
                "SELECT MAX(embedded_at) AS m FROM tile_embeddings WHERE model_name = ?",
                [model_name],
            )
        )
        if rows and rows[0]["m"] is not None:
            return float(rows[0]["m"])
        return None

    def select_pending_tiles(
        self,
        model_name: str,
        limit: int = 64,
        min_valid_fraction: float = 0.5,
        exclude_cloudy_above: float = 0.8,
    ) -> List[Dict[str, Any]]:
        """Tiles eligible for embedding that lack a tile_embeddings row for model."""
        sql = """
            SELECT t.*, s.sensor, s.source_type, s.georeferenced, s.band_names_json
            FROM tiles t
            JOIN geo_scenes s ON s.scene_id = t.scene_id
            WHERE (t.superseded IS NULL OR t.superseded = 0)
              AND t.tile_id NOT IN (
                SELECT tile_id FROM tile_embeddings WHERE model_name = ?
              )
            ORDER BY t.tile_id
            LIMIT ?
        """
        # Filter cloudy / low-valid in Python so we can log skip reasons distinctly
        rows = [dict(r) for r in self.db.query(sql, [model_name, max(limit * 4, limit)])]
        out: List[Dict[str, Any]] = []
        for r in rows:
            vf = r.get("valid_fraction")
            if vf is not None and float(vf) < min_valid_fraction:
                self.log_embed_skip(int(r["tile_id"]), model_name, f"valid_fraction={vf}<{min_valid_fraction}")
                continue
            cf = r.get("cloud_fraction")
            if cf is not None and float(cf) > exclude_cloudy_above:
                self.log_embed_skip(
                    int(r["tile_id"]), model_name, f"cloud_fraction={cf}>{exclude_cloudy_above}"
                )
                continue
            out.append(r)
            if len(out) >= limit:
                break
        return out

    def delete_tile_embeddings_for_tiles(self, tile_ids: Sequence[int], model_name: Optional[str] = None) -> None:
        if not tile_ids:
            return
        placeholders = ",".join("?" * len(tile_ids))
        if model_name:
            self.db.execute(
                f"DELETE FROM tile_embeddings WHERE model_name = ? AND tile_id IN ({placeholders})",
                [model_name, *tile_ids],
            )
        else:
            self.db.execute(
                f"DELETE FROM tile_embeddings WHERE tile_id IN ({placeholders})",
                list(tile_ids),
            )

    def delete_demo_scenes(self) -> Tuple[List[int], List[str]]:
        """Remove DEMO scenes and their tiles. Returns (tile_ids, scene_ids)."""
        scenes = [dict(r) for r in self.db["geo_scenes"].rows_where("source_type = ?", ["DEMO"])]
        scene_ids = [s["scene_id"] for s in scenes]
        tile_ids: List[int] = []
        for sid in scene_ids:
            tiles = self.get_tiles_for_scene(sid, include_superseded=True)
            tile_ids.extend(int(t["tile_id"]) for t in tiles)
            self.db.execute("DELETE FROM tile_embeddings WHERE tile_id IN "
                            "(SELECT tile_id FROM tiles WHERE scene_id = ?)", [sid])
            self.db.execute("DELETE FROM tiles WHERE scene_id = ?", [sid])
            self.db.execute("DELETE FROM scene_files WHERE scene_id = ?", [sid])
            self.db.execute("DELETE FROM ingestion_log WHERE scene_id = ?", [sid])
            self.db.execute("DELETE FROM geo_scenes WHERE scene_id = ?", [sid])
        return tile_ids, scene_ids

    # ------------------------------------------------------------------
    # Search candidate filtering
    # ------------------------------------------------------------------

    def filter_candidate_tile_ids(
        self,
        *,
        bbox: Optional[Tuple[float, float, float, float]] = None,
        aoi_geojson: Optional[Dict[str, Any]] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        sensors: Optional[List[str]] = None,
        max_cloud_fraction: Optional[float] = None,
        min_valid_fraction: Optional[float] = None,
        scene_ids: Optional[List[str]] = None,
        georeferenced_only: bool = False,
        include_legacy: bool = False,
        include_demo: bool = False,
        null_cloud_include: bool = True,
        exclude_superseded: bool = True,
        model_name: Optional[str] = None,
        exclude_tile_id: Optional[int] = None,
    ) -> List[int]:
        """
        Return tile_ids matching metadata/spatial filters.
        Uses tiles_rtree when a bbox is provided.
        """
        clauses: List[str] = ["1=1"]
        params: List[Any] = []

        if exclude_superseded:
            clauses.append("(t.superseded IS NULL OR t.superseded = 0)")

        # Provenance / source_type
        allowed = ["'REAL'"]
        if include_legacy:
            allowed.append("'LEGACY'")
        if include_demo:
            allowed.append("'DEMO'")
        clauses.append(f"COALESCE(s.source_type, 'REAL') IN ({','.join(allowed)})")

        if georeferenced_only:
            clauses.append("s.georeferenced = 1")

        if date_from:
            clauses.append("s.acquisition_datetime >= ?")
            params.append(date_from)
        if date_to:
            # Inclusive upper bound: allow date-only strings by appending time if needed
            end = date_to if "T" in date_to else f"{date_to}T23:59:59Z"
            clauses.append("s.acquisition_datetime <= ?")
            params.append(end)

        if sensors:
            placeholders = ",".join("?" * len(sensors))
            clauses.append(f"LOWER(s.sensor) IN ({placeholders})")
            params.extend([s.lower() for s in sensors])

        if max_cloud_fraction is not None:
            if null_cloud_include:
                clauses.append(
                    "(t.cloud_fraction IS NULL OR t.cloud_fraction < 0 OR t.cloud_fraction <= ?)"
                )
            else:
                clauses.append("(t.cloud_fraction IS NOT NULL AND t.cloud_fraction >= 0 AND t.cloud_fraction <= ?)")
            params.append(max_cloud_fraction)

        if min_valid_fraction is not None:
            clauses.append("(t.valid_fraction IS NULL OR t.valid_fraction >= ?)")
            params.append(min_valid_fraction)

        if scene_ids:
            placeholders = ",".join("?" * len(scene_ids))
            clauses.append(f"t.scene_id IN ({placeholders})")
            params.extend(scene_ids)

        if exclude_tile_id is not None:
            clauses.append("t.tile_id != ?")
            params.append(int(exclude_tile_id))

        if model_name:
            clauses.append(
                "t.tile_id IN (SELECT tile_id FROM tile_embeddings WHERE model_name = ?)"
            )
            params.append(model_name)

        # Spatial: bbox via rtree intersection, optional AOI polygon refine
        rtree_join = ""
        if bbox is not None:
            minlon, minlat, maxlon, maxlat = bbox
            rtree_join = (
                "JOIN tiles_rtree r ON r.id = t.tile_id "
                "AND r.maxlon >= ? AND r.minlon <= ? "
                "AND r.maxlat >= ? AND r.minlat <= ?"
            )
            params = [minlon, maxlon, minlat, maxlat] + params

        sql = f"""
            SELECT t.tile_id, t.minlon, t.minlat, t.maxlon, t.maxlat, t.footprint_wkt
            FROM tiles t
            JOIN geo_scenes s ON s.scene_id = t.scene_id
            {rtree_join}
            WHERE {' AND '.join(clauses)}
        """
        rows = [dict(r) for r in self.db.query(sql, params)]

        if aoi_geojson is not None:
            try:
                from shapely.geometry import shape, box as shapely_box
                from shapely import wkt as shapely_wkt

                aoi = shape(aoi_geojson)
                filtered = []
                for r in rows:
                    try:
                        geom = shapely_wkt.loads(r["footprint_wkt"]) if r.get("footprint_wkt") else shapely_box(
                            r["minlon"], r["minlat"], r["maxlon"], r["maxlat"]
                        )
                        if geom.intersects(aoi):
                            filtered.append(r)
                    except Exception:
                        continue
                rows = filtered
            except Exception:
                pass

        return [int(r["tile_id"]) for r in rows]

    def get_tiles_with_scenes(self, tile_ids: Sequence[int]) -> Dict[int, Dict[str, Any]]:
        if not tile_ids:
            return {}
        placeholders = ",".join("?" * len(tile_ids))
        sql = f"""
            SELECT t.*, s.sensor, s.acquisition_datetime, s.date_source,
                   s.source_type, s.georeferenced, s.crs
            FROM tiles t
            JOIN geo_scenes s ON s.scene_id = t.scene_id
            WHERE t.tile_id IN ({placeholders})
        """
        out: Dict[int, Dict[str, Any]] = {}
        for r in self.db.query(sql, list(tile_ids)):
            d = dict(r)
            out[int(d["tile_id"])] = d
        return out

    def set_source_type(self, scene_id: str, source_type: str) -> None:
        self.db.execute(
            "UPDATE geo_scenes SET source_type = ? WHERE scene_id = ?",
            [source_type, scene_id],
        )

    def classify_demo_legacy(self) -> Dict[str, int]:
        """One-shot classification helper for existing data."""
        demo = 0
        legacy = 0
        for scene in self.db["geo_scenes"].rows:
            sid = scene["scene_id"]
            files = self.get_scene_files(sid)
            paths = " ".join(f.get("path", "") for f in files).lower()
            name = sid.lower()
            if "demo" in paths or "site0" in paths or "site0" in name or "demo" in name:
                self.set_source_type(sid, "DEMO")
                demo += 1
            elif not scene.get("georeferenced") or "whatsapp" in paths or "whatsapp" in name:
                self.set_source_type(sid, "LEGACY")
                legacy += 1
            elif not scene.get("source_type"):
                self.set_source_type(sid, "REAL")
        return {"demo": demo, "legacy": legacy}
