"""
Tests for AerialEye ingestion service.
"""
import io
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Override DB to a temp file during tests
os.environ["AERIALEYE_TEST"] = "1"


def make_test_image_bytes(size=(64, 64)) -> bytes:
    """Create a small JPEG image in memory."""
    from PIL import Image
    img = Image.fromarray(np.random.randint(0, 255, (*size, 3), dtype=np.uint8))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Use a temporary database for each test."""
    import backend.db as db_module
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.db")
    return tmp_path


def test_ingest_new_image(tmp_db):
    """Ingest a new image → status=ingested."""
    from backend.services.ingestion_service import ingest_file

    # Override asset store path
    import backend.services.ingestion_service as ing
    ing.ASSET_STORE = tmp_db / "assets"
    ing.ASSET_STORE.mkdir()

    file_bytes = make_test_image_bytes()
    result = ingest_file(
        file_bytes=file_bytes,
        filename="test_image_2023-01-01.jpg",
        sensor="test-sensor",
        acquisition_time="2023-01-01T00:00:00Z",
        label="DEMO",
    )
    assert result["status"] == "ingested"
    assert "asset_id" in result
    assert result["quality_score"] >= 0


def test_ingest_deduplication(tmp_db):
    """Ingesting the same bytes twice → second call returns skipped."""
    from backend.services.ingestion_service import ingest_file
    import backend.services.ingestion_service as ing
    ing.ASSET_STORE = tmp_db / "assets"
    ing.ASSET_STORE.mkdir(exist_ok=True)

    file_bytes = make_test_image_bytes()
    first = ingest_file(file_bytes=file_bytes, filename="dup.jpg", label="DEMO")
    second = ingest_file(file_bytes=file_bytes, filename="dup.jpg", label="DEMO")

    assert first["status"] == "ingested"
    assert second["status"] == "skipped"
    assert first["asset_id"] == second["asset_id"]


def test_quality_assessment(tmp_db):
    """Quality score should be between 0 and 1."""
    from backend.services.ingestion_service import ingest_file
    import backend.services.ingestion_service as ing
    ing.ASSET_STORE = tmp_db / "assets"
    ing.ASSET_STORE.mkdir(exist_ok=True)

    file_bytes = make_test_image_bytes()
    result = ingest_file(file_bytes=file_bytes, filename="q_test.jpg", label="DEMO")

    assert 0.0 <= result["quality_score"] <= 1.0
