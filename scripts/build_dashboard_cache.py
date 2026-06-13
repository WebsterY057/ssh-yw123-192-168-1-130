#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.backtest_dashboard_data import CACHE_PATH, write_dashboard_cache


def main() -> None:
    payload = write_dashboard_cache(CACHE_PATH)
    print(f"wrote {CACHE_PATH} with {len(payload['strategies'])} strategies")


if __name__ == "__main__":
    main()
