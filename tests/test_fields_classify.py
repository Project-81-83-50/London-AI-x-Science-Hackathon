"""analysis.fields (edge maps, phase correlation, detector identification) and analysis.classify (the KPI
classifier): golden outputs on synthetic data."""

import numpy as np
import pytest
from _support import check_golden, detector_views, write_tiff
from scipy import fft

from analysis import classify, fields

# ---------------------------------------------------------------- analysis.fields


def test_edge_map(triplet_tiffs):
    check_golden("fields/edge_map", {det: fields.edge_map(p) for det, p in triplet_tiffs.items()})


def test_phase_correlation(triplet_tiffs, bse_tiffs):
    spectra = {det: fft.fft2(fields.edge_map(p)) for det, p in triplet_tiffs.items()}
    unrelated = fft.fft2(fields.edge_map(bse_tiffs[0]))
    result = {
        "bse_etd": fields.phase_correlation(spectra["BSE"], spectra["ETD"]),
        "bse_inlens": fields.phase_correlation(spectra["BSE"], spectra["Inlens"]),
        "etd_inlens": fields.phase_correlation(spectra["ETD"], spectra["Inlens"]),
        "unrelated": fields.phase_correlation(spectra["BSE"], unrelated),
    }
    # Same field scores higher than unrelated fields (on these small 64 px edge maps the absolute scores
    # sit above the real-data MATCH_SCORE threshold, so only the ordering is asserted).
    assert min(result["bse_etd"][0], result["bse_inlens"][0]) > result["unrelated"][0]
    assert result["bse_etd"][1] == [-8, 8]  # (6, -4) px shift, quantised to the 8 px edge-map bins
    check_golden("fields/phase_correlation", result)


def test_identify_detectors(triplet_tiffs, synthetic_dir):
    """Views given in a scrambled order; the noisiest is BSE, darker pores ETD, filled pores InLens."""
    order = ["Inlens", "BSE", "ETD"]
    result = fields.identify_detectors([triplet_tiffs[d] for d in order])
    assert [r["detector"] for r in result] == ["InLens", "BSE", "ETD"]
    pair = fields.identify_detectors([triplet_tiffs["BSE"], triplet_tiffs["Inlens"]])
    check_golden("fields/identify_detectors", {"triplet": result, "bse_inlens": pair})


def test_read_grey_noise_contrast(triplet_tiffs):
    img = fields.read_grey(triplet_tiffs["BSE"])
    binned = fields.read_grey(triplet_tiffs["BSE"], 4)
    labels = fields.phase_map(binned)
    check_golden(
        "fields/grey_noise_contrast",
        {
            "grey": img,
            "binned": binned,
            "relative_noise": {d: fields.relative_noise(fields.read_grey(p)) for d, p in triplet_tiffs.items()},
            "phase_map": labels,
            "phase_contrast": {
                d: fields.phase_contrast(fields.read_grey(p, 4), labels) for d, p in triplet_tiffs.items()
            },
        },
    )


def test_grouping_and_locations():
    scores = np.array(
        [
            [0.0, 0.30, 0.20, 0.01, 0.02],
            [0.30, 0.0, 0.25, 0.03, 0.01],
            [0.20, 0.25, 0.0, 0.10, 0.02],
            [0.01, 0.03, 0.10, 0.0, 0.08],
            [0.02, 0.01, 0.02, 0.08, 0.0],
        ]
    )
    groups = fields.group_fields(scores)
    assert groups == [[0, 1, 2], [3, 4]]

    def view(code, det, detector):
        return {
            "filename": f"img_{code}_{det}.tif",
            "filename_code": code,
            "filename_detector": det.upper(),
            "detector": detector,
        }

    field_list = [
        {"views": [view("a1", "BSE", "BSE"), view("a1", "ETD", "ETD"), view("b2", "Inlens", "InLens")]},
        {"views": [view("b2", "BSE", "BSE"), view("b2", "SE", "ETD")]},
        {"views": [view("c3", "BSE", "BSE")]},
    ]
    fields.assign_locations(field_list)
    assert sorted(f["location"] for f in field_list) == ["a1", "b2", "c3"]
    check_golden(
        "fields/assign_locations",
        {
            "fields": field_list,
            "confidence": [fields._match_confidence(n, s) for n, s in ((1, 0), (2, 0.2), (3, 0.05))],
        },
    )


def test_match_batch(tmp_path, monkeypatch):
    """The whole field-matching step on a synthetic batch folder (outputs redirected to tmp_path)."""
    raw, out = tmp_path / "raw", tmp_path / "fields"
    for seed, code in ((50, "f1a"), (51, "f2b")):
        for det, arr in detector_views(seed, (512, 512), shift=(4, 6)).items():
            write_tiff(raw / "batch_9" / f"img_{code}_{det}.tif", arr, 25.0)
    monkeypatch.setattr(fields, "RAW", raw)
    monkeypatch.setattr(fields, "OUT", out)
    manifest = fields.match_batch("9")
    assert (out / "batch_9.json").is_file()
    assert [sorted(v["filename_code"] for v in f["views"]) for f in manifest["fields"]] == [["f1a"] * 3, ["f2b"] * 3]
    assert all(v["label_matches_image"] for f in manifest["fields"] for v in f["views"])
    check_golden("fields/match_batch", {k: v for k, v in manifest.items() if k != "generated"})
    assert fields.load_or_match("9")["generated"] == manifest["generated"]  # cached manifest reused


# ---------------------------------------------------------------- analysis.classify


def _training_data(n_per_batch: int = 5):
    rng = np.random.default_rng(11)
    y = np.repeat(classify.BATCHES, n_per_batch)
    shift = np.zeros(len(classify.FEATURES))
    shift[[0, 3, 7]] = [1.6, -1.2, 0.9]
    X = rng.normal(size=(len(y), len(classify.FEATURES))) + np.array([int(b) - 2 for b in y])[:, None] * shift
    return X, y


@pytest.fixture(scope="module")
def training_data():
    return _training_data()


def test_selected_dlda(training_data):
    X, y = training_data
    model = classify.SelectedDLDA().fit(X, y)
    rng = np.random.default_rng(12)
    queries = rng.normal(size=(4, X.shape[1]))
    check_golden(
        "classify/selected_dlda",
        {
            "k": model.k,
            "cols": model.cols,
            "classes": model.classes,
            "inner_scores": model.inner_scores,
            "proba_train": model.proba(X),
            "proba_queries": model.proba(queries),
            "means": model.model.means,
            "var": model.model.var,
        },
    )


def test_dlda_parts(training_data):
    X, y = training_data
    m = classify.DiagonalLDA().fit(X[:, :4], y)
    check_golden(
        "classify/parts",
        {
            "anova_rank": classify.anova_rank(X, y),
            "scores": m.scores(X[:3, :4]),
            "balanced_accuracy": classify.balanced_accuracy(y, np.roll(y, 1)),
            "matrix": classify.matrix([{"kpis": {"porosity": 0.3, "crack_share": None}}]),
        },
    )


def test_leave_one_out(training_data):
    X, y = training_data
    pred, chosen = classify.leave_one_out(X, y)
    check_golden("classify/leave_one_out", {"pred": pred, "chosen": chosen})
