"""
AppSample Genshin Map Downloader
Downloads tiles, overlays, and metadata from the appsample CDN.
Mirrors the folder structure of the existing reverse appsample/ data.
"""
import json
import os
import sys
import time
import hashlib
import urllib.request
import ssl
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_DIR = Path(__file__).parent
CDN = "https://game-cdn.appsample.com/gim"
OVERLAYS_DIR = BASE_DIR / "overlays"
TILES_DIR = BASE_DIR / "tiles"

# All underground maps from the JS config
UNDERGROUND_MAPS = {
    "chasm": {"cdn": "map-chasm/v0", "max_zoom": 13},
    "enkanomiya": {"cdn": "map-enkanomiya/v26", "max_zoom": 13},
    "isles": {"cdn": "map-isles/v28rc4", "max_zoom": 13},
    "veluriyam-mirage": {"cdn": "map-veluriyam-mirage/rc2", "max_zoom": 13},
    "sea-of-bygone-eras": {"cdn": "map-bygone-eras/v1", "max_zoom": 13},
    "simulanka": {"cdn": "map-simulanka/rc2", "max_zoom": 13},
    "temple-of-space": {"cdn": "map-temple-of-space/rc1", "max_zoom": 13},
    "ancient-sacred": {"cdn": "map-ancient-sacred/v2", "max_zoom": 12},
}

# Teyvat tile bounds from JS config
# maxY extended by 1 for zoom 15 to capture 3 real tiles at y=58
# that exist on CDN but fall outside the JS config's maxY:57
TEYVAT_TILE_BOUNDS = {
    13: {"minX": -16, "maxX": 15, "minY": -16, "maxY": 14},
    15: {"minX": -64, "maxX": 63, "minY": -64, "maxY": 58},
}

# Underground tile bounds (all use -16..15 for x and y at zoom 13)
UNDERGROUND_BOUNDS = {"minX": -16, "maxX": 15, "minY": -16, "maxY": 15}

ssl_ctx = ssl.create_default_context()
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def fetch(url, retries=2, timeout=15):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            resp = urllib.request.urlopen(req, context=ssl_ctx, timeout=timeout)
            return resp.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if attempt == retries - 1:
                return None
            time.sleep(0.3)
        except Exception:
            if attempt == retries - 1:
                return None
            time.sleep(0.3)
    return None


def download_file(url, dest):
    if dest.exists() and dest.stat().st_size > 0:
        return "skip"
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = fetch(url)
    if data and len(data) > 0:
        dest.write_bytes(data)
        return "ok"
    return "empty"


def download_tile(args):
    url, dest = args
    return download_file(url, dest)


def load_black_tiles():
    url = f"{CDN}/map-teyvat/v65-rc1/black-tile.json"
    data = json.loads(fetch(url))
    result = {}
    for zoom_str, tiles_str in data.get("data", {}).items():
        zoom = int(zoom_str)
        tiles = set()
        for t in tiles_str.split(","):
            parts = t.split("_")
            if len(parts) == 2:
                tiles.add((int(parts[0]), int(parts[1])))
        result[zoom] = tiles
    return result


def download_teyvat_tiles(zooms=None):
    if zooms is None:
        zooms = [13, 15]
    
    print("Fetching black-tile.json...")
    black_tiles = load_black_tiles()
    
    total = 0
    downloaded = 0
    skipped = 0
    errors = 0
    
    for zoom in zooms:
        bounds = TEYVAT_TILE_BOUNDS.get(zoom)
        if not bounds:
            print(f"  No bounds for zoom {zoom}, skipping")
            continue
        
        tasks = []
        for x in range(bounds["minX"], bounds["maxX"] + 1):
            for y in range(bounds["minY"], bounds["maxY"] + 1):
                if (x, y) in black_tiles.get(zoom, set()):
                    skipped += 1
                    continue
                url = f"{CDN}/map-teyvat/v65-rc1/{zoom}/tile-{x}_{y}.jpg"
                dest = TILES_DIR / str(zoom) / f"tile-{x}_{y}.jpg"
                tasks.append((url, dest))
        
        total += len(tasks)
        print(f"  Zoom {zoom}: {len(tasks)} tiles to download ({skipped} black tiles skipped)")
        
        with ThreadPoolExecutor(max_workers=16) as pool:
            results = list(pool.map(download_tile, tasks))
        
        downloaded += results.count("ok")
        errors += len(results) - results.count("ok") - results.count("skip")
    
    return {"total": total, "downloaded": downloaded, "skipped": skipped, "errors": errors}


def download_underground_tiles():
    total = 0
    downloaded = 0
    errors = 0
    
    for map_name, config in UNDERGROUND_MAPS.items():
        tasks = []
        
        # Only download zoom 13 (matching existing data)
        zoom = 13
        for x in range(UNDERGROUND_BOUNDS["minX"], UNDERGROUND_BOUNDS["maxX"] + 1):
            for y in range(UNDERGROUND_BOUNDS["minY"], UNDERGROUND_BOUNDS["maxY"] + 1):
                url = f"{CDN}/{config['cdn']}/{zoom}/tile-{x}_{y}.jpg"
                dest = TILES_DIR / "underground" / map_name / str(zoom) / f"tile-{x}_{y}.jpg"
                tasks.append((url, dest))
        
        total += len(tasks)
        print(f"  {map_name}: {len(tasks)} tiles at zoom 13")
        
        with ThreadPoolExecutor(max_workers=10) as pool:
            results = list(pool.map(download_tile, tasks))
        
        ok = results.count("ok")
        skip = results.count("skip")
        downloaded += ok
        errors += len(results) - ok - skip
        print(f"    -> {ok} new, {skip} existing")
    
    return {"total": total, "downloaded": downloaded, "errors": errors}


def fetch_overlays_from_website():
    """Extract overlay data directly from the appsample website JS bundles."""
    import re
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  Playwright not installed, cannot fetch overlays from website")
        return None
    
    print("  Fetching overlay data from website JS...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        js_contents = {}
        
        def on_response(response):
            url = response.url
            if 'appsample.com' in url and '.js' in url and 'chunks' in url:
                try:
                    body = response.body().decode('utf-8', errors='replace')
                    name = url.split('/')[-1].split('?')[0]
                    js_contents[name] = body
                except:
                    pass
        
        page.on('response', on_response)
        page.goto('https://genshin-impact-map.appsample.com/', timeout=30000)
        page.wait_for_timeout(5000)
        browser.close()
    
    # Find JSON.parse calls with overlay data
    for name, content in js_contents.items():
        pattern = r"JSON\.parse\('(\{.*?\})'\)"
        for m in re.findall(pattern, content):
            try:
                data = json.loads(m)
                if isinstance(data, dict):
                    for key, val in data.items():
                        if isinstance(val, list) and len(val) > 10 and isinstance(val[0], dict) and 'img' in val[0]:
                            return val
            except json.JSONDecodeError:
                pass
    
    return None


def download_overlays():
    overlay_url = "https://game-cdn.appsample.com/gim/overlays/"
    downloaded = 0
    errors = 0
    
    # Try loading from local file first, then fetch from website
    all_overlays = None
    for candidate in [
        BASE_DIR.parent / "overlays_from_js.json",
        Path(__file__).parent.parent / "overlays_from_js.json",
    ]:
        if candidate.exists():
            with open(candidate, "r", encoding="utf-8") as f:
                all_overlays = json.load(f)
            break
    
    if all_overlays is None:
        all_overlays = fetch_overlays_from_website()
        if all_overlays is None:
            print("  Could not fetch overlay data")
            return {"total": 0, "downloaded": 0, "errors": 0}
    
    # Filter to CDN-hosted overlays
    teyvat_overlays = [o for o in all_overlays if "game-cdn.appsample.com/gim/overlays/" in o.get("img", "")]
    
    print(f"  {len(teyvat_overlays)} teyvat overlays to download")
    
    for ov in teyvat_overlays:
        img_url = ov.get("img", "")
        if not img_url:
            continue
        ov_id = ov.get("id", 0)
        dest = OVERLAYS_DIR / f"overlay_{ov_id}.png"
        result = download_file(img_url, dest)
        if result == "ok":
            downloaded += 1
        elif result == "empty":
            errors += 1
    
    return {"total": len(teyvat_overlays), "downloaded": downloaded, "errors": errors}


def save_overlay_metadata():
    all_overlays = None
    for candidate in [
        BASE_DIR.parent / "overlays_from_js.json",
        Path(__file__).parent.parent / "overlays_from_js.json",
    ]:
        if candidate.exists():
            with open(candidate, "r", encoding="utf-8") as f:
                all_overlays = json.load(f)
            break
    
    if all_overlays is None:
        all_overlays = fetch_overlays_from_website()
        if all_overlays is None:
            print("  Could not fetch overlay data for metadata")
            return
    
    # Build metadata matching existing format
    metadata = []
    for ov in all_overlays:
        ov_id = ov.get("id", 0)
        if "game-cdn.appsample.com/gim/overlays/" not in ov.get("img", ""):
            continue
        
        bounds = ov.get("bounds", {})
        # Compute tile bounds at zoom 13 and 15
        entry = {
            "id": ov_id,
            "name": ov.get("name", ""),
            "sid": ov.get("sid", 0),
            "path": f"overlays\\overlay_{ov_id}.png",
            "image_url": ov.get("img", ""),
            "bounds": bounds,
        }
        
        # Compute tile bounds from lat/lng
        for zoom in [13, 15]:
            half = 2 ** (zoom - 1)
            total = 2 ** zoom
            
            north = bounds.get("north", 0)
            south = bounds.get("south", 0)
            east = bounds.get("east", 0)
            west = bounds.get("west", 0)
            
            import math
            google_x_west = (west + 180) / 360 * total
            google_x_east = (east + 180) / 360 * total
            
            north_rad = north * math.pi / 180
            south_rad = south * math.pi / 180
            google_y_north = (1 - math.log(math.tan(north_rad) + 1 / math.cos(north_rad)) / math.pi) / 2 * total
            google_y_south = (1 - math.log(math.tan(south_rad) + 1 / math.cos(south_rad)) / math.pi) / 2 * total
            
            game_x_west = google_x_west - half
            game_x_east = google_x_east - half
            game_y_north = half - google_y_north - 1
            game_y_south = half - google_y_south - 1
            
            entry[f"tile_bounds_{zoom}"] = {
                "min_x": min(game_x_west, game_x_east),
                "min_y": min(game_y_north, game_y_south),
                "max_x": max(game_x_west, game_x_east),
                "max_y": max(game_y_north, game_y_south),
            }
        
        metadata.append(entry)
    
    dest = BASE_DIR / "overlay_metadata.json"
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    print(f"  Saved overlay_metadata.json ({len(metadata)} entries)")


def main():
    print("=" * 60)
    print("  AppSample Genshin Map Downloader")
    print("=" * 60)
    
    start = time.time()
    
    # 1. Teyvat tiles
    print("\n[1/4] Downloading Teyvat (overworld) tiles...")
    teyvat = download_teyvat_tiles()
    print(f"  Result: {teyvat}")
    
    # 2. Underground tiles
    print("\n[2/4] Downloading underground tiles...")
    underground = download_underground_tiles()
    print(f"  Result: {underground}")
    
    # 3. Overlays
    print("\n[3/4] Downloading overlay images...")
    overlays = download_overlays()
    print(f"  Result: {overlays}")
    
    # 4. Overlay metadata
    print("\n[4/4] Saving overlay metadata...")
    save_overlay_metadata()
    
    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.1f}s")
    
    # Summary
    total_tiles = teyvat["total"] + underground["total"]
    total_dl = teyvat["downloaded"] + underground["downloaded"]
    total_err = teyvat["errors"] + underground["errors"]
    print(f"\nSummary:")
    print(f"  Tiles: {total_dl} downloaded, {total_err} errors, {teyvat['skipped']} black-tile skips")
    print(f"  Overlays: {overlays['downloaded']}/{overlays['total']}")
    print(f"  Total files: {total_dl + overlays['downloaded']}")


if __name__ == "__main__":
    main()
