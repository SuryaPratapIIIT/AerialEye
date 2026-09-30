import os
import argparse
import random
import uuid
import time
from pathlib import Path
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS

try:
    from backend.repository import GeoRepository
except ImportError:
    print("Please run this from the root directory: python scripts/add_mock_map_data.py")
    exit(1)

def get_exif_data(image_path):
    """Extract EXIF data from an image."""
    exif_data = {}
    try:
        image = Image.open(image_path)
        info = image._getexif()
        if info:
            for tag, value in info.items():
                decoded = TAGS.get(tag, tag)
                if decoded == "GPSInfo":
                    gps_data = {}
                    for t in value:
                        sub_decoded = GPSTAGS.get(t, t)
                        gps_data[sub_decoded] = value[t]
                    exif_data[decoded] = gps_data
                else:
                    exif_data[decoded] = value
    except Exception as e:
        pass
    return exif_data

def get_decimal_from_dms(dms, ref):
    """Convert degrees, minutes, seconds to decimal degrees."""
    try:
        degrees = dms[0]
        minutes = dms[1]
        seconds = dms[2]
        decimal = float(degrees) + float(minutes)/60 + float(seconds)/3600
        if ref in ['S', 'W']:
            decimal = -decimal
        return decimal
    except:
        return None

def get_coordinates(exif_data):
    """Extract lat/lon from EXIF data."""
    if 'GPSInfo' in exif_data:
        gps_info = exif_data['GPSInfo']
        gps_latitude = gps_info.get('GPSLatitude')
        gps_latitude_ref = gps_info.get('GPSLatitudeRef')
        gps_longitude = gps_info.get('GPSLongitude')
        gps_longitude_ref = gps_info.get('GPSLongitudeRef')

        if gps_latitude and gps_latitude_ref and gps_longitude and gps_longitude_ref:
            lat = get_decimal_from_dms(gps_latitude, gps_latitude_ref)
            lon = get_decimal_from_dms(gps_longitude, gps_longitude_ref)
            return lat, lon
    return None, None

def generate_dummy_coordinates(index):
    """Generate distinct coordinates if EXIF is missing. (Scattered across India)"""
    # India bounding box roughly: lat 8 to 35, lon 68 to 97
    import random
    
    # Pick a random base location in India for each image
    lat = random.uniform(10.0, 32.0)
    lon = random.uniform(70.0, 90.0)
    
    return lat, lon

def ingest_mock_images(folder_path):
    repo = GeoRepository()
    folder = Path(folder_path)
    
    if not folder.exists() or not folder.is_dir():
        print(f"Error: {folder_path} is not a valid directory.")
        return

    images = list(folder.glob("*.jpg")) + list(folder.glob("*.jpeg")) + list(folder.glob("*.png"))
    if not images:
        print(f"No images found in {folder_path}.")
        return

    print(f"Found {len(images)} images. Integrating into database...")
    
    for idx, img_path in enumerate(images):
        scene_id = f"MOCK_{uuid.uuid4().hex[:8].upper()}"
        print(f"\nProcessing {img_path.name} as Scene: {scene_id}")
        
        # 1. Try fetching coordinates
        exif = get_exif_data(img_path)
        lat, lon = get_coordinates(exif)
        
        if lat is None or lon is None:
            print("  - No EXIF GPS found. Assigning distinct dummy coordinates...")
            lat, lon = generate_dummy_coordinates(idx)
        else:
            print(f"  - Found EXIF coordinates: {lat}, {lon}")
            
        # Create a small bounding box around the point (approx 200m x 200m)
        delta = 0.001
        minlat, maxlat = lat - delta, lat + delta
        minlon, maxlon = lon - delta, lon + delta
        
        # 2. Insert into geo_scenes
        scene_data = {
            "scene_id": scene_id,
            "sensor": "Mock-Drone",
            "product_level": "L1",
            "acquisition_datetime": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "date_source": "MOCK",
            "crs": "EPSG:4326",
            "transform_json": "[]",
            "width": 1024,
            "height": 1024,
            "resolution_m": 0.5,
            "bounds_native_json": f"[{minlon}, {minlat}, {maxlon}, {maxlat}]",
            "minlon": minlon,
            "minlat": minlat,
            "maxlon": maxlon,
            "maxlat": maxlat,
            "band_names_json": '["RGB"]',
            "nodata": 0.0,
            "georeferenced": True,
            "cloud_mask_available": False,
            "ingested_at": time.time(),
            "pipeline_version": "mock_v1",
            "source_type": "DEMO"
        }
        
        repo.db["geo_scenes"].insert(scene_data, pk="scene_id", replace=True)
        
        # 3. Create a single tile for the image so it shows on the map
        # We use a WKT polygon for the footprint
        wkt = f"POLYGON (({minlon} {minlat}, {maxlon} {minlat}, {maxlon} {maxlat}, {minlon} {maxlat}, {minlon} {minlat}))"
        
        tile_data = {
            "scene_id": scene_id,
            "footprint_wkt": wkt,
            "cloud_fraction": 0.0,
            "valid_fraction": 1.0,
            "preview_path": str(img_path.absolute()),
            "chip_path": str(img_path.absolute()),
            "embedded": 0,
            "quality_source": "mock",
            "minlon": minlon,
            "minlat": minlat,
            "maxlon": maxlon,
            "maxlat": maxlat,
        }
        repo.db["tiles"].insert(tile_data)
        
        print(f"  -> Successfully added {img_path.name} to the map at [{lat:.4f}, {lon:.4f}].")

    print("\nDone! You can now view these images on the Leaflet map in the frontend UI.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest mock images with coordinates for Leaflet map prototype")
    parser.add_argument("folder", help="Folder containing the uploaded mock images (.jpg/.png)")
    args = parser.parse_args()
    ingest_mock_images(args.folder)
