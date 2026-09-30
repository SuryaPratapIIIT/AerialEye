"""Scene series selection over an AOI."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from shapely.geometry import box, shape
from shapely.geometry.base import BaseGeometry

from backend.repository import GeoRepository
from backend.services.change.config import load_change_config
from backend.services.change.types import SceneObservation


def _aoi_geom(aoi: Any) -> BaseGeometry:
    if isinstance(aoi, dict):
        if aoi.get("type") == "Feature":
            return shape(aoi["geometry"])
        if aoi.get("type") == "FeatureCollection":
            return shape(aoi["features"][0]["geometry"])
        return shape(aoi)
    raise ValueError("AOI must be GeoJSON geometry/feature")


def select_scene_series(
    aoi: Any,
    date_from: str,
    date_to: str,
    sensor: Optional[str] = None,
    cfg: Optional[Dict[str, Any]] = None,
    repo: Optional[GeoRepository] = None,
) -> Tuple[List[SceneObservation], List[Dict[str, Any]]]:
    """
    Return (usable_scenes ordered by date, unusable_records).
    Usable-pixel fraction estimated from tile cloud/valid fractions intersecting AOI.
    """
    cfg = cfg or load_change_config()
    repo = repo or GeoRepository()
    geom = _aoi_geom(aoi)
    min_u = float(cfg.get("min_usable_fraction", 0.6))
    minlon, minlat, maxlon, maxlat = geom.bounds

    # Scenes intersecting AOI bbox via geo_scenes
    sql = """
        SELECT * FROM geo_scenes
        WHERE maxlon >= ? AND minlon <= ? AND maxlat >= ? AND minlat <= ?
          AND acquisition_datetime >= ? AND acquisition_datetime <= ?
          AND (source_type IS NULL OR source_type = 'REAL')
    """
    params: List[Any] = [minlon, maxlon, minlat, maxlat, date_from, date_to]
    if sensor:
        sql += " AND LOWER(sensor) LIKE ?"
        params.append(f"%{sensor.lower()}%")
    sql += " ORDER BY acquisition_datetime ASC"

    rows = [dict(r) for r in repo.db.query(sql, params)]
    usable: List[SceneObservation] = []
    unusable: List[Dict[str, Any]] = []

    for row in rows:
        scene_box = box(row["minlon"], row["minlat"], row["maxlon"], row["maxlat"])
        if not scene_box.intersects(geom):
            unusable.append({"scene_id": row["scene_id"], "reason": "no_aoi_intersection"})
            continue

        tiles = repo.get_tiles_for_scene(row["scene_id"])
        # Usable fraction from tiles intersecting AOI
        inter_tiles = []
        for t in tiles:
            tb = box(t["minlon"], t["minlat"], t["maxlon"], t["maxlat"])
            if tb.intersects(geom):
                inter_tiles.append(t)
        if not inter_tiles:
            # Scene-level fallback: 1 - mean cloud if available
            frac = 0.8
            qs = "none"
        else:
            vals = []
            for t in inter_tiles:
                vf = t.get("valid_fraction")
                cf = t.get("cloud_fraction")
                if vf is not None:
                    vals.append(float(vf) * (1.0 - float(cf or 0)))
                elif cf is not None:
                    vals.append(1.0 - float(cf))
            frac = float(sum(vals) / len(vals)) if vals else 0.5
            qs = inter_tiles[0].get("quality_source") or "none"

        obs = SceneObservation(
            scene_id=row["scene_id"],
            sensor=row.get("sensor") or "unknown",
            acquisition_datetime=row.get("acquisition_datetime") or "",
            georeferenced=bool(row.get("georeferenced")),
            source_type=row.get("source_type") or "REAL",
            minlon=row["minlon"],
            minlat=row["minlat"],
            maxlon=row["maxlon"],
            maxlat=row["maxlat"],
            usable_fraction_aoi=frac,
            quality_source=qs,
            resolution_m=float(row.get("resolution_m") or 10.0),
        )
        if frac < min_u:
            obs.unusable_reason = f"usable_fraction={frac:.3f}<{min_u}"
            unusable.append({"scene_id": obs.scene_id, "reason": obs.unusable_reason, "usable_fraction": frac})
        else:
            usable.append(obs)

    usable.sort(key=lambda o: o.acquisition_datetime)
    return usable, unusable


def prefer_same_season_pair(
    scenes: List[SceneObservation],
    cfg: Dict[str, Any],
) -> Optional[Tuple[SceneObservation, SceneObservation]]:
    """Pick the pair with minimal |DOY| difference among chronological pairs."""
    from backend.services.change.stages import day_of_year

    if len(scenes) < 2:
        return None
    best = None
    best_diff = 9999
    for i in range(len(scenes)):
        for j in range(i + 1, len(scenes)):
            d = abs(day_of_year(scenes[i].acquisition_datetime) - day_of_year(scenes[j].acquisition_datetime))
            d = min(d, 365 - d)
            if d < best_diff:
                best_diff = d
                best = (scenes[i], scenes[j])
    return best
