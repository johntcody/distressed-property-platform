"""Make services/distress-score importable despite the hyphenated directory name."""

import importlib.util
import sys
from pathlib import Path

_service_dir = Path(__file__).parent.parent.parent / "services" / "distress-score"


def _load(module_name: str, file_name: str):
    if module_name in sys.modules:
        return
    spec = importlib.util.spec_from_file_location(module_name, _service_dir / file_name)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)


# Load scorer first (no intra-service deps)
_load("distress_score_scorer", "scorer.py")

# Expose under the name the test uses
sys.modules.setdefault(
    "services.distress_score",
    type(sys)("services.distress_score"),
)
sys.modules["services.distress_score.scorer"] = sys.modules["distress_score_scorer"]
