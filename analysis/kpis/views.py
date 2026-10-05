"""Loading the SEM views of a field and choosing which one to segment.

Images are read as grey in [0, 1] with their pixel size from the TIFF resolution tags; view_score() and
view_confidence() rate a BSE view by a quick test segmentation, and inventory() lists each field's views as
matched by analysis.fields (filename detector labels are wrong, so detectors come from the pixels).
"""

from pathlib import Path

import numpy as np
import tifffile

from ..fields import batch_dir, load_or_match
from .constants import MAX_BRIGHT_SHARE, RIM_CLEAN, RIM_USABLE
from .measurements import boundary_density
from .segmentation import segment


def pixel_size_nm(tif: tifffile.TiffFile) -> float | None:
    """Pixel size from the TIFF resolution tags (pixels per inch or per cm)."""
    page = tif.pages[0]
    xres, unit = page.tags.get("XResolution"), page.tags.get("ResolutionUnit")
    per_unit_nm = {2: 25.4e6, 3: 1e7}.get(int(unit.value) if unit else 2)
    if xres and per_unit_nm and xres.value[0]:
        px = per_unit_nm * xres.value[1] / xres.value[0]
        if px < 10_000:  # larger values are screen-dpi placeholders, not a calibration
            return px
    return None


def read_grey(path: str | Path) -> tuple[np.ndarray, float | None]:
    """Grey image in [0, 1] and its raw pixel size. The RGB channels are copies, except for a
    two-pixel stripe on the right edge of some files, which is cropped."""
    with tifffile.TiffFile(path) as tif:
        arr = tif.asarray()
        px = pixel_size_nm(tif)
    if arr.ndim == 3:
        arr = arr[..., 1]
    full = float(np.iinfo(arr.dtype).max) if np.issubdtype(arr.dtype, np.integer) else 1.0
    return arr[:, :-2].astype(np.float32) / full, px


def bin_image(img: np.ndarray, b: int) -> np.ndarray:
    """Block-average by an integer factor `b`, dropping the remainder rows / columns."""
    h, w = img.shape[0] // b * b, img.shape[1] // b * b
    return img[:h, :w].reshape(h // b, b, w // b, b).mean(axis=(1, 3))


def view_score(img: np.ndarray, px_nm: float | None) -> tuple[float, float]:
    """Quick 100 nm/px test segmentation: (bright-class perimeter per area in 1/um, bright area
    share). Compact bright particles score about 1.5-2.2; rim-lit edge views score higher."""
    b = max(1, round(100 / px_nm)) if px_nm else 4
    labels, _ = segment(bin_image(img, b))
    bright = labels == 2
    share = float(bright.mean())
    rim = boundary_density(bright, (px_nm * b if px_nm else 100) / 1000) / max(share, 1e-9)
    return rim, share


def view_confidence(rim: float, share: float) -> str:
    """'clean', 'usable' or 'excluded' from the view_score() of a view."""
    if share > MAX_BRIGHT_SHARE or rim > RIM_USABLE:
        return "excluded"
    return "clean" if rim <= RIM_CLEAN else "usable"


def inventory(batch: str, rebuild_fields: bool = False) -> dict[str, dict]:
    """Views grouped by the field they show (matched from pixels, not from filenames)."""
    manifest = load_or_match(batch, rebuild_fields)
    return {
        f["field_id"]: {
            "field": f,
            "views": [
                {
                    "filename": v["filename"],
                    "path": batch_dir(batch) / v["filename"],
                    "detector": v["detector"],
                    "detector_confidence": v["detector_confidence"],
                    "filename_detector": v["filename_detector"],
                }
                for v in f["views"]
            ],
        }
        for f in manifest["fields"]
    }
