import http.server
import socketserver
import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
MAPS_DIR = BASE_DIR.parent / "maps"
SURFACE_DIR = MAPS_DIR / "surface"

ROUTE_OUTPUT_DIR = BASE_DIR.parent / "output"

# Phase 1: viewer serves from surface map only (multi-map serving comes later)
TILES_DIR = SURFACE_DIR / "tiles"
OVERLAYS_DIR = SURFACE_DIR / "overlays"

HTML_PATH = BASE_DIR / "viewer.html"

_tile_mem_cache = {}
_overlay_mem_cache = {}
_viewer_html = None
_markers_data = None
_database_data = None
_route_cache = {}      # {route_name: {"route": bytes, "optimized": bytes | None}}
_minimap_cache = {}    # {"route_name/filename": bytes}
_title_cache = {}      # {"route_name/filename": bytes}

def preload():
    global _viewer_html, _markers_data, _database_data
    print("Pre-loading assets into memory...")

    # Viewer HTML is loaded dynamically on request
    # with open(BASE_DIR / "viewer.html", "rb") as f:
    #     _viewer_html = f.read()

    # Markers and Database were old scraping files, removed.

    # Skip tile preload — 7000 tiles take too long. Serve from disk on-demand.
    print(f"  Tiles directory: {TILES_DIR} (served from disk)")

    ocount = 0
    if OVERLAYS_DIR.exists():
        for ov_file in OVERLAYS_DIR.glob("overlay_*.png"):
            with open(ov_file, "rb") as f:
                _overlay_mem_cache[ov_file.name] = f.read()
            ocount += 1
    print(f"  Cached {ocount} overlays ({sum(len(v) for v in _overlay_mem_cache.values()) / 1024 / 1024:.1f} MB)")

    # Skip caching routes in memory so they can update dynamically
    # Routes will be read from disk on every request.
    print(f"  Routes directory: {ROUTE_OUTPUT_DIR} (served from disk)")
    
    # We still cache minimaps since there are thousands of them
    mcount = 0
    tcount = 0
    if ROUTE_OUTPUT_DIR.exists():
        for route_dir in ROUTE_OUTPUT_DIR.iterdir():
            if not route_dir.is_dir():
                continue
            minimaps_dir = route_dir / "minimaps"
            if minimaps_dir.exists():
                for img_file in sorted(minimaps_dir.glob("*.png")):
                    cache_key = route_dir.name + "/" + img_file.name
                    with open(img_file, "rb") as f:
                        _minimap_cache[cache_key] = f.read()
                    mcount += 1
            titles_dir = route_dir / "titles"
            if titles_dir.exists():
                for img_file in sorted(titles_dir.glob("*.png")):
                    cache_key = route_dir.name + "/" + img_file.name
                    with open(img_file, "rb") as f:
                        _title_cache[cache_key] = f.read()
                    tcount += 1
    print(f"  Cached {mcount} minimaps ({sum(len(v) for v in _minimap_cache.values()) / 1024 / 1024:.1f} MB)")
    print(f"  Cached {tcount} title crops ({sum(len(v) for v in _title_cache.values()) / 1024 / 1024:.1f} MB)")
    print("  Ready!")

class TileHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            with open(HTML_PATH, "rb") as f:
                html_data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", len(html_data))
            self.end_headers()
            self.wfile.write(html_data)
            return



        if self.path.startswith("/tiles/"):
            parts = self.path.split("/")
            if len(parts) >= 4:
                zoom = parts[2]
                tile_name = parts[3]
                cache_key = zoom + "/" + tile_name
                data = _tile_mem_cache.get(cache_key)
                if not data:
                    # Load from disk on-demand
                    tile_path = TILES_DIR / zoom / tile_name
                    if tile_path.exists():
                        with open(tile_path, "rb") as f:
                            data = f.read()
                        _tile_mem_cache[cache_key] = data
                if data:
                    self.send_response(200)
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Cache-Control", "public, max-age=604800, immutable")
                    self.send_header("Content-Length", len(data))
                    self.end_headers()
                    self.wfile.write(data)
                    return
            self.send_response(204)
            self.end_headers()
            return

        if self.path.startswith("/overlays/"):
            ov_name = self.path.split("/")[-1]
            data = _overlay_mem_cache.get(ov_name)
            if data:
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Cache-Control", "public, max-age=604800, immutable")
                self.send_header("Content-Length", len(data))
                self.end_headers()
                self.wfile.write(data)
                return
            self.send_response(404)
            self.end_headers()
            return

        # --- Route endpoints ---
        if self.path == "/tile_database.json":
            # Phase 1: serve tile database for surface map only (viewer.html expects this)
            db_path = SURFACE_DIR / "tile_database.json"
            if db_path.exists():
                data = db_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", len(data))
                self.end_headers()
                self.wfile.write(data)
                return
            self.send_response(404)
            self.end_headers()
            return

        if self.path == "/routes":
            routes_list = []
            if ROUTE_OUTPUT_DIR.exists():
                for route_dir in ROUTE_OUTPUT_DIR.iterdir():
                    if not route_dir.is_dir():
                        continue
                    if (route_dir / "route.json").exists():
                        routes_list.append({
                            "name": route_dir.name,
                            "has_optimized": (route_dir / "optimized_route.json").exists(),
                        })
            data = json.dumps(routes_list).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(data))
            self.end_headers()
            self.wfile.write(data)
            return

        if self.path.startswith("/route/"):
            parts = self.path.split("/")
            # /route/<name>/route.json or /route/<name>/optimized_route.json
            if len(parts) >= 4 and parts[3] in ("route.json", "optimized_route.json"):
                route_name = parts[2]
                file_path = ROUTE_OUTPUT_DIR / route_name / parts[3]
                if file_path.exists():
                    with open(file_path, "rb") as f:
                        data = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", len(data))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                self.send_response(404)
                self.end_headers()
                return

            # /route/<name>/exports/<filename>
            if len(parts) >= 5 and parts[3] == "exports":
                route_name = parts[2]
                filename = parts[4]
                exports_dir = ROUTE_OUTPUT_DIR / route_name / "exports"
                file_path = exports_dir / filename
                if file_path.exists():
                    data = file_path.read_bytes()
                    # content-type based on extension
                    if filename.endswith(".json") or filename.endswith(".geojson"):
                        ctype = "application/json"
                    elif filename.endswith(".csv"):
                        ctype = "text/csv"
                    else:
                        ctype = "application/octet-stream"
                    self.send_response(200)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Length", len(data))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                self.send_response(404)
                self.end_headers()
                return

            # /route/<name>/minimaps/<filename>
            if len(parts) >= 5 and parts[3] == "minimaps":
                route_name = parts[2]
                filename = parts[4]
                cache_key = route_name + "/" + filename
                data = _minimap_cache.get(cache_key)
                if data:
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Cache-Control", "public, max-age=86400")
                    self.send_header("Content-Length", len(data))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                self.send_response(404)
                self.end_headers()
                return

            # /route/<name>/titles/<filename>
            if len(parts) >= 5 and parts[3] == "titles":
                route_name = parts[2]
                filename = parts[4]
                cache_key = route_name + "/" + filename
                data = _title_cache.get(cache_key)
                if data:
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Cache-Control", "public, max-age=86400")
                    self.send_header("Content-Length", len(data))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                # Fallback to disk
                titles_dir = ROUTE_OUTPUT_DIR / route_name / "titles"
                file_path = titles_dir / filename
                if file_path.exists():
                    data = file_path.read_bytes()
                    _title_cache[cache_key] = data
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Cache-Control", "public, max-age=86400")
                    self.send_header("Content-Length", len(data))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                self.send_response(404)
                self.end_headers()
                return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        pass

class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

if __name__ == "__main__":
    import sys
    preload()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9090
    server = ThreadedHTTPServer(("127.0.0.1", port), TileHandler)
    print(f"Map viewer running at http://127.0.0.1:{port}")
    server.serve_forever()
