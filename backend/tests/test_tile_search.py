"""
Prompt 2 embedding/search tests — network disabled, FakeEmbeddingModel only.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
os.environ["AERIALEYE_TEST"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"


@pytest.fixture
def embed_env(tmp_path, monkeypatch):
    """Isolated DB + indexes + fake model."""
    import backend.db as db_module
    import backend.services.embedding_service as es
    import backend.services.embedding_models as em

    db_path = tmp_path / "test.db"
    index_dir = tmp_path / "indexes"
    index_dir.mkdir()
    tiles_dir = tmp_path / "tiles"
    tiles_dir.mkdir()

    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    monkeypatch.setattr(es, "INDEX_DIR", index_dir)
    monkeypatch.setattr(es, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(es, "_config_cache", {
        "embedding": {
            "model": "fake-hist",
            "device": "cpu",
            "min_valid_fraction": 0.5,
            "exclude_cloudy_from_index_above": 0.8,
            "use_hnsw": False,
            "batch_size": 8,
            "input_size": 64,
        },
        "search": {
            "deduplicate_iou_threshold": 0.8,
            "deduplicate_overlapping": True,
            "max_candidates_for_exact": 5000,
            "prompt_templates": ["a satellite image of {query}"],
            "null_cloud_fraction": "include",
        },
    })
    es._active_model = None
    es._active_model_name = None
    es._faiss_index = None
    es._vector_store = {}

    from backend.repository import GeoRepository
    from backend.services.embedding_models import FakeEmbeddingModel

    repo = GeoRepository()
    model = FakeEmbeddingModel(dim=64)

    def _get_model(name=None, device=None, models_dir=None):
        return model

    monkeypatch.setattr(es, "get_model", lambda name=None, device=None: model)
    monkeypatch.setattr(em, "get_embedding_model", lambda name, device="cpu", models_dir=None: model)

    return {
        "repo": repo,
        "model": model,
        "tmp": tmp_path,
        "index_dir": index_dir,
        "tiles_dir": tiles_dir,
        "es": es,
    }


def _make_rgb(path: Path, color=(80, 140, 60)) -> Path:
    from PIL import Image

    img = Image.new("RGB", (64, 64), color)
    img.save(path)
    return path


def _insert_tile(
    repo,
    tiles_dir,
    tile_id: int,
    scene_id: str,
    *,
    minlon=10.0,
    minlat=20.0,
    maxlon=10.1,
    maxlat=20.1,
    cloud=0.1,
    valid=0.9,
    sensor="Sentinel-2",
    acq="2024-03-15T00:00:00Z",
    source_type="REAL",
    georeferenced=True,
    superseded=False,
    color=(80, 140, 60),
):
    from PIL import Image

    scene_dir = tiles_dir / scene_id
    scene_dir.mkdir(parents=True, exist_ok=True)
    preview = scene_dir / f"{tile_id}.png"
    chip = scene_dir / f"{tile_id}.npy"
    _make_rgb(preview, color)
    arr = np.asarray(Image.open(preview))
    np.save(str(chip), arr)

    if repo.get_scene(scene_id) is None:
        repo.insert_scene(
            {
                "scene_id": scene_id,
                "sensor": sensor,
                "product_level": "L2A",
                "acquisition_datetime": acq,
                "date_source": "test",
                "crs": "EPSG:4326",
                "transform_json": "[]",
                "width": 64,
                "height": 64,
                "resolution_m": 10.0,
                "bounds_native_json": "[]",
                "minlon": minlon,
                "minlat": minlat,
                "maxlon": maxlon,
                "maxlat": maxlat,
                "band_names_json": '["R","G","B"]',
                "nodata": -9999.0,
                "georeferenced": georeferenced,
                "cloud_mask_available": False,
                "ingested_at": 0.0,
                "pipeline_version": "test",
                "source_type": source_type,
            }
        )

    repo.insert_tiles(
        [
            {
                "tile_id": tile_id,
                "scene_id": scene_id,
                "row": 0,
                "col": tile_id % 100,
                "window_json": "[0,0,64,64]",
                "footprint_wkt": f"POLYGON(({minlon} {minlat},{maxlon} {minlat},{maxlon} {maxlat},{minlon} {maxlat},{minlon} {minlat}))",
                "minlon": minlon,
                "minlat": minlat,
                "maxlon": maxlon,
                "maxlat": maxlat,
                "centroid_lon": (minlon + maxlon) / 2,
                "centroid_lat": (minlat + maxlat) / 2,
                "nodata_fraction": 0.0,
                "cloud_fraction": cloud,
                "shadow_fraction": 0.0,
                "snow_fraction": 0.0,
                "valid_fraction": valid,
                "quality_source": "test",
                "preview_path": str(preview),
                "chip_path": str(chip),
                "mask_path": "",
                "embedded": False,
                "superseded": superseded,
            }
        ]
    )
    # Sync rtree manually if trigger missed replace
    try:
        repo.db.execute(
            "INSERT OR REPLACE INTO tiles_rtree(id, minlon, maxlon, minlat, maxlat) VALUES (?,?,?,?,?)",
            [tile_id, minlon, maxlon, minlat, maxlat],
        )
    except Exception:
        pass


def test_no_duplicate_ids_on_double_add(embed_env):
    es = embed_env["es"]
    repo = embed_env["repo"]
    _insert_tile(repo, embed_env["tiles_dir"], 1, "s1", color=(10, 20, 30))
    _insert_tile(repo, embed_env["tiles_dir"], 2, "s1", minlon=11, maxlon=11.1, color=(40, 50, 60))

    es.run_incremental_embed(model_name="fake-hist", batch_size=8)
    n1 = es.get_index("fake-hist").ntotal
    es.run_incremental_embed(model_name="fake-hist", batch_size=8)
    n2 = es.get_index("fake-hist").ntotal
    assert n1 == n2 == 2
    ids = es.get_index_ids()
    assert ids == {1, 2}


def test_incremental_only_encodes_new(embed_env, monkeypatch):
    es = embed_env["es"]
    repo = embed_env["repo"]
    for i in range(10):
        _insert_tile(
            repo,
            embed_env["tiles_dir"],
            100 + i,
            f"sc{i}",
            minlon=1 + i * 0.2,
            maxlon=1.1 + i * 0.2,
            color=(i * 20, 50, 100),
        )
    stats1 = es.run_incremental_embed(model_name="fake-hist", batch_size=16)
    assert stats1["encoded"] == 10

    encode_calls = {"n": 0}
    real_encode = embed_env["model"].encode_images

    def counting_encode(images):
        encode_calls["n"] += len(images)
        return real_encode(images)

    monkeypatch.setattr(embed_env["model"], "encode_images", counting_encode)

    for i in range(5):
        _insert_tile(
            repo,
            embed_env["tiles_dir"],
            200 + i,
            f"sc_new{i}",
            minlon=50 + i,
            maxlon=50.1 + i,
            color=(200, i * 10, 30),
        )
    stats2 = es.run_incremental_embed(model_name="fake-hist", batch_size=16)
    assert stats2["encoded"] == 5
    assert encode_calls["n"] == 5


def test_crash_between_index_and_db_no_duplicates(embed_env):
    es = embed_env["es"]
    repo = embed_env["repo"]
    for i in range(3):
        _insert_tile(repo, embed_env["tiles_dir"], 300 + i, f"crash{i}", minlon=i, maxlon=i + 0.1)

    with pytest.raises(RuntimeError, match="Simulated crash"):
        es.run_incremental_embed(model_name="fake-hist", fail_after_index_write=True)

    # Index may have vectors; DB may not
    n_index = es.get_index("fake-hist").ntotal
    assert n_index > 0
    # Re-run should heal without duplicates
    stats = es.run_incremental_embed(model_name="fake-hist")
    assert es.get_index("fake-hist").ntotal == n_index
    assert repo.count_tiles_indexed("fake-hist") == n_index


def test_bbox_and_date_filters(embed_env):
    es = embed_env["es"]
    repo = embed_env["repo"]
    _insert_tile(repo, embed_env["tiles_dir"], 401, "a", minlon=10, minlat=20, maxlon=11, maxlat=21, acq="2024-01-01T00:00:00Z", color=(1, 2, 3))
    _insert_tile(repo, embed_env["tiles_dir"], 402, "b", minlon=50, minlat=50, maxlon=51, maxlat=51, acq="2024-06-01T00:00:00Z", color=(200, 200, 200))
    _insert_tile(repo, embed_env["tiles_dir"], 403, "c", minlon=10.2, minlat=20.2, maxlon=10.5, maxlat=20.5, acq="2024-01-15T00:00:00Z", color=(5, 5, 5))
    es.run_incremental_embed(model_name="fake-hist")

    from backend.services.search_service import search_text

    out = search_text(
        "test",
        k=10,
        filters={"bbox": [9.5, 19.5, 12, 22], "date_from": "2024-01-01", "date_to": "2024-01-31"},
    )
    ids = {r["tile_id"] for r in out["results"]}
    assert 401 in ids
    assert 403 in ids
    assert 402 not in ids

    # Boundary: date_to inclusive
    out2 = search_text("test", k=10, filters={"date_from": "2024-06-01", "date_to": "2024-06-01"})
    ids2 = {r["tile_id"] for r in out2["results"]}
    assert 402 in ids2


def test_sensor_and_cloud_filters_null_cloud(embed_env):
    es = embed_env["es"]
    repo = embed_env["repo"]
    _insert_tile(repo, embed_env["tiles_dir"], 501, "s2a", sensor="Sentinel-2", cloud=0.2, color=(1, 1, 1))
    _insert_tile(repo, embed_env["tiles_dir"], 502, "l8a", sensor="Landsat", cloud=0.9, minlon=2, maxlon=2.1, color=(2, 2, 2))
    _insert_tile(repo, embed_env["tiles_dir"], 503, "s2b", sensor="Sentinel-2", cloud=None, minlon=3, maxlon=3.1, color=(3, 3, 3))
    # Fix null cloud in DB
    repo.db.execute("UPDATE tiles SET cloud_fraction = NULL WHERE tile_id = 503")
    es.run_incremental_embed(model_name="fake-hist")

    from backend.services.search_service import search_text

    out = search_text("x", k=10, filters={"sensors": ["Sentinel-2"], "max_cloud_fraction": 0.5})
    ids = {r["tile_id"] for r in out["results"]}
    assert 501 in ids
    assert 503 in ids  # null included by default
    assert 502 not in ids


def test_filtered_search_returns_exactly_k(embed_env):
    es = embed_env["es"]
    repo = embed_env["repo"]
    for i in range(12):
        _insert_tile(
            repo,
            embed_env["tiles_dir"],
            600 + i,
            f"fk{i}",
            minlon=i,
            maxlon=i + 0.05,
            color=(i * 15, 40, 80),
        )
    es.run_incremental_embed(model_name="fake-hist")
    from backend.services.search_service import search_text

    out = search_text("river", k=5, filters={})
    assert out["total"] == 5
    assert len(out["results"]) == 5


def test_superseded_never_in_results(embed_env):
    es = embed_env["es"]
    repo = embed_env["repo"]
    _insert_tile(repo, embed_env["tiles_dir"], 701, "old", superseded=False, color=(1, 1, 1))
    _insert_tile(repo, embed_env["tiles_dir"], 702, "new", minlon=5, maxlon=5.1, color=(9, 9, 9))
    es.run_incremental_embed(model_name="fake-hist")
    repo.db.execute("UPDATE tiles SET superseded = 1 WHERE tile_id = 701")

    from backend.services.search_service import search_text

    out = search_text("x", k=10)
    ids = {r["tile_id"] for r in out["results"]}
    assert 701 not in ids
    assert 702 in ids


def test_query_tile_excluded_from_similar(embed_env):
    es = embed_env["es"]
    repo = embed_env["repo"]
    for i in range(5):
        _insert_tile(repo, embed_env["tiles_dir"], 800 + i, f"sim{i}", minlon=i, maxlon=i + 0.1, color=(i * 30, 10, 10))
    es.run_incremental_embed(model_name="fake-hist")
    from backend.services.search_service import similar_tiles

    out = similar_tiles(800, k=5)
    ids = [r["tile_id"] for r in out["results"]]
    assert 800 not in ids


def test_missing_weights_clear_error(tmp_path, monkeypatch):
    import backend.services.embedding_models as em

    monkeypatch.setattr(em, "MODELS_DIR", tmp_path / "models")
    with pytest.raises(em.ModelWeightsMissingError) as ei:
        em.CLIPViTB32Model(device="cpu", models_dir=tmp_path / "models")
    assert "missing" in str(ei.value).lower() or "weights" in str(ei.value).lower()


def test_response_schema_footprint_provenance_version(embed_env):
    es = embed_env["es"]
    repo = embed_env["repo"]
    _insert_tile(repo, embed_env["tiles_dir"], 901, "schema", color=(50, 50, 50))
    es.run_incremental_embed(model_name="fake-hist")
    from backend.services.search_service import search_text

    out = search_text("schema", k=1)
    assert out["results"]
    r = out["results"][0]
    assert "footprint" in r and r["footprint"].get("type")
    assert r["provenance"] == "REAL"
    assert r["model_version"]
    assert "search_meta" in out
