"""Camada de integração do AUTOSEG com o núcleo genérico Workaholic."""
import sys
from pathlib import Path

WORKAHOLIC_SRC = Path(__file__).resolve().parents[2] / "workaholic" / "src"
if str(WORKAHOLIC_SRC) not in sys.path:
    sys.path.insert(0, str(WORKAHOLIC_SRC))
