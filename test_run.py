import logging
import sys
from pathlib import Path

# Make repo root + route_explorer/ importable
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from route_explorer.src.localizer import Localizer
from route_explorer.src.optimizer import RouteOptimizer
from route_explorer.src.map_dataset import MapDataset
from route_explorer.src.benchmark import BenchmarkReport
from route_explorer.src.exporter import RouteExporter

logging.basicConfig(level=logging.INFO)

BASE_DIR = Path(__file__).parent
map_dir = BASE_DIR / "maps" / "surface"
route_dir = BASE_DIR / "output" / "test_clip"

dataset = MapDataset.load(map_dir)
loc = Localizer(dataset)

benchmark = BenchmarkReport()
loc.localize_route(route_dir, benchmark=benchmark)

opt = RouteOptimizer()
opt.optimize_route(route_dir)

exporter = RouteExporter(route_dir)
export_dir = route_dir / "exports"
exporter.export_all(export_dir)
print(f"Exports written to: {export_dir}")
