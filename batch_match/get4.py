"""GET4 phase-fraction uncertainty: compatibility shim over `analysis.get4`, the single implementation.

batch_classifier.py and the scripts in experiments/ import this module as top-level `get4` (batch_match/ on
sys.path). Every name of analysis.get4 is re-exported unchanged, plus the older name `segment_bse` for
`segment_intensity_classes`. Running it is running the analysis.get4 command line; from batch_match/:

    python get4.py data/batches/Batch_1 --out out/get4/Batch_1          # one batch -> per-image + batch JSON/PNG
    python get4.py IMAGES... --baseline out/get4/Batch_1/batch_uncertainty.json --out out/get4/Batch_2
    python get4.py --compare out/get4/Batch_1/batch_uncertainty.json out/get4/Batch_2/batch_uncertainty.json

See `python -m analysis.get4 --help` (from the repository root) for every option, and analysis/get4/ for
the method.
"""

import sys
from pathlib import Path

# batch_match/ is also used on its own (`python get4.py`, `import get4` with batch_match/ on sys.path), where
# the repository root, and so the `analysis` package, is not importable yet. It is appended, not prepended,
# so it never shadows modules of batch_match/ itself.
_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.append(_REPO_ROOT)

from analysis.get4 import *  # noqa: E402, F403
from analysis.get4 import __all__ as _ANALYSIS_ALL  # noqa: E402
from analysis.get4 import main, segment_intensity_classes  # noqa: E402

segment_bse = segment_intensity_classes  # name used by batch_classifier.py and the experiments

__all__ = [*_ANALYSIS_ALL, "segment_bse"]

if __name__ == "__main__":
    main()
