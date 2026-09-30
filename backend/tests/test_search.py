"""Tests for AerialEye search service."""
import io
import os
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
os.environ["AERIALEYE_TEST"] = "1"


def make_test_image_bytes() -> bytes:
    from PIL import Image
    img = Image.fromarray(np.random.randint(0, 200, (64, 64, 3), dtype=np.uint8))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def populated_db(tmp_path, monkeypatch):
    import backend.db as db_module
    import backend.services.ingestion_service as ing
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.db")
    ing.ASSET_STORE = tmp_path / "assets"
    ing.ASSET_STORE.mkdir()

    from backend.services.ingestion_service import ingest_file
    for i in range(3):
        ingest_file(
            file_bytes=make_test_image_bytes(),
            filename=f"search_test_{i}_2023-0{i+1}-01.jpg",
            sensor="TestSensor",
            acquisition_time=f"2023-0{i+1}-01T00:00:00Z",
            label="DEMO",
            tags=["construction", "test"],
        )
    return tmp_path


def test_keyword_fallback_search(populated_db):
    """Keyword search returns results when CLIP is not available."""
    from backend.services.search_service import text_search
    result = text_search(query="construction", top_k=10)
    assert isinstance(result, dict)
    assert "results" in result
    assert "label" in result


def test_search_empty_index(tmp_path, monkeypatch):
    """Search on empty index returns empty results gracefully."""
    import backend.db as db_module
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "empty.db")
    from backend.services.search_service import text_search
    result = text_search(query="anything")
    assert result["total"] == 0
    assert result["results"] == []


def test_search_date_filter(populated_db):
    """Date filter restricts results."""
    from backend.services.search_service import text_search
    result = text_search(query="test", date_from="2023-02-01", date_to="2023-03-31")
    for r in result["results"]:
        assert r["acquisition_time"] >= "2023-02-01"
        assert r["acquisition_time"] <= "2023-04-01"
