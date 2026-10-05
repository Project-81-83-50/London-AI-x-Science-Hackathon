"""Reading SEM images: TIFF metadata (pixel size, databar), memory-mapped pixel access and resampling."""

import re
from pathlib import Path

import numpy as np
import tifffile
from skimage import io, transform

UNIT_TO_NM = {"pm": 1e-3, "nm": 1.0, "um": 1e3, "µm": 1e3, "mm": 1e6, "m": 1e9}


def _pixel_size_nm(tif: tifffile.TiffFile) -> float | None:
    """Best-effort pixel size from FEI/Thermo or Zeiss SEM metadata."""
    fei = tif.fei_metadata
    if fei:
        try:
            return float(fei["Scan"]["PixelWidth"]) * 1e9
        except (KeyError, TypeError, ValueError):
            pass
    sem = tif.sem_metadata
    if sem:
        for key, value in sem.items():
            if "pixel_size" not in key.lower():
                continue
            text = " ".join(map(str, value)) if isinstance(value, (list, tuple)) else str(value)
            m = re.search(r"([\d.]+(?:e-?\d+)?)\s*(pm|nm|um|µm|mm|m)\b", text)
            if m:
                return float(m.group(1)) * UNIT_TO_NM[m.group(2)]
    ij = tif.imagej_metadata
    if ij and "unit" in ij:  # FIJI / ImageJ calibration: XResolution = pixels per unit
        unit = {"micron": "um", "\\u00B5m": "um"}.get(ij["unit"], ij["unit"])
        tag = tif.pages[0].tags.get("XResolution")
        if tag and unit in UNIT_TO_NM:
            num, den = tag.value
            if num:
                return den / num * UNIT_TO_NM[unit]
    # standard TIFF resolution tags (pixels per inch / cm); ignore placeholder values like 72 dpi
    page = tif.pages[0]
    xres, unit = page.tags.get("XResolution"), page.tags.get("ResolutionUnit")
    per_unit_nm = {2: 25.4e6, 3: 1e7}.get(int(unit.value) if unit else 2)
    if xres and per_unit_nm and xres.value[0]:
        px = per_unit_nm * xres.value[1] / xres.value[0]
        if px < 10_000:  # < 10 um/px: a real calibration, not a screen-dpi default
            return px
    return None


def _databar_rows(tif: tifffile.TiffFile, height: int) -> int:
    """FEI/Thermo images store the true image height; anything below it is the info bar."""
    fei = tif.fei_metadata
    try:
        return max(0, height - int(fei["Image"]["ResolutionY"]))
    except (KeyError, TypeError, ValueError):
        return 0


def _bin_chunked(arr: np.ndarray, b: int, chunk_rows: int = 2048) -> np.ndarray:
    """Grey-convert and bin in row chunks so a memory-mapped TIF never loads whole."""
    h, w = arr.shape[0] // b * b, arr.shape[1] // b * b
    out = np.empty((h // b, w // b), np.float32)
    step = max(b, chunk_rows // b * b)
    for y in range(0, h, step):
        blk = np.asarray(arr[y : min(y + step, h), :w], dtype=np.float32)
        if blk.ndim == 3:
            blk = blk[..., :3].mean(axis=-1)
        out[y // b : (y + blk.shape[0]) // b] = blk.reshape(blk.shape[0] // b, b, w // b, b).mean(axis=(1, 3))
    return out


def read_meta(path: str | Path, page: int = 0) -> dict:
    """Cheap metadata pass (no pixel data), so the batch scale can be chosen first."""
    meta = {"pixel_size_nm": None, "databar_rows": 0, "n_pages": 1}
    if Path(path).suffix.lower() in (".tif", ".tiff"):
        with tifffile.TiffFile(path) as tif:
            meta["pixel_size_nm"] = _pixel_size_nm(tif)
            meta["databar_rows"] = _databar_rows(tif, tif.pages[page].shape[0])
            meta["n_pages"] = len(tif.pages)
    return meta


def _open_array(path: str | Path, page: int) -> np.ndarray:
    """Pixel array of one page, memory-mapped when the TIF layout allows it."""
    if Path(path).suffix.lower() in (".tif", ".tiff"):
        try:
            return tifffile.memmap(path, page=page, mode="r")
        except Exception:  # compressed or non-contiguous: read normally
            return tifffile.imread(path, key=page)
    return io.imread(path)


def load_image(
    path: str | Path,
    meta: dict,
    page: int = 0,
    crop_bottom: int | None = None,
    px_nm: float | None = None,
    target_nm: float | None = None,
    bin_factor: int = 2,
    tilt_deg: float | None = None,
) -> tuple[np.ndarray, dict]:
    """Crop the databar, scale grey levels to [0, 1] of the detector range and resample to
    square pixels of target_nm (integer block-binning, then an anti-aliased resize for the
    remainder). Without pixel sizes this is plain binning by bin_factor."""
    arr = _open_array(path, page)
    rows = meta["databar_rows"] if crop_bottom is None else crop_bottom
    if rows:
        arr = arr[: arr.shape[0] - rows]
    if np.issubdtype(arr.dtype, np.integer):
        full_scale = float(np.iinfo(arr.dtype).max)
    else:
        full_scale = float(np.nanmax(np.asarray(arr[::16, ::16]))) or 1.0

    factor = target_nm / px_nm if (px_nm and target_nm) else float(bin_factor)
    b = max(1, int(np.floor(factor + 1e-9)))
    img = _bin_chunked(arr, b) / full_scale
    rx = factor / b
    ry = rx * np.sin(np.radians(tilt_deg)) if tilt_deg else rx  # tilt: each row spans more real length
    shape = (max(1, int(round(img.shape[0] / ry))), max(1, int(round(img.shape[1] / rx))))
    if shape != img.shape:
        img = transform.resize(img, shape, order=1, anti_aliasing=True, preserve_range=True).astype(np.float32)
    info = {
        "databar_rows": rows,
        "shape_px": [int(arr.shape[0]), int(arr.shape[1])],
        "full_scale": full_scale,
        "scale_factor": float(factor),
        "shape_analysed": [int(img.shape[0]), int(img.shape[1])],
        "upsampled": bool(factor < 1),
    }
    return img, info
