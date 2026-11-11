#!/usr/bin/env python3

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SOURCES = (ROOT / "index.html", ROOT / "style.css", ROOT / "photo.jpg")
OUTPUT = ROOT / "cv.pdf"
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


def source_state():
    return tuple((path.stat().st_mtime_ns, path.stat().st_size) for path in SOURCES)


def wait_until_stable():
    previous = None
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            current = source_state()
        except FileNotFoundError:
            previous = None
            time.sleep(0.5)
            continue
        if current == previous:
            return current
        previous = current
        time.sleep(0.5)
    raise TimeoutError("CV source files did not settle within 30 seconds")


def render_pdf():
    with tempfile.TemporaryDirectory(prefix="cv-pdf-") as temp_dir:
        temp_path = Path(temp_dir)
        pdf_path = temp_path / "cv.pdf"
        profile_path = temp_path / "chrome-profile"
        command = [
            str(CHROME),
            "--headless",
            "--disable-gpu",
            "--no-pdf-header-footer",
            f"--user-data-dir={profile_path}",
            f"--print-to-pdf={pdf_path}",
            SOURCES[0].as_uri(),
        ]
        log_path = temp_path / "chrome.log"
        with log_path.open("w") as chrome_log:
            result = subprocess.run(
                command,
                stdout=subprocess.DEVNULL,
                stderr=chrome_log,
                timeout=120,
                check=False,
            )
        if result.returncode:
            details = log_path.read_text().strip()
            raise RuntimeError(f"Chrome PDF export failed: {details}")
        if not pdf_path.is_file() or not pdf_path.read_bytes().startswith(b"%PDF-"):
            raise RuntimeError("Chrome did not produce a valid PDF")
        return pdf_path.read_bytes()


def generate_pdf():
    if not CHROME.is_file():
        raise FileNotFoundError(f"Chrome was not found at {CHROME}")

    for _ in range(5):
        state = wait_until_stable()
        pdf = render_pdf()
        if source_state() == state:
            with tempfile.NamedTemporaryFile(
                dir=ROOT, prefix=".cv-", suffix=".pdf", delete=False
            ) as output:
                temp_output = Path(output.name)
                output.write(pdf)
            os.replace(temp_output, OUTPUT)
            print(f"Updated {OUTPUT}", flush=True)
            return

    raise RuntimeError("CV sources kept changing during PDF generation")


def watch():
    generate_pdf()
    state = source_state()
    print("Watching CV source files for changes.", flush=True)
    while True:
        time.sleep(1)
        try:
            current = source_state()
        except FileNotFoundError:
            continue
        if current == state:
            continue
        print("CV source changed; regenerating PDF.", flush=True)
        try:
            generate_pdf()
        except (OSError, RuntimeError, TimeoutError, ValueError, subprocess.TimeoutExpired) as error:
            print(f"CV PDF generation failed: {error}", file=sys.stderr, flush=True)
        try:
            state = source_state()
        except FileNotFoundError:
            state = None


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["--watch"]:
            watch()
        elif not sys.argv[1:]:
            generate_pdf()
        else:
            raise ValueError(f"Usage: {Path(__file__).name} [--watch]")
    except (OSError, RuntimeError, TimeoutError, ValueError, subprocess.TimeoutExpired) as error:
        print(f"CV PDF generation failed: {error}", file=sys.stderr, flush=True)
        sys.exit(1)
