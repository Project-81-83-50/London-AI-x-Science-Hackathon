"""Compatibility entry point for the shared research-grounded explanation service.

Run from sem_pipeline with python -m website.agents <run folder>. The backend owns facts decoding,
Corrective RAG, all four agent roles, validation, job coordination and report publication.
Credentials remain in sem_pipeline/.env or the server environment.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # sem_pipeline/


def main(run: str) -> None:
    """Delegate one run to the same report engine used by the website."""
    sys.path.insert(0, str(ROOT.parent / "backend"))
    from app.research.cli import run_report

    try:
        result = run_report(Path(run))
        print(json.dumps(result, ensure_ascii=False))
        if result.get("status") not in {"done", "running"}:
            raise SystemExit(1)
    except Exception as e:  # noqa: BLE001 - shown on the page
        print(
            f"Report service unavailable ({type(e).__name__}). Check API configuration and backend dependencies.",
            file=sys.stderr,
        )
        raise SystemExit(1) from e


if __name__ == "__main__":
    main(sys.argv[1])
