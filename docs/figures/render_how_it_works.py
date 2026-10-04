"""Render docs/figures/how-it-works.html to PNG.

Writes ``how-it-works.png`` next to the HTML source. Run with
``uv run --with pillow python docs/figures/render_how_it_works.py``.

Uses headless Google Chrome (override the path with ``CHROME_PATH``) and Pillow
to trim the white margin. Output is 2.5x the 1600 px layout width, marked as
300 DPI.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "how-it-works.html"
DEFAULT_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
SCALE = 2.5
WINDOW = (1600, 1400)
PAD = 28
TIMEOUT_SECONDS = 120
OUTPUT = HERE / "how-it-works.png"


def _screenshot(url: str, raw_path: Path) -> None:
    chrome = os.environ.get("CHROME_PATH", DEFAULT_CHROME)
    profile = Path(tempfile.mkdtemp(prefix="onboard-figure-chrome-"))
    command = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--no-first-run",
        "--disable-extensions",
        f"--user-data-dir={profile}",
        f"--force-device-scale-factor={SCALE}",
        f"--window-size={WINDOW[0]},{WINDOW[1]}",
        "--virtual-time-budget=8000",
        f"--screenshot={raw_path}",
        url,
    ]
    # Headless Chrome on macOS can write the screenshot and then never exit,
    # so wait for the file rather than for the process.
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if raw_path.exists() and raw_path.stat().st_size > 0:
                time.sleep(2)
                return
            if process.poll() is not None and not raw_path.exists():
                raise RuntimeError(f"Chrome exited without writing {raw_path}")
            time.sleep(0.5)
        raise TimeoutError(f"Chrome did not write {raw_path} within {TIMEOUT_SECONDS}s")
    finally:
        process.kill()
        shutil.rmtree(profile, ignore_errors=True)


def _trim(raw_path: Path, out_path: Path) -> tuple[int, int]:
    image = Image.open(raw_path).convert("RGB")
    background = Image.new("RGB", image.size, (255, 255, 255))
    bbox = ImageChops.difference(image, background).getbbox()
    if bbox is None:
        raise RuntimeError(f"{raw_path} is blank")
    if bbox[3] >= image.height - PAD:
        raise RuntimeError("Figure reaches the bottom of the window; increase WINDOW height")
    cropped = image.crop(
        (
            max(bbox[0] - PAD, 0),
            max(bbox[1] - PAD, 0),
            min(bbox[2] + PAD, image.width),
            min(bbox[3] + PAD, image.height),
        )
    )
    cropped.save(out_path, optimize=True, dpi=(300, 300))
    return cropped.size


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        raw_path = Path(tmp) / "raw.png"
        _screenshot(SOURCE.as_uri(), raw_path)
        width, height = _trim(raw_path, OUTPUT)
        print(f"wrote {OUTPUT.relative_to(HERE.parent.parent)} ({width} x {height})")


if __name__ == "__main__":
    main()
