"""Isolate the hybrid engine per test run (never touch the real ~/.agentdrift)."""

import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="agentdrift-test-"))
os.environ.setdefault("AGENTDRIFT_DATA_DIR", str(_tmp))
