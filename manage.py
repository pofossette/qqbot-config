#!/usr/bin/env python3
from __future__ import annotations

import runpy
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


if __name__ == "__main__":
    namespace = runpy.run_path(str(SCRIPTS_DIR / "manage.py"))
    raise SystemExit(namespace["main"]())
