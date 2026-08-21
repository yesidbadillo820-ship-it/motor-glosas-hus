"""Permite correr el sistema con ``python -m icfes``."""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
