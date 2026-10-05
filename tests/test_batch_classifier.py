"""batch_match/batch_classifier.py: golden fingerprint, texture and known-location features on synthetic images."""

import numpy as np
import pytest
from _support import check_golden, synthetic_image


@pytest.fixture(scope="module")
def bc(batch_match_modules):
    return batch_match_modules.batch_classifier


@pytest.fixture(scope="module")
def u8() -> np.ndarray:
    """576 x 576 uint8 image: after 2x binning exactly one 256 px texture tile plus a margin."""
    return synthetic_image(seed=40, shape=(576, 576), dtype=np.uint8)


def test_fingerprint(bc, u8, striped_float):
    striped = np.round(striped_float * 255).astype(np.uint8)
    result = {"plain": bc.fingerprint(u8), "striped": bc.fingerprint(striped)}
    assert len(result["plain"]) == 28
    check_golden("batch_classifier/fingerprint", result)


@pytest.mark.filterwarnings("ignore:divide by zero:RuntimeWarning", "ignore:invalid value:RuntimeWarning")
def test_texture_tiles(bc, u8):
    tiles = bc.texture_tiles(u8)
    assert tiles.shape[0] == 1
    flat = np.full((256, 256), 0.5)
    check_golden("batch_classifier/texture", {"tiles": tiles.tolist(), "flat_tile": bc.texture_tile(flat).tolist()})


def test_edge_map_and_matching(bc, u8):
    edges = bc.edge_map(u8)
    shifted = bc.edge_map(np.roll(u8, (40, -24), axis=(0, 1))[:400, :400])
    other = bc.edge_map(synthetic_image(seed=41, shape=(576, 576), dtype=np.uint8))
    scores = {
        "self": bc.match_score(edges, edges),
        "crop": bc.match_score(shifted, edges),
        "unrelated": bc.match_score(other, edges),
    }
    assert scores["crop"] > bc.MATCH_THRESHOLD > scores["unrelated"]
    refs = [
        {"edges": edges, "batch": "Batch_1", "location": "aaa"},
        {"edges": other, "batch": "Batch_2", "location": "bbb"},
    ]
    best = bc.find_known_location(np.roll(u8, (40, -24), axis=(0, 1))[:400, :400], refs)
    assert best[1:] == ("Batch_1", "aaa")
    check_golden(
        "batch_classifier/edge_map",
        {"edges": edges, "edges_binning4": bc.edge_map(u8, 4), "scores": scores, "best": list(best)},
    )


def test_load_u8_and_names(bc, bse_tiffs, plain_tiff):
    a = bc.load_u8(bse_tiffs[0])  # uint8: kept, edge columns cut
    b = bc.load_u8(bse_tiffs[1])  # uint16: rescaled by its maximum
    c = bc.load_u8(plain_tiff)
    assert a.dtype == b.dtype == np.uint8
    assert a.shape == (512, 512 - 2 * bc.EDGE)
    assert bc.parse_name("img_ab12_ETD.tif") == ("ab12", "SE")
    assert bc.parse_name("img_ab12_Inlens.tif") == ("ab12", "InLens")
    with pytest.raises(ValueError):
        bc.parse_name("scan_01.tif")
    check_golden("batch_classifier/load_u8", {"uint8": a, "uint16": b, "plain_uint16": c})


def test_material_percentages(bc, bse_tiffs):
    """GET4 phase fractions at 25 nm/px, as the material range rule uses them."""
    result = {p.name: bc.material_percentages(p) for p in bse_tiffs[:2]}
    check_golden("batch_classifier/material_percentages", result)


def test_range_rule_and_calibration(bc):
    materials = {
        "l1": {"pore": [0.20, 0.01], "graphite": [0.70, 0.01], "bright phase": [0.10, 0.005]},
        "l2": {"pore": [0.22, 0.01], "graphite": [0.68, 0.01], "bright phase": [0.10, 0.005]},
        "l3": {"pore": [0.30, 0.01], "graphite": [0.60, 0.01], "bright phase": [0.10, 0.005]},
        "l4": {"pore": [0.32, 0.01], "graphite": [0.58, 0.01], "bright phase": [0.10, 0.005]},
    }
    batch_of = {"l1": "Batch_1", "l2": "Batch_1", "l3": "Batch_2", "l4": "Batch_2"}
    ranges = bc.material_ranges(materials, batch_of, list(materials))
    query = {"pore": [0.21, 0.002], "graphite": [0.69, 0.002], "bright phase": [0.10, 0.002]}
    assert bc.range_vote(query, ranges) == "Batch_1"
    rng = np.random.default_rng(0)
    lp = rng.normal(size=(30, 3))
    y = rng.integers(0, 3, 30)
    conf = rng.uniform(0.3, 1.0, 50)
    right = rng.uniform(size=50) < conf
    batches = np.array(["Batch_1", "Batch_2", "Batch_3"])
    labels = batches[np.arange(30) % 3]
    X = rng.normal(size=(30, 5)) + (np.arange(30) % 3)[:, None] * np.array([1.0, 0.5, 0.0, 0.0, -0.5])
    X[3, 2] = np.nan
    model, means = bc.fit_view(X, labels)
    model_proba = np.exp(bc.log_proba(model, means, X[:6], batches))
    assert bc.decide(model_proba[0], 0.5, "Batch_2", batches)[1] == "material"
    check_golden(
        "batch_classifier/rules",
        {
            "ranges": ranges,
            "exclusive": bc.exclusive_phases(query, ranges),
            "softmax": bc.softmax(lp[:3]),
            "temperature": bc.fit_temperature(lp, y),
            "threshold": bc.choose_threshold(conf, right, 10),
            "lda_proba": model_proba,
            "location_proba": bc.location_proba(model_proba[:3]),
            "decisions": [list(bc.decide(p, 0.6, None, batches)) for p in model_proba],
        },
    )
