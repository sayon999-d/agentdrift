"""Isolate the hybrid engine per test run in a temporary directory."""

import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="agentdrift-test-"))
os.environ.setdefault("AGENTDRIFT_DATA_DIR", str(_tmp))
