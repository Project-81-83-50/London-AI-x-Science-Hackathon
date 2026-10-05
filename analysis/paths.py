"""Repository folders used by the analysis modules: one definition of every input and output location.

Each analysis module keeps its historical module-level names as aliases of these (for example
``analysis.fields.RAW = paths.RAW_DIR``) and reads its own alias at call time, so code and tests that read or
reassign ``module.RAW`` / ``module.OUT`` keep working. Point a module somewhere else by reassigning its alias,
not the constant here.

There is deliberately no environment-variable override: SEM_RAW_DATA_DIR already tells the test suite where to
look for real images (tests/conftest.py), and analysis.classify reports reference images relative to the
repository root, which a raw-data folder outside the repository would break.

    python -m analysis.paths     # print the resolved folders
"""

import argparse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Inputs
RAW_DIR = REPO_ROOT / "data" / "raw"  # batch_N/ (reference batches) and unknown/
RAW_UNKNOWN_DIR = RAW_DIR / "unknown"
SEM_PIPELINE_DIR = REPO_ROOT / "sem_pipeline"  # the v3 SEM pipeline (analysis.v3_unknown, analysis.v3_report)
BATCH_MATCH_CODE_DIR = REPO_ROOT / "batch_match"  # the batch-match classifier (analysis.batch_match)

# Outputs (Git-ignored, like the raw data)
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
FIELDS_DIR = PROCESSED_DIR / "fields"  # analysis.fields
KPI_DIR = PROCESSED_DIR / "batch_kpis"  # analysis.kpis
CLASSIFICATION_DIR = PROCESSED_DIR / "classification"  # analysis.classify
BATCH_MATCH_DIR = PROCESSED_DIR / "batch_match"  # analysis.batch_match
GET4_DIR = PROCESSED_DIR / "get4"  # analysis.get4 --project (as run by analysis.reports)
V3_UNKNOWN_DIR = PROCESSED_DIR / "v3_unknown"  # analysis.v3_unknown
V3_REPORT_DIR = PROCESSED_DIR / "v3_report"  # analysis.v3_report


def main() -> None:
    argparse.ArgumentParser(description="Print the folders the analysis modules read from and write to.").parse_args()
    for name, value in globals().items():
        if isinstance(value, Path):
            print(f"{name:22} {value}")


if __name__ == "__main__":
    main()
