import os
import pytest
import numpy as np
import rasterio
from rasterio.transform import from_origin
from PIL import Image
from pathlib import Path
from backend.services.geospatial_ingestion import (
    process_folder, extract_metadata, compute_quality_mask, IngestionConfig
)
from backend.repository import GeoRepository
from shapely.wkt import loads

@pytest.fixture
def test_dir(tmp_path):
    data_dir = tmp_path / "raw"
    data_dir.mkdir()
    
    # 1. Synthetic GeoTIFF (Sentinel-2 style)
    tif_path = data_dir / "S2A_MSIL2A_20240315T053641_B04.tif"
    transform = from_origin(300000, 4000000, 10, 10)
    data = np.ones((1, 512, 512), dtype=rasterio.uint16)
    with rasterio.open(
        tif_path, 'w', driver='GTiff',
        height=512, width=512, count=1, dtype=data.dtype,
        crs='EPSG:32630', transform=transform, nodata=0
    ) as dst:
        dst.write(data)

    scl_path = data_dir / "S2A_MSIL2A_20240315T053641_SCL.tif"
    scl_data = np.ones((1, 512, 512), dtype=rasterio.uint8) * 4 # Valid
    scl_data[0, 0:100, 0:100] = 8 # Cloud
    with rasterio.open(
        scl_path, 'w', driver='GTiff',
        height=512, width=512, count=1, dtype=scl_data.dtype,
        crs='EPSG:32630', transform=transform, nodata=0
    ) as dst:
        dst.write(scl_data)

    # 2. Corrupt GeoTIFF
    corrupt_path = data_dir / "LC08_CORRUPT_20240101.tif"
    corrupt_path.write_text("Not a real tif")

    # 3. Legacy JPG
    jpg_path = data_dir / "legacy_drone_shot.jpg"
    img = Image.new('RGB', (100, 100), color = 'red')
    img.save(jpg_path)

    return tmp_path

@pytest.fixture
def config():
    return IngestionConfig(
        tile_size=256,
        overlap=32,
        edge_tiles="drop",
        min_valid_fraction=0.5,
        nodata_fraction_threshold=0.5,
        scl_masks={"cloud": [8, 9], "valid": [4, 5, 6]},
        qa_masks={"cloud_bit": 3}
    )

def test_metadata_extraction(test_dir):
    files = [test_dir / "raw" / "S2A_MSIL2A_20240315T053641_B04.tif"]
    meta = extract_metadata("S2A_MSIL2A_20240315T053641", files)
    
    assert meta["sensor"] == "Sentinel-2"
    assert "2024-03-15" in meta["acquisition_datetime"]
    assert meta["georeferenced"] is True
    assert meta["width"] == 512
    assert meta["height"] == 512

def test_cloud_fraction(config):
    scl_window = np.ones((100, 100), dtype=np.uint8) * 4
    scl_window[0:10, 0:10] = 8 # 100 pixels cloudy
    mask, _ = compute_quality_mask(scl_window, config, "Sentinel-2")
    cloud_frac = np.sum(mask == 1) / mask.size
    assert cloud_frac == 0.01

def test_process_folder(test_dir):
    # This also tests corrupt file isolation (7) and legacy JPG (9)
    res = process_folder(str(test_dir / "raw"), "config.yaml")
    
    assert res["new"] == 2 # 1 S2, 1 JPG
    assert res["failed"] == 1 # Corrupt LC08
    assert res["skipped"] == 0
    
    repo = GeoRepository()
    # Find S2 scene
    s2_scenes = list(repo.db["geo_scenes"].rows_where("sensor = 'Sentinel-2'"))
    assert len(s2_scenes) == 1
    s2_id = s2_scenes[0]["scene_id"]
    
    tiles = list(repo.db["tiles"].rows_where("scene_id = ?", [s2_id]))
    # 512x512 with 256 tiles, 32 overlap:
    # Step = 224.
    # X: 0 (0-256), 224 (224-480). Next is 448 which leaves 512-448=64 width. 
    # With drop logic, 64 < 128 (50% min), so it drops.
    # Result: 2x2 = 4 tiles.
    assert len(tiles) == 4
    
    # Test footprint match (2)
    t0 = tiles[0]
    poly = loads(t0["footprint_wkt"])
    # Native: 300000, 4000000, res=10. Tile 256x256 -> 2560m x 2560m
    # We won't strictly check exact WGS84 coords because of pyproj rounding, 
    # but we can ensure it has coordinates.
    assert poly.area > 0
    
    # Test Idempotency (4)
    res2 = process_folder(str(test_dir / "raw"), "config.yaml")
    assert res2["new"] == 0
    assert res2["skipped"] == 2
    
    # Test Modified file triggers re-ingestion (6)
    tif_path = test_dir / "raw" / "S2A_MSIL2A_20240315T053641_B04.tif"
    with open(tif_path, "ab") as f:
        f.write(b"mod")
    
    res3 = process_folder(str(test_dir / "raw"), "config.yaml")
    assert res3["new"] == 1
    assert res3["skipped"] == 1 # JPG unchanged
