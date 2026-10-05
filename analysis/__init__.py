"""In-house image analysis of the SEM battery-electrode images.

Command-line entry points (run them from the repository root, e.g. `python -m analysis.kpis --help`):

- fields: group each batch's images into fields of view and identify every view's detector from its pixels
- kpis (package): per-location segmentation KPIs and the detailed KPI report of each batch
    - views: image loading, pixel size, binning and BSE view selection
    - segmentation: shading removal and the 3-class (pore / graphite / bright phase) segmentation
    - measurements: the per-location KPIs of one segmented BSE view
    - cross_detector: BSE compared pixel by pixel with the field's ETD and InLens segmentations
    - catalogue: KPI groups, names, units and definitions (KPI_GROUPS, KPI_INDEX, HEADLINE)
    - statistics: across-location summaries, size histograms and plain-language findings
    - report: the per-batch report.json and segmentation overlays (analyse_batch)
    - constants: tunable thresholds and sizes; cli: `python -m analysis.kpis`
- classify: classify the unknown locations as batch 1, 2 or 3 from their KPIs (diagonal LDA)
- kpi_single: the same classifier applied to one uploaded location
- get4 (package): GET4 uncertainty of phase fractions (area, regularity and between-image factors)
- batch_match: adapter running the batch-match classifier in batch_match/ on this project's data
- v3_unknown: segment the unknown images with the v3 SEM pipeline in sem_pipeline/
- v3_report: general and detailed batch reports built on the v3 SEM pipeline's outputs
- reports: run the reference-batch report generators in one command
- paths: the repository folders every module reads from and writes to

Paths: inputs are the raw images in data/raw/batch_N and data/raw/unknown; outputs go to data/processed/.
Every folder is defined once in analysis.paths. Modules keep their own module-level aliases (`RAW`, `OUT`, ...)
and read them at call time, so a script or test can redirect one module by reassigning its alias.

Output rule: progress and status messages (which item is being processed, steps started or skipped, files
written) go through `logging` (`logger = logging.getLogger(__name__)`). The result a command exists to show
(classification table, field listing, JSON summary) is printed with print(). Each entry point's main() calls
configure_cli_logging(), which writes the analysis loggers' records to stdout as the bare message, so the console
output, and the log the backend captures from these subprocesses (analysis_run.log), reads as plain text lines.
Importing a module never configures logging; a library caller decides where the messages go.
"""

import logging
import sys

_CLI_HANDLER = "analysis-cli"


def configure_cli_logging(level: int = logging.INFO) -> None:
    """Send records of the `analysis` loggers (and of a module run as `__main__`) to stdout as `%(message)s`.

    Only these loggers are configured, so third-party libraries log exactly as they would without it.
    Calling it again does not add a second handler."""
    for name in ("analysis", "__main__"):
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.propagate = False
        if not any(h.get_name() == _CLI_HANDLER for h in logger.handlers):
            handler = logging.StreamHandler(sys.stdout)
            handler.set_name(_CLI_HANDLER)
            handler.setFormatter(logging.Formatter("%(message)s"))
            logger.addHandler(handler)
