#!/usr/bin/env python3
"""Launcher kept for continuity with the original MVP: `python3 app.py`."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tes.ui.app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
