import yaml
from pathlib import Path
from typing import Dict, Any, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SENSORS_DIR = PROJECT_ROOT / "config" / "sensors"

class SensorProfile:
    def __init__(self, name: str, data: Dict[str, Any]):
        self.name = name
        self.data = data
        self.band_mapping = data.get("band_mapping", {})
        self.cloud_mask = data.get("cloud_mask", {})
        self.reflectance_scale = data.get("reflectance_scale", 10000.0)
        self.reflectance_offset = data.get("reflectance_offset", 0.0)
        self.resolution_m = data.get("resolution_m", 10.0)

    @property
    def cloud_classes(self) -> List[int]:
        return self.cloud_mask.get("cloud_classes", [])

    @property
    def shadow_classes(self) -> List[int]:
        return self.cloud_mask.get("shadow_classes", [])

    @property
    def snow_classes(self) -> List[int]:
        return self.cloud_mask.get("snow_classes", [])

    @property
    def nodata_classes(self) -> List[int]:
        return self.cloud_mask.get("nodata_classes", [])

    @classmethod
    def load(cls, sensor_name: str) -> "SensorProfile":
        # Fallback to sentinel2 if not found
        s_name = sensor_name.lower().split("-")[0]
        if "landsat" in s_name:
            path = SENSORS_DIR / "landsat.yaml"
        else:
            path = SENSORS_DIR / "sentinel2.yaml"
            
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                return cls(sensor_name, data)
        
        # Default fallback
        return cls("Unknown", {})
