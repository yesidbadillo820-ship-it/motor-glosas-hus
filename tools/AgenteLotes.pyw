"""Doble clic aquí para abrir el Agente de Lotes (ventana, sin consola)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agente_lotes_gui import main  # noqa: E402

main()
