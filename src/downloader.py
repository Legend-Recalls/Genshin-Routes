import logging
import subprocess
from pathlib import Path

from config import VIDEOS_DIR

logger = logging.getLogger(__name__)


def is_local_file(path: str) -> bool:
    p = Path(path)
    return p.exists() and p.suffix.lower() in {".mp4", ".mkv", ".webm", ".avi"}


def download_video(url: str) -> Path:
    if is_local_file(url):
        local_path = Path(url)
        logger.info("Local file detected: %s", local_path)
        return local_path

    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)

    output_template = str(VIDEOS_DIR / "%(title)s.%(ext)s")

    cmd = [
        "yt-dlp",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", output_template,
        "--no-playlist",
        "--extractor-args", "youtube:player_client=web",
        "--remote-components", "ejs:github",
        url,
    ]

    logger.info("Downloading video: %s", url)
    print("Downloading video...")

    before = set(VIDEOS_DIR.glob("*.mp4"))
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        msg = f"yt-dlp failed:\n{result.stderr}"
        logger.error(msg)
        raise RuntimeError(msg)

    after = set(VIDEOS_DIR.glob("*.mp4"))
    new_files = after - before

    if new_files:
        f = sorted(new_files, key=lambda p: p.stat().st_mtime, reverse=True)[0]
        logger.info("Downloaded: %s", f)
        print(f"Downloaded: {f.name}")
        return f

    raise RuntimeError("Download completed but no new MP4 file found in videos/")
