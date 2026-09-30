"""Pydantic request/response models for AerialEye search & embed APIs."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator


class SearchFilters(BaseModel):
    bbox: Optional[List[float]] = Field(
        None, description="[minlon, minlat, maxlon, maxlat]"
    )
    aoi: Optional[Dict[str, Any]] = Field(None, description="GeoJSON geometry polygon")
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    sensors: Optional[List[str]] = None
    max_cloud_fraction: Optional[float] = Field(None, ge=0.0, le=1.0)
    min_valid_fraction: Optional[float] = Field(None, ge=0.0, le=1.0)
    scene_ids: Optional[List[str]] = None
    georeferenced_only: bool = False
    include_legacy: bool = False
    include_demo: bool = False
    deduplicate: Optional[bool] = None
    negative_terms: Optional[List[str]] = None

    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, v):
        if v is None:
            return v
        if len(v) != 4:
            raise ValueError("bbox must be [minlon, minlat, maxlon, maxlat]")
        minlon, minlat, maxlon, maxlat = v
        if minlon > maxlon or minlat > maxlat:
            raise ValueError("bbox ordering invalid: require minlon<=maxlon, minlat<=maxlat")
        return v


class TextSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    k: int = Field(20, ge=1, le=200)
    filters: Optional[SearchFilters] = None


class ImageSearchJsonRequest(BaseModel):
    tile_id: int
    k: int = Field(20, ge=1, le=200)
    filters: Optional[SearchFilters] = None


class EmbedRunRequest(BaseModel):
    model: Optional[str] = None
    batch_size: int = Field(64, ge=1, le=512)
    device: Optional[str] = Field(None, pattern="^(cpu|cuda)$")
    limit: Optional[int] = Field(None, ge=1)


class ChangeRunRequest(BaseModel):
    aoi: Dict[str, Any] = Field(..., description="GeoJSON geometry or Feature")
    date_from: str
    date_to: str
    mode: str = Field("pair", pattern="^(pair|series)$")
    before_scene_id: Optional[str] = None
    after_scene_id: Optional[str] = None
    sensor: Optional[str] = None
    include_low_confidence: bool = False
    background: bool = True


class TileSearchResult(BaseModel):
    tile_id: int
    score: float
    rank: int
    scene_id: Optional[str] = None
    sensor: Optional[str] = None
    acquisition_datetime: Optional[str] = None
    date_source: Optional[str] = None
    footprint: Optional[Dict[str, Any]] = None
    bbox: Optional[List[Optional[float]]] = None
    centroid: Optional[List[Optional[float]]] = None
    cloud_fraction: Optional[float] = None
    valid_fraction: Optional[float] = None
    quality_source: Optional[str] = None
    preview_url: Optional[str] = None
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    provenance: Optional[str] = None


class SearchResponse(BaseModel):
    results: List[Dict[str, Any]]
    total: int
    search_meta: Dict[str, Any]
    label: Optional[str] = None
    method: Optional[str] = None
    model: Optional[str] = None
    query: Optional[str] = None
    note: Optional[str] = None
    error: Optional[str] = None
