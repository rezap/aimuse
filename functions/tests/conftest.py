import sys
from pathlib import Path

# Always test against the backend source, not a stale copy left in functions/aimuse by
# scripts/dev.sh or scripts/e2e.sh (that copy exists only for the emulator and deploys).
_BACKEND_SRC = Path(__file__).resolve().parents[2] / "backend" / "src"
if _BACKEND_SRC.is_dir():
    sys.path.insert(0, str(_BACKEND_SRC))
