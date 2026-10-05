"""Detailed KPI report for each reference battery batch (data/raw/batch_N) and the unknown set.

Each batch is one battery type, imaged at several fields of view; every field has two to
three detector views. Filenames do not say which files show the same field (see
analysis.fields), so fields are matched from the images first and each field is one
replicate. The electrode cross-sections show three intensity classes on a
compositional-contrast view: black pores, dark-grey graphite flakes and a bright,
higher-Z phase (likely the silicon-containing additive). This package:

1. Analyses the BSE view of each field. Filename detector labels are wrong, so the detector
   of every view is identified from its pixels by analysis.fields (BSE / InLens / ETD).
   Fields without a BSE view are reported but left out of the batch statistics. A BSE view
   whose bright class has rough rims or a high loading is kept but flagged lower-confidence,
   since binder and particle edges can leak into the bright class.
2. Segments that view into pore / graphite / bright phase (3-class Otsu after removing
   smooth shading) and measures composition, pore network, bright-particle, graphite
   texture, interface and homogeneity KPIs.
3. Segments the field's ETD and InLens views the same way, aligns them to the BSE view and compares them
   pixel by pixel (cross-detector KPIs: where ETD and InLens agree or disagree with the BSE phases).
4. Summarises every KPI across locations (mean, SD, CV, t-based 95% CI, range) and writes
   a frontend-ready report plus a segmentation overlay per field.

The unknown set (data/raw/unknown) is measured the same way by analysis.classify, which calls
analyse_batch("unknown") and writes batch_unknown/.

Outputs (Git-ignored, like the raw data):
  data/processed/batch_kpis/batch_N/report.json
  data/processed/batch_kpis/batch_N/overlays/<field>.jpg
  data/processed/batch_kpis/summary.json      headline KPIs of every batch side by side

    python -m analysis.kpis [--batches 1 2 3] [--rebuild-fields]

Modules: views (loading, view selection), segmentation, measurements (per-location KPIs), cross_detector,
catalogue (KPI definitions), statistics (summaries, histograms, findings), report (analyse_batch, overlays),
constants (thresholds) and cli. Every public name is re-exported here, so `from analysis import kpis` and
`kpis.segment(...)`, `kpis.KPI_INDEX` etc. work as before the package split.

OUT (the output folder) lives here only; analyse_batch() and the command line read `analysis.kpis.OUT` at call
time, so reassigning it redirects the reports.
"""

from .. import paths
from .catalogue import (
    CROSS_DETECTOR_KPIS,
    DENSITY,
    HEADLINE,
    KPI_GROUPS,
    KPI_INDEX,
    MICRON,
    PER_UM,
    PERCENT,
    RATIO,
    SIGNED_KPIS,
)
from .cli import main
from .constants import (
    CRACK_ASPECT,
    CRACK_LENGTH_UM,
    MAX_BRIGHT_SHARE,
    MIN_BRIGHT_PX,
    MIN_PORE_PX,
    PHASE_COLORS,
    PROFILE_BANDS,
    RIM_CLEAN,
    RIM_USABLE,
    SEPARABILITY_LIMIT,
    TARGET_NM,
)
from .cross_detector import cross_detector
from .measurements import boundary_density, chords, clark_evans, ecd_um, measure_location, regions, weighted_median
from .report import analyse_batch, save_overlay
from .segmentation import poly_surface, segment
from .statistics import findings, histogram, locations_phrase, summarise
from .views import bin_image, inventory, pixel_size_nm, read_grey, view_confidence, view_score

ROOT = paths.REPO_ROOT
OUT = paths.KPI_DIR

__all__ = [
    "CRACK_ASPECT",
    "CRACK_LENGTH_UM",
    "CROSS_DETECTOR_KPIS",
    "DENSITY",
    "HEADLINE",
    "KPI_GROUPS",
    "KPI_INDEX",
    "MAX_BRIGHT_SHARE",
    "MICRON",
    "MIN_BRIGHT_PX",
    "MIN_PORE_PX",
    "OUT",
    "PERCENT",
    "PER_UM",
    "PHASE_COLORS",
    "PROFILE_BANDS",
    "RATIO",
    "RIM_CLEAN",
    "RIM_USABLE",
    "ROOT",
    "SEPARABILITY_LIMIT",
    "SIGNED_KPIS",
    "TARGET_NM",
    "analyse_batch",
    "bin_image",
    "boundary_density",
    "chords",
    "clark_evans",
    "cross_detector",
    "ecd_um",
    "findings",
    "histogram",
    "inventory",
    "locations_phrase",
    "main",
    "measure_location",
    "pixel_size_nm",
    "poly_surface",
    "read_grey",
    "regions",
    "save_overlay",
    "segment",
    "summarise",
    "view_confidence",
    "view_score",
    "weighted_median",
]
