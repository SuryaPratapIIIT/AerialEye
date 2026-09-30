"""Tests for AerialEye review service."""
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
    img = Image.fromarray(np.random.randint(30, 180, (64, 64, 3), dtype=np.uint8))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def review_setup(tmp_path, monkeypatch):
    import backend.db as db_module
    import backend.services.ingestion_service as ing
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.db")
    ing.ASSET_STORE = tmp_path / "assets"
    ing.ASSET_STORE.mkdir()

    from backend.services.ingestion_service import ingest_file
    r1 = ingest_file(file_bytes=make_test_image_bytes(), filename="before.jpg", acquisition_time="2022-01-01T00:00:00Z", label="DEMO")
    r2 = ingest_file(file_bytes=make_test_image_bytes(), filename="after.jpg", acquisition_time="2023-01-01T00:00:00Z", label="DEMO")

    from backend.services.temporal_service import run_change_analysis
    change = run_change_analysis(r1["asset_id"], r2["asset_id"])
    return {"candidate_id": change.get("candidate_id"), "tmp_path": tmp_path}


def test_review_queue_empty(tmp_path, monkeypatch):
    import backend.db as db_module
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "empty.db")
    from backend.services.review_service import get_review_queue
    result = get_review_queue()
    assert result["total"] == 0
    assert result["items"] == []


def test_submit_decision(review_setup):
    candidate_id = review_setup["candidate_id"]
    if not candidate_id:
        pytest.skip("Change analysis did not produce a candidate")

    from backend.services.review_service import submit_decision, get_review_queue
    result = submit_decision(candidate_id=candidate_id, status="CONFIRMED", notes="looks real")
    assert result["success"] is True
    assert result["status"] == "CONFIRMED"

    queue = get_review_queue()
    confirmed = [i for i in queue["items"] if i["candidate_id"] == candidate_id]
    assert len(confirmed) == 1
    assert confirmed[0]["status"] == "CONFIRMED"


def test_invalid_decision_status(review_setup):
    candidate_id = review_setup["candidate_id"] or "fake-id"
    from backend.services.review_service import submit_decision
    result = submit_decision(candidate_id=candidate_id, status="INVALID_STATUS")
    assert result["success"] is False
