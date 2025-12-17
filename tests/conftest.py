import sys
from pathlib import Path

# Ensure repository root is on the import path so "app" package is discoverable
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
