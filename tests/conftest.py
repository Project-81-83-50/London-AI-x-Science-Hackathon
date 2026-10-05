"""Fixtures: synthetic SEM images (as arrays and TIFF files), the three GET4 entry points, and real images if present.

Real images are never in Git. The `realdata` tests look for batch_1 under SEM_RAW_DATA_DIR (if set), then
data/raw/ and data/ at the repository root, and skip when none is found.
"""

import importlib
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from _support import REPO_ROOT, detector_views, synthetic_image, write_tiff

# ---------------------------------------------------------------- synthetic images

PIXEL_NM = 25.0  # pixel size written into the synthetic TIFFs' resolution tags (the raw data's ~25 nm/px)


@pytest.fixture(scope="session")
def bse_float() -> np.ndarray:
    """384 x 384 float32 BSE-like image in [0, 1]."""
    return synthetic_image(seed=0)


@pytest.fixture(scope="session")
def striped_float() -> np.ndarray:
    """384 x 384 float32 image with strong horizontal scan lines (triggers GET4's destriping)."""
    return synthetic_image(seed=1, stripes=0.03)


@pytest.fixture(scope="session")
def synthetic_dir(tmp_path_factory) -> Path:
    """Session temp folder holding every synthetic TIFF (tests never write into the repository's data/)."""
    return tmp_path_factory.mktemp("synthetic")


@pytest.fixture(scope="session")
def bse_tiffs(synthetic_dir) -> list[Path]:
    """Three 512 x 512 BSE TIFFs of different locations (uint8, uint16, uint8) with a 25 nm pixel size."""
    specs = [("aaa111", 10, np.uint8), ("bbb222", 11, np.uint16), ("ccc333", 12, np.uint8)]
    folder = synthetic_dir / "bse"
    return [
        write_tiff(folder / f"img_{code}_BSE.tif", synthetic_image(seed, (512, 512), dtype), PIXEL_NM)
        for code, seed, dtype in specs
    ]


@pytest.fixture(scope="session")
def plain_tiff(synthetic_dir) -> Path:
    """uint16 TIFF without any pixel-size metadata."""
    return write_tiff(synthetic_dir / "plain" / "img_plain0_BSE.tif", synthetic_image(20, (384, 448), np.uint16))


@pytest.fixture(scope="session")
def triplet_tiffs(synthetic_dir) -> dict[str, Path]:
    """BSE / ETD / Inlens uint8 TIFFs of one synthetic field (SE views shifted by (6, -4) px), 25 nm/px."""
    views = detector_views(seed=30, shape=(512, 512), shift=(6, -4))
    folder = synthetic_dir / "triplet"
    return {det: write_tiff(folder / f"img_ddd444_{det}.tif", arr, PIXEL_NM) for det, arr in views.items()}


@pytest.fixture(scope="session")
def triplet_arrays() -> dict[str, np.ndarray]:
    """The uint8 arrays written by `triplet_tiffs`."""
    return detector_views(seed=30, shape=(512, 512), shift=(6, -4))


# ---------------------------------------------------------------- the three GET4 entry points (two are shims)


@contextmanager
def isolated_import(path_entry: Path, prefixes: tuple[str, ...]) -> Iterator[None]:
    """Import top-level modules from `path_entry` without leaking them: during the block `path_entry` is first
    on sys.path and modules named in `prefixes` (and their submodules) are unloaded; afterwards sys.path and
    those sys.modules entries are restored. Module objects imported inside stay usable."""

    def ours(name: str) -> bool:
        return any(name == p or name.startswith(p + ".") for p in prefixes)

    saved_path = list(sys.path)
    saved = {k: v for k, v in sys.modules.items() if ours(k)}
    for k in saved:
        del sys.modules[k]
    sys.path.insert(0, str(path_entry))
    importlib.invalidate_caches()
    try:
        yield
    finally:
        sys.path[:] = saved_path
        for k in [k for k in sys.modules if ours(k)]:
            del sys.modules[k]
        sys.modules.update(saved)


@pytest.fixture(scope="session")
def analysis_get4():
    import analysis.get4

    return analysis.get4


@pytest.fixture(scope="session")
def batch_match_modules() -> SimpleNamespace:
    """batch_match/get4.py and batch_match/batch_classifier.py, imported as batch_classifier does
    (batch_match/ on sys.path, top-level names `get4` and `batch_classifier`)."""
    with isolated_import(REPO_ROOT / "batch_match", ("get4", "batch_classifier")):
        bc = importlib.import_module("batch_classifier")
        g4 = importlib.import_module("get4")
    assert bc.get4 is g4
    return SimpleNamespace(get4=g4, batch_classifier=bc)


@pytest.fixture(scope="session")
def sem_get4():
    """sem_pipeline/src/get4.py imported as `src.get4` (cwd sem_pipeline in normal use)."""
    with isolated_import(REPO_ROOT / "sem_pipeline", ("src",)):
        mod = importlib.import_module("src.get4")
    return mod


# ---------------------------------------------------------------- real data (skipped when absent)


def _real_batch_dir() -> Path | None:
    candidates = []
    if os.environ.get("SEM_RAW_DATA_DIR"):
        candidates.append(Path(os.environ["SEM_RAW_DATA_DIR"]))
    candidates += [REPO_ROOT / "data" / "raw", REPO_ROOT / "data"]
    for root in candidates:
        folder = root / "batch_1"
        if folder.is_dir() and any(folder.glob("img_*_BSE.tif")):
            return folder
    return None


@pytest.fixture(scope="session")
def real_batch_dir() -> Path:
    folder = _real_batch_dir()
    if folder is None:
        pytest.skip("no real images: batch_1 not found under SEM_RAW_DATA_DIR, data/raw/ or data/")
    return folder


@pytest.fixture(scope="session")
def real_triplet(real_batch_dir) -> dict[str, Path]:
    """BSE / ETD / Inlens files of the first location (by name) in batch_1 that has all three views."""
    for bse in sorted(real_batch_dir.glob("img_*_BSE.tif")):
        stem = bse.name[: -len("_BSE.tif")]
        views = {"BSE": bse, "ETD": bse.with_name(f"{stem}_ETD.tif"), "Inlens": bse.with_name(f"{stem}_Inlens.tif")}
        if all(p.is_file() for p in views.values()):
            return views
    pytest.skip(f"no location with BSE, ETD and Inlens views in {real_batch_dir}")


@pytest.fixture(scope="session")
def real_image(real_triplet) -> Path:
    """One real BSE TIFF from batch_1."""
    return real_triplet["BSE"]
