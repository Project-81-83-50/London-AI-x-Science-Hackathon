"""GET4: uncertainty of phase-fraction KPIs from SEM images of one batch.

This package is the single implementation of GET4 in the repository. Two older entry points are thin
compatibility shims that re-export it unchanged:

- batch_match/get4.py (imported as top-level `get4` by batch_match/batch_classifier.py and the experiments;
  it also keeps the old name `segment_bse` for `segment_intensity_classes`), and
- sem_pipeline/src/get4.py (imported as `src.get4` by the SEM pipeline).

Usage
-----
From the repository root, `python -m analysis.get4 --help`. The backend runs

    python -m analysis.get4 --project --fast [--batch unknown] --out data/processed/get4

which writes, per data/raw folder and detector, <out>/<folder>/<DETECTOR>/batch_uncertainty.json,
analysis_report.json, batch_uncertainty.png and one <image>_uncertainty.json per image, plus
<out>/<folder>/location_manifest.json. Other modes: images or folders as positional inputs (one batch),
--baseline (compare imaging and borrow tau2 from an earlier run) and --compare (lot A vs lot B).
As a library, import the functions from here (`from analysis import get4; get4.analyse_phase(...)`).

Structure
---------
- constants      class names (PHASES, INTENSITY_CLASSES), Z95, image suffixes, FFT size limits
- loading        TIFF metadata (pixel size, databar), memory-mapped reading, binning / resampling
- preprocessing  imaging-quality metrics, shading flattening, curtaining / scan-line removal
- segmentation   three-class intensity segmentation and its systematic sensitivity
- spatial        factors 1 and 2 for one phase mask: covariance, integral range, tiles, `analyse_phase`
- imaging        imaging-condition flags against a reference, the common pixel size (`resolve_target`)
- pooling        factor 3: random-effects pooling over images (`analyse_batch`), next-measurement advice
- comparison     lot A vs lot B (`compare_lots`)
- reporting      console reports (print_*)
- plotting       per-image and batch figures (matplotlib imported lazily)
- inputs         detector / location codes from filenames, `collect_images`
- pipeline       `analyse_image` (one image) and `analyse_paths` (one image set -> JSON reports)
- cli            argument parser and `main` (also run by `python -m analysis.get4`)

Every name of the former single-module analysis/get4.py, including the private helpers callers and tests
use, is re-exported here, so `analysis.get4.X` keeps working. Constants are read by the submodule that
defines or imports them: assigning `analysis.get4.SOME_CONSTANT = ...` on this package does NOT change what
the functions do (nothing in the repository does this). To override a constant, patch it on every
submodule that uses it (e.g. `analysis.get4.constants.FULL_FFT_MAX_PX` and
`analysis.get4.pipeline.FULL_FFT_MAX_PX`), since `from .constants import X` binds X in each module.

Method
------
Question answered: "Given the images we have, how well do we actually know this
batch's phase fractions, what is limiting that, and what should we image next?"

The error bar is built from three factors, each acting at a different length scale:

1. AREA USED (scale of one feature)
   A phase fraction is a mean over pixels, but pixels are correlated: a pixel in a
   particle predicts its neighbours. With C(r) the normalised two-point covariance
   (C(0) = 1), the variance of the mean over an image of area A is

       Var_area = phi(1-phi)/A * sum_r C(r) w_A(r)  ~=  phi(1-phi) * a / A,   a = sum_r C(r)

   so the image is worth N_eff = A / a independent samples, where `a` (the
   "integral range") is roughly the area of one typical feature.
   Information view: Fisher information about phi is N_eff / (phi(1-phi)); bits gained
   over a flat prior are -1/2 log2(2 pi e SE^2). Every 4x area buys exactly one bit.

2. REGULARITY (scale of the image)
   The C(r) model only knows about feature-scale correlation. If the image also has
   larger-scale structure (a through-thickness gradient, a cluster, a crack band),
   L x L tiles will vary MORE than C(r) predicts. The ratio

       D = observed tile variance / predicted tile variance     (largest L with >= 16 tiles)

   is an overdispersion factor: D ~ 1 means the image is statistically regular,
   D > 1 means it is not, and Var_image = Var_area * max(D, 1). We never shrink the
   error bar when D < 1. C(r) is cut at 5 correlation lengths so that large-scale
   structure cannot hide inside the "feature size" and must show up here instead.
   D only probes scales up to ~1/4 of the image. A gradient across the whole image
   height is reported separately as a top-to-bottom trend: if the image spans the
   electrode thickness it is a material property (e.g. binder migration), not noise.

3. DIFFERENCE BETWEEN IMAGES (scale of the electrode)
   No single image can show how much the electrode varies from place to place.
   Fields of view are combined with a random-effects model (as in meta-analysis):

       phi_i = mu + b_i + e_i,   b_i ~ N(0, tau^2),   e_i ~ N(0, Var_image_i)

   tau^2 (true field-to-field variation) is estimated by DerSimonian-Laird; the batch
   CI uses the Hartung-Knapp correction with a t distribution, which is honest when
   there are only a few images. I^2 = share of the observed spread that is real
   field-to-field variation rather than sampling noise.

The batch variance splits exactly into the three factors (the "uncertainty budget"),
which also tells you what to do next: if AREA dominates, image bigger fields; if
BETWEEN dominates, image more locations; if REGULARITY dominates, look at the image.

Segmentation sensitivity (threshold nudged by +-2% of the grey range) is systematic,
does not shrink with more images, and is reported separately.

Imaging conditions (so an imaging change is not mistaken for a material change)
--------------------------------------------------------------------------------
SCALE: every image is resampled to one physical pixel size before anything else
   (the baseline's, if given, else the coarsest image x --bin), so smoothing, tiles
   and thresholds act on the same physical scale. Missing / mixed pixel sizes are
   refused or flagged; a phase whose features are < 5 px is flagged resolution-limited.
   --tilt-deg corrects the y foreshortening of FIB cross-sections imaged under tilt.
IMAGING QUALITY: sharpness, directional blur (astigmatism), noise, brightness,
   contrast, clipping, phase separability and stripe strength are measured per image
   and compared with the baseline images (or the rest of the batch). An image outside
   the reference range is reported as an IMAGING difference to investigate first.
SURFACE ROUGHNESS / SHADING: smooth shading is removed by fitting a low-order surface
   to the majority phase only (so real composition gradients survive); curtaining and
   scan lines are notch-filtered in Fourier space when detected. Remaining local
   shading is measured by re-fitting thresholds per tile: the phi difference between
   local and global thresholds is the roughness part of the segmentation error.
   Not handled: "pore-back" (material deeper inside pores showing through).
   Irregular / organic particle SHAPES need no special handling: C(r) assumes none.

Note: images passed together must be different LOCATIONS imaged with the SAME
detector. The same field seen by BSE / SE / InLens is not three independent samples.
"""

from .cli import RAW_ROOT, build_parser, main
from .comparison import _cdf, _lot_variance, _prob_range, compare_lots, compare_phase, how_sure, parse_tolerances
from .constants import FFT_TILE, FULL_FFT_MAX_PX, IMAGE_SUFFIXES, INTENSITY_CLASSES, PHASES, Z95
from .imaging import QUALITY_LIMITS, QUALITY_TOLERANCE, quality_flags, resolve_target
from .inputs import DETECTOR_TAGS, _detector_of, _location_of, collect_images
from .loading import UNIT_TO_NM, _bin_chunked, _databar_rows, _open_array, _pixel_size_nm, load_image, read_meta
from .pipeline import analyse_image, analyse_paths
from .plotting import (
    BUDGET_COLORS,
    GRID,
    INK,
    INK2,
    PHASE_COLORS,
    SURFACE,
    _style,
    plot_batch_report,
    plot_image_report,
)
from .pooling import analyse_batch, next_measurement, random_effects
from .preprocessing import (
    F0,
    STRIPE_LIMIT,
    _central_crop,
    _poly_terms,
    destripe,
    flatten_shading,
    image_quality,
    noise_sigma,
    separability,
    stripe_index,
)
from .reporting import print_batch_summary, print_comparison, print_image_summary, print_quality_report
from .segmentation import local_segmentation_fractions, segment_intensity_classes, segmentation_sensitivity
from .spatial import (
    FEATURE_CUTOFF,
    _raw_autocorr,
    analyse_phase,
    correlation_length,
    depth_trend,
    dispersion,
    info_bits,
    integral_range,
    normalised_covariance,
    predicted_se,
    tile_scaling,
)

# Everything above, private helpers included, so that `from analysis.get4 import *` (used by the shims in
# batch_match/ and sem_pipeline/src/) re-exports the complete former module namespace.
__all__ = [
    # constants
    "FFT_TILE",
    "FULL_FFT_MAX_PX",
    "IMAGE_SUFFIXES",
    "INTENSITY_CLASSES",
    "PHASES",
    "Z95",
    # loading
    "UNIT_TO_NM",
    "_bin_chunked",
    "_databar_rows",
    "_open_array",
    "_pixel_size_nm",
    "load_image",
    "read_meta",
    # preprocessing
    "F0",
    "STRIPE_LIMIT",
    "_central_crop",
    "_poly_terms",
    "destripe",
    "flatten_shading",
    "image_quality",
    "noise_sigma",
    "separability",
    "stripe_index",
    # segmentation
    "local_segmentation_fractions",
    "segment_intensity_classes",
    "segmentation_sensitivity",
    # spatial
    "FEATURE_CUTOFF",
    "_raw_autocorr",
    "analyse_phase",
    "correlation_length",
    "depth_trend",
    "dispersion",
    "info_bits",
    "integral_range",
    "normalised_covariance",
    "predicted_se",
    "tile_scaling",
    # imaging
    "QUALITY_LIMITS",
    "QUALITY_TOLERANCE",
    "quality_flags",
    "resolve_target",
    # pooling
    "analyse_batch",
    "next_measurement",
    "random_effects",
    # comparison
    "_cdf",
    "_lot_variance",
    "_prob_range",
    "compare_lots",
    "compare_phase",
    "how_sure",
    "parse_tolerances",
    # reporting
    "print_batch_summary",
    "print_comparison",
    "print_image_summary",
    "print_quality_report",
    # plotting
    "BUDGET_COLORS",
    "GRID",
    "INK",
    "INK2",
    "PHASE_COLORS",
    "SURFACE",
    "_style",
    "plot_batch_report",
    "plot_image_report",
    # inputs
    "DETECTOR_TAGS",
    "_detector_of",
    "_location_of",
    "collect_images",
    # pipeline
    "analyse_image",
    "analyse_paths",
    # cli
    "RAW_ROOT",
    "build_parser",
    "main",
]
