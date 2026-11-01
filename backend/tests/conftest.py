"""Always isolate tests from a real account database and local secrets."""

import os
import tempfile
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///" + str(
    Path(tempfile.mkdtemp(prefix="acadsync-tests-")) / "test.db"
)
os.environ["FRONTEND_URL"] = "http://localhost:3000"
os.environ["DEMO_ENABLED"] = "true"
