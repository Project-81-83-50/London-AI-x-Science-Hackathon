"""GET4 phase-fraction uncertainty: compatibility shim over `analysis.get4`, the single implementation.

The SEM pipeline imports it as `src.get4` (e.g. `from .get4 import analyse_phase` in src/v3.py); every name
of analysis.get4 is re-exported unchanged. `python -m src.get4 ...` (cwd sem_pipeline/) runs the
analysis.get4 command line; see `python -m analysis.get4 --help` from the repository root, and
analysis/get4/ for the method. Its --project mode reads data/raw/ at the repository root.
"""

import sys
from pathlib import Path

# sem_pipeline/ is run from within the repository (cwd sem_pipeline/), where the repository root, and so the
# `analysis` package, is not on sys.path. It is appended, not prepended, so it never shadows the pipeline's
# own modules.
_REPO_ROOT = str(Path(__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.append(_REPO_ROOT)

from analysis.get4 import *  # noqa: E402, F403
from analysis.get4 import __all__, main  # noqa: E402, F401  (__all__: the same star-export list)

if __name__ == "__main__":
    main()
