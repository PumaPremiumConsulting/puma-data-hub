from __future__ import annotations

import sys
from pathlib import Path

from mangum import Mangum

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from main import app, init_db  # noqa: E402

init_db()
handler = Mangum(app, lifespan="auto")
