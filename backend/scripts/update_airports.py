"""Download the latest OpenFlights airports.dat and overwrite the local copy.

Run manually (or via cron) when a refresh is needed:
    python scripts/update_airports.py

Source: https://github.com/jpatokal/openflights
"""

import sys
import urllib.request
from pathlib import Path

SOURCE_URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airports.dat"
TARGET = Path(__file__).parent.parent / "app" / "data" / "airports.dat"


def main() -> int:
    print(f"Fetching {SOURCE_URL} ...")
    try:
        with urllib.request.urlopen(SOURCE_URL, timeout=30) as resp:
            data = resp.read()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_bytes(data)
    lines = data.count(b"\n")
    kb = len(data) / 1024
    print(f"OK — wrote {TARGET} ({kb:.1f} KB, {lines} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
