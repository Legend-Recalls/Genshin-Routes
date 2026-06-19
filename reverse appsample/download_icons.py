"""
Download all marker icons from the AppSample CDN.
Icons are used by the viewer to display feature markers on the map.
"""
import os
import time
import ssl
import urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

BASE_DIR = Path(__file__).parent
ICONS_DIR = BASE_DIR / "icons"
CDN = "https://game-cdn.appsample.com/gim/markers"

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
            time.sleep(0.2)
        except Exception:
            if attempt == retries - 1:
                return None
            time.sleep(0.2)
    return None


def download_icon(type_code):
    dest = ICONS_DIR / f"{type_code}.png"
    if dest.exists() and dest.stat().st_size > 0:
        return "skip"
    url = f"{CDN}/{type_code}.png?v=3"
    data = fetch(url)
    if data and len(data) > 100:
        dest.write_bytes(data)
        return "ok"
    return "fail"


def main():
    ICONS_DIR.mkdir(parents=True, exist_ok=True)

    features_path = BASE_DIR / "features.json"
    with open(features_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    types = set()
    for feat in raw.get("features", []):
        types.add(feat["type"])

    print(f"Downloading {len(types)} marker icons...")
    tasks = sorted(types)

    ok = 0
    skip = 0
    fail = 0
    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(download_icon, tasks))
    ok = results.count("ok")
    skip = results.count("skip")
    fail = results.count("fail")

    print(f"  {ok} downloaded, {skip} cached, {fail} failed")
    print(f"  Icons saved to {ICONS_DIR}")


if __name__ == "__main__":
    import json
    main()
