"""analysis.kpis (segmentation and per-location KPIs) and analysis.kpi_single (one location): golden outputs."""

import numpy as np
import pytest
from _support import check_golden

from analysis import classify, kpi_single, kpis


@pytest.fixture(scope="module")
def segmented(bse_float):
    return kpis.segment(bse_float.astype(np.float32))


def test_segment(segmented):
    labels, quality = segmented
    assert labels.dtype == np.uint8 and set(np.unique(labels)) == {0, 1, 2}
    check_golden("kpis/segment", {"labels": labels, "quality": quality})


def test_measure_location(segmented):
    labels, _ = segmented
    kp, extra = kpis.measure_location(labels, 0.05)
    assert set(kp) <= set(kpis.KPI_INDEX)
    check_golden("kpis/measure_location", {"kpis": kp, "extra": extra})


def test_measurement_helpers(segmented):
    labels, _ = segmented
    pore = labels == 0
    rng = np.random.default_rng(3)
    ys, xs = rng.uniform(0, 300, 40), rng.uniform(0, 200, 40)
    check_golden(
        "kpis/helpers",
        {
            "chords_x": kpis.chords(pore, 1),
            "chords_y": kpis.chords(pore, 0),
            "boundary_density": kpis.boundary_density(pore, 0.05),
            "regions": kpis.regions(pore, kpis.MIN_PORE_PX),
            "clark_evans": [kpis.clark_evans(ys, xs, (300, 200)), kpis.clark_evans(ys[:5], xs[:5], (300, 200))],
            "ecd_um": kpis.ecd_um(np.array([4.0, 20.0, 100.0]), 0.05),
            "weighted_median": kpis.weighted_median(np.array([3.0, 1.0, 2.0, 5.0]), np.array([1.0, 1.0, 5.0, 1.0])),
            "bin_image": kpis.bin_image(np.arange(35, dtype=float).reshape(5, 7), 2),
            "poly_surface": kpis.poly_surface(
                (40, 50), np.array([0, 10, 39, 20, 5, 30.0]), np.array([0, 49, 10, 25, 40, 3.0]), np.arange(6.0)
            ),
        },
    )


def test_view_score(bse_float):
    rim, share = kpis.view_score(bse_float.astype(np.float32), 25.0)
    rim_nopx, share_nopx = kpis.view_score(bse_float.astype(np.float32), None)
    check_golden(
        "kpis/view_score",
        {"px25": [rim, share, kpis.view_confidence(rim, share)], "no_px": [rim_nopx, share_nopx]},
    )
    assert kpis.view_confidence(1.0, 0.5) == "excluded"


def test_cross_detector(triplet_arrays):
    bse = kpis.bin_image(triplet_arrays["BSE"].astype(np.float32) / 255, 2)
    labels, _ = kpis.segment(bse)
    views = {d: kpis.bin_image(triplet_arrays[d].astype(np.float32) / 255, 2) for d in ("ETD", "Inlens")}
    cross, alignment = kpis.cross_detector(bse, labels, {"ETD": views["ETD"], "InLens": views["Inlens"]})
    assert alignment["ETD"] == [-3, 2]  # the SE views are shifted by (6, -4) raw px = (3, -2) binned px
    assert set(cross) == set(kpis.CROSS_DETECTOR_KPIS)
    check_golden("kpis/cross_detector", {"kpis": cross, "alignment": alignment})


def test_summaries():
    values = [0.31, 0.29, None, 0.35, float("nan"), 0.33]
    check_golden(
        "kpis/summaries",
        {
            "summarise": kpis.summarise(values),
            "summarise_signed": kpis.summarise([0.01, 0.02, 0.015], signed=True),
            "summarise_one": kpis.summarise([0.2]),
            "summarise_none": kpis.summarise([None]),
            "histogram": kpis.histogram(np.array([0.05, 0.1, 0.2, 0.2, 1.5, 9.0]), 0.05, 5.0, 8),
            "phrase": [kpis.locations_phrase(1), kpis.locations_phrase(3)],
        },
    )


def test_save_overlay(segmented, bse_float, tmp_path):
    labels, _ = segmented
    out = tmp_path / "overlay.jpg"
    kpis.save_overlay(bse_float, labels, out, width=200)
    from PIL import Image

    with Image.open(out) as im:
        assert im.size == (200, 200)


# ---------------------------------------------------------------- analysis.kpi_single


@pytest.fixture(scope="module")
def single_measurement(triplet_tiffs):
    return kpi_single.measure(triplet_tiffs["BSE"], {"ETD": triplet_tiffs["ETD"], "InLens": triplet_tiffs["Inlens"]})


def test_kpi_single_measure(single_measurement, triplet_tiffs):
    kp, info = single_measurement
    assert info["pixel_size_nm"] == pytest.approx(25.0)
    assert info["views_compared"] == ["ETD", "InLens"]
    bse_only, _ = kpi_single.measure(triplet_tiffs["BSE"], {})
    assert not set(kpis.CROSS_DETECTOR_KPIS) & set(bse_only)
    check_golden("kpi_single/measure", {"kpis": kp, "info": info})


def _synthetic_references(n_per_batch: int = 6):
    """Reference locations / labels / KPI matrix in the shape analysis.classify.load_references returns."""
    rng = np.random.default_rng(7)
    ref, y, rows = [], [], []
    for b, batch in enumerate(classify.BATCHES):
        for i in range(n_per_batch):
            ref.append({"batch": batch, "location_id": f"L{batch}{i}", "analysed_image": f"img_L{batch}{i}_BSE.tif"})
            y.append(batch)
            rows.append(rng.normal(size=len(classify.FEATURES)) + b * np.linspace(1.5, 0.0, len(classify.FEATURES)))
    return ref, np.array(y), np.array(rows)


def test_kpi_single_classify(single_measurement, triplet_tiffs, monkeypatch, tmp_path):
    """The full classify step on synthetic references (no data/processed needed)."""
    monkeypatch.setattr(kpi_single, "load_references", _synthetic_references)
    monkeypatch.setattr(kpi_single, "VALIDATION_CACHE", tmp_path / "missing.json")
    kp, _ = single_measurement
    result = kpi_single.classify(kp, triplet_tiffs["BSE"])
    assert result["predicted_batch"] in {"Batch_1", "Batch_2", "Batch_3"}
    assert result["session_hint"]["image_height_px"] == 512
    check_golden("kpi_single/classify", result)
