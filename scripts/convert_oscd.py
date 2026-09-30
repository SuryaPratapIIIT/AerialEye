#!/usr/bin/env python3
"""
Convert OSCD (Onera Satellite Change Detection) style raster masks to GeoJSON label format.
"""

import json
import argparse
from pathlib import Path
import numpy as np

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mask", required=True, help="Path to OSCD raster mask (e.g., .tif or .png)")
    parser.add_argument("--out", default="data/labels_template.geojson", help="Output GeoJSON path")
    args = parser.parse_args()

    # In a real implementation we would use rasterio and rasterio.features.shapes
    # to polygonize the mask array.
    # For this template, we generate the expected GeoJSON structure.

    template = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "change_type": "construction",
                    "confidence": "high",
                    "source": "manual_label"
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [0.0, 0.0],
                            [0.01, 0.0],
                            [0.01, 0.01],
                            [0.0, 0.01],
                            [0.0, 0.0]
                        ]
                    ]
                }
            }
        ]
    }
    
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(template, f, indent=2)
        
    print(f"Generated label template at {out_path}")

if __name__ == "__main__":
    main()
