"""Repository paths shared by Officina and its flavors."""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
AUTOSEG_DIR = REPO_ROOT / 'flavors' / 'autoseg'
