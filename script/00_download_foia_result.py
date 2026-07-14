"""Step 0: download the FOIA response zip from MuckRock and extract it.

Downloads 2-3-26_MR201972.zip (509 MiB) to the project root, verifies its
md5 checksum, and extracts its contents into raw-response/. If the zip is
already present, the download is skipped; verification and extraction
always run, so the end state is always the same:

    raw-response/2-3-26 MR201972.pdf             (cover letter)
    raw-response/Flock Data/Event Logs/          (1 file)
    raw-response/Flock Data/Organization Audit/  (25 files)
    raw-response/Flock Data/Network Audit/       (25 files)

Run from anywhere:  python3 script/00_download_foia_result.py
"""

import hashlib
import sys
import urllib.request
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ZIP_URL = "https://cdn.muckrock.com/foia_files/2026/02/26/2-3-26_MR201972.zip"
ZIP_FILE = PROJECT_ROOT / "2-3-26_MR201972.zip"
ZIP_MD5 = "facee13f82244fd5e7c2180bc0d3899b"
# Everything in the zip lives under this folder; it is stripped on
# extraction so raw-response/ holds the PDF and "Flock Data/" directly.
ZIP_PREFIX = "2-3-26 MR201972/"
RAW_DIR = PROJECT_ROOT / "raw-response"


def main():
    if ZIP_FILE.exists():
        print(f"{ZIP_FILE.name} already present, skipping download")
    else:
        print(f"Downloading {ZIP_URL} (509 MiB) ...", flush=True)
        urllib.request.urlretrieve(ZIP_URL, ZIP_FILE)
        print("  done")

    print("Verifying md5 ...", flush=True)
    md5 = hashlib.md5()
    with open(ZIP_FILE, "rb") as f:
        while chunk := f.read(1 << 20):
            md5.update(chunk)
    if md5.hexdigest() != ZIP_MD5:
        print(f"ERROR: md5 mismatch.\n  expected {ZIP_MD5}\n  got      {md5.hexdigest()}\n"
              "The download is corrupt or the file changed upstream. "
              "Delete the zip and retry.", file=sys.stderr)
        sys.exit(1)
    print(f"  OK ({ZIP_MD5})")

    print(f"Extracting into {RAW_DIR} ...", flush=True)
    extracted = 0
    with zipfile.ZipFile(ZIP_FILE) as zf:
        for entry in zf.namelist():
            if not entry.startswith(ZIP_PREFIX) or entry.endswith("/"):
                continue
            relative = entry[len(ZIP_PREFIX):]
            target = RAW_DIR / relative
            if not target.resolve().is_relative_to(RAW_DIR.resolve()):
                print(f"ERROR: unsafe path in zip: {entry}", file=sys.stderr)
                sys.exit(1)
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(entry) as src, open(target, "wb") as dst:
                while chunk := src.read(1 << 20):
                    dst.write(chunk)
            extracted += 1
    print(f"  {extracted} files extracted")


if __name__ == "__main__":
    main()
