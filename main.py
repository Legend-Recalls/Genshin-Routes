import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import OUTPUT_DIR, DATA_DIR, PROJECT_ROOT, MAPS_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger("route_explorer")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 50)
    print("  Route Explorer")
    print("=" * 50)
    print("\n  1) Extract Minimaps")
    print("  2) Localize Route")
    print("  3) Optimize Route")
    print("  4) View Route")
    print("  5) Exit")

    choice = input("\nChoice (1-5): ").strip()

    if choice == "1":
        handle_extract()
    elif choice == "2":
        handle_localize()
    elif choice == "3":
        handle_optimize()
    elif choice == "4":
        handle_view()
    elif choice == "5":
        print("Goodbye!")
    else:
        print("Invalid choice")


def handle_localize():
    print("\nAvailable routes for localization:")
    routes = [d for d in OUTPUT_DIR.iterdir() if d.is_dir() and (d / "route.json").exists()]
    if not routes:
        print("  No routes found. Extract minimaps first.")
        return

    for i, r in enumerate(routes, 1):
        print(f"  {i}) {r.name}")

    choice = input(f"\nChoice (1-{len(routes)}): ").strip()
    try:
        idx = int(choice) - 1
        route_dir = routes[idx]
    except (ValueError, IndexError):
        print("Invalid choice")
        return

    from src.localizer import Localizer
    from src.map_dataset import MapDataset
    map_dir = MAPS_DIR / "surface"
    if not map_dir.exists():
        print(f"Map directory not found: {map_dir}")
        return
    localizer = Localizer(MapDataset.load(map_dir))
    localizer.localize_route(route_dir)

    # Prompt auto-optimization
    choice_opt = input("\nDo you want to run route optimization now? [Y/n]: ").strip().lower()
    if choice_opt in ("", "y", "yes"):
        from src.optimizer import RouteOptimizer
        optimizer = RouteOptimizer()
        optimizer.optimize_route(route_dir)


def handle_optimize():
    print("\nAvailable routes for optimization:")
    routes = [d for d in OUTPUT_DIR.iterdir() if d.is_dir() and (d / "route.json").exists()]
    if not routes:
        print("  No routes found. Localize first.")
        return

    for i, r in enumerate(routes, 1):
        status = " (Optimized)" if (r / "optimized_route.json").exists() else ""
        print(f"  {i}) {r.name}{status}")

    choice = input(f"\nChoice (1-{len(routes)}): ").strip()
    try:
        idx = int(choice) - 1
        route_dir = routes[idx]
    except (ValueError, IndexError):
        print("Invalid choice")
        return

    from src.optimizer import RouteOptimizer
    optimizer = RouteOptimizer()
    optimizer.optimize_route(route_dir)


def handle_view():
    import subprocess
    from pathlib import Path
    
    viewer_dir = PROJECT_ROOT / "src"
    viewer_script = viewer_dir / "viewer.py"
    
    print("\nStarting Web Viewer...")
    print("Open http://127.0.0.1:9090 in your browser.")
    print("Press Ctrl+C to stop.")
    try:
        subprocess.run([sys.executable, str(viewer_script)], cwd=str(viewer_dir))
    except KeyboardInterrupt:
        print("\nViewer stopped.")


def handle_extract():
    from src.calibrate import calibrate_video
    from src.extractor import extract_minimaps, verify_and_confirm

    print("\nSelect input source:")
    print("  1) YouTube URL")
    print("  2) Local video file")
    source = input("\nChoice (1 or 2): ").strip()

    if source == "1":
        url = input("Enter YouTube URL: ").strip()
        from src.downloader import download_video
        video_path = download_video(url)
    elif source == "2":
        url = input("Enter path to local video file: ").strip().strip('"').strip("'")
        video_path = Path(url).resolve()
        if not video_path.exists():
            print(f"File not found: {video_path}")
            return
    else:
        print("Invalid choice.")
        return

    video_name = video_path.stem
    output_dir = OUTPUT_DIR / video_name
    output_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Calibrate - draw minimap region manually
    print("\n--- Step 1: Calibrate Minimap Region ---")
    profile = calibrate_video(video_path)
    if profile is None:
        print("Calibration cancelled.")
        return

    # Step 2: Verify
    print("\n--- Step 2: Verify Crop Region ---")
    confirmed = verify_and_confirm(video_path, profile, output_dir)
    if not confirmed:
        print("Aborted by user.")
        return

    # Step 3: Extract
    print("\n--- Step 3: Extract Minimaps ---")
    route_path = extract_minimaps(video_path, video_name, profile=profile, output_base=OUTPUT_DIR)
    print(f"\nDone! Route saved: {route_path}")

    # Prompt auto-localization
    choice = input("\nDo you want to run route localization now? [Y/n]: ").strip().lower()
    if choice in ("", "y", "yes"):
        from src.localizer import Localizer
        from src.map_dataset import MapDataset
        map_dir = MAPS_DIR / "surface"
        if not map_dir.exists():
            print(f"Map directory not found: {map_dir}")
            return
        localizer = Localizer(MapDataset.load(map_dir))
        localizer.localize_route(output_dir)

        # Prompt auto-optimization
        choice_opt = input("\nDo you want to run route optimization now? [Y/n]: ").strip().lower()
        if choice_opt in ("", "y", "yes"):
            from src.optimizer import RouteOptimizer
            optimizer = RouteOptimizer()
            optimizer.optimize_route(output_dir)


if __name__ == "__main__":
    main()
