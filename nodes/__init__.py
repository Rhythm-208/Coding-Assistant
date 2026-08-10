# nodes package
# Ensure APP/ is on sys.path so node modules can do `from State import ...`
import sys
from pathlib import Path

_app_dir = str(Path(__file__).resolve().parent.parent)
if _app_dir not in sys.path:
    sys.path.insert(0, _app_dir)
