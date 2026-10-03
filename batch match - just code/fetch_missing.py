"""
Download any Drive images not yet in data/batches. Uses Drive's direct-download address
(the one a browser uses), which is not rate-limited the way gdown's is. Safe to rerun:
files already present are skipped, and a download only counts if it is a real TIFF.

    python fetch_missing.py
"""

import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent / "data" / "batches"
URL = "https://drive.usercontent.google.com/download?id={id}&export=download&confirm=t"
TIFF_MAGIC = (b"II*\x00", b"MM\x00*")


def fetch(file_id, dest):
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        urllib.request.urlretrieve(URL.format(id=file_id), tmp)
        with open(tmp, "rb") as fh:
            if fh.read(4) not in TIFF_MAGIC:  # Drive answered with an HTML error page
                raise ValueError("not a TIFF")
        tmp.replace(dest)
        return True
    except Exception:
        tmp.unlink(missing_ok=True)
        return False


def main():
    files = json.loads((ROOT / "drive_files.json").read_text(encoding="utf-8-sig"))
    missing = [f for f in files if not (ROOT / f["batch"] / f["name"]).exists()]
    print(f"{len(files) - len(missing)} of {len(files)} files present, {len(missing)} to fetch")
    for f in missing:
        dest = ROOT / f["batch"] / f["name"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        print(f"  {'ok  ' if fetch(f['id'], dest) else 'FAIL'} {f['batch']}/{f['name']}", flush=True)
        time.sleep(1)
    left = sum(not (ROOT / f["batch"] / f["name"]).exists() for f in files)
    print(f"done: {len(files) - left} of {len(files)} present" + (f", {left} still missing" if left else ""))


if __name__ == "__main__":
    main()
