"""dashboard.ipynb is committed with no outputs (it may be served to no one, but keep
it PHI-free regardless)."""

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_dashboard_has_no_outputs():
    nb = json.loads((PROJECT_ROOT / "dashboard.ipynb").read_text())
    assert sum(len(c.get("outputs", [])) for c in nb["cells"]) == 0
