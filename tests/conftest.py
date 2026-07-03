import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["NEXUSLEAD_DB"] = str(ROOT / "data" / "test_nexuslead.db")

test_db = Path(os.environ["NEXUSLEAD_DB"])
if test_db.exists():
    test_db.unlink()
