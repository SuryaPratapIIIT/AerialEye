import argparse
import logging
import time
from backend.services.geospatial_ingestion import process_folder

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def main():
    parser = argparse.ArgumentParser(description="AerialEye Geospatial Ingestion CLI")
    parser.add_argument("folder", help="Folder containing raw GeoTIFFs to ingest")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--tile-size", type=int, help="Override tile size")
    parser.add_argument("--overlap", type=int, help="Override overlap")
    parser.add_argument("--watch", action="store_true", help="Poll folder continuously")
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode")
    parser.add_argument("--workers", type=int, default=1, help="Number of workers (unused in v1)")
    
    args = parser.parse_args()
    
    if args.dry_run:
        logging.info("Dry-run mode not fully implemented. Exiting.")
        return
        
    def run_ingest():
        logging.info(f"Starting ingestion on {args.folder}")
        start = time.time()
        res = process_folder(args.folder, args.config)
        elapsed = time.time() - start
        
        print("\n--- INGESTION SUMMARY ---")
        print(f"New Scenes:     {res['new']}")
        print(f"Skipped Scenes: {res['skipped']}")
        print(f"Failed Scenes:  {res['failed']}")
        print(f"Tiles Created:  {res['tiles']}")
        print(f"Time Taken:     {elapsed:.2f}s")
        print("-------------------------\n")

    if args.watch:
        logging.info("Watching folder... (polling every 30s)")
        while True:
            run_ingest()
            time.sleep(30)
    else:
        run_ingest()

if __name__ == "__main__":
    main()
