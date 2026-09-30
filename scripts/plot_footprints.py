import matplotlib.pyplot as plt
from shapely.wkt import loads
import argparse
from backend.repository import GeoRepository

def plot_scene_tiles(scene_id: str, out_path: str = "footprints.png"):
    repo = GeoRepository()
    scene = repo.get_scene(scene_id)
    if not scene:
        print(f"Scene {scene_id} not found.")
        return
        
    tiles = repo.db["tiles"].rows_where("scene_id = ?", [scene_id])
    
    fig, ax = plt.subplots(figsize=(10, 10))
    for t in tiles:
        poly = loads(t["footprint_wkt"])
        x, y = poly.exterior.xy
        ax.plot(x, y, color='#6699cc', alpha=0.7, linewidth=3, solid_capstyle='round', zorder=2)
        
    ax.set_title(f"Tile Footprints for {scene_id}")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    plt.savefig(out_path)
    print(f"Saved footprint plot to {out_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("scene_id")
    parser.add_argument("--out", default="footprints.png")
    args = parser.parse_args()
    plot_scene_tiles(args.scene_id, args.out)
