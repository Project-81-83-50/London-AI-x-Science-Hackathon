"""Characterisation tests of analysis.get4 (the GET4 copy the backend runs): golden outputs on synthetic images."""

import json
import subprocess
import sys

import numpy as np
import pytest
from _get4_cases import (
    analyse_image_results,
    file_outputs,
    get4_args,
    phase_outputs,
    pooling_outputs,
    preprocessing_outputs,
)
from _support import REPO_ROOT, check_golden, drop_keys

from analysis import get4


@pytest.fixture(scope="module")
def image_results(bse_tiffs, tmp_path_factory) -> list[dict]:
    """analyse_image (fast mode, common 50 nm target) on the three synthetic BSE TIFFs."""
    return analyse_image_results(get4, bse_tiffs, tmp_path_factory.mktemp("get4_images"), get4_args)


def test_file_loading(bse_tiffs, plain_tiff):
    check_golden("analysis_get4/file_outputs", file_outputs(get4, bse_tiffs[1], plain_tiff))


def test_read_meta_pixel_size(bse_tiffs, plain_tiff):
    assert get4.read_meta(bse_tiffs[0])["pixel_size_nm"] == pytest.approx(25.0)
    assert get4.read_meta(plain_tiff) == {"pixel_size_nm": None, "databar_rows": 0, "n_pages": 1}


def test_preprocessing_and_segmentation(bse_float, striped_float):
    out = preprocessing_outputs(get4, bse_float, striped_float)
    assert out["destripe_clean"] == {"unchanged": True, "applied": []}
    assert out["destripe_striped"]["applied"] == ["horizontal scan lines"]
    check_golden("analysis_get4/preprocessing", out)


def test_phase_statistics(bse_float):
    check_golden("analysis_get4/phase_outputs", phase_outputs(get4, bse_float))


def test_pooling():
    check_golden("analysis_get4/pooling", pooling_outputs(get4))


def test_analyse_image(image_results):
    assert [r["image"] for r in image_results] == ["img_aaa111_BSE.tif", "img_bbb222_BSE.tif", "img_ccc333_BSE.tif"]
    for r in image_results:
        assert set(r["phases"]) == set(get4.PHASES.values())
        assert sum(p["phi"] for p in r["phases"].values()) == pytest.approx(1.0)
    check_golden("analysis_get4/analyse_image", image_results)


def test_analyse_batch(image_results):
    batch = get4.analyse_batch(image_results)
    prior = get4.analyse_batch(image_results[:2], tau2_prior={"pore": 1e-3, "graphite": 0.0})
    single = get4.analyse_batch(image_results[:1])
    check_golden("analysis_get4/analyse_batch", {"three": batch, "two_with_prior": prior, "one": single})


def test_quality_flags_and_target(image_results, bse_tiffs):
    refs = [r["quality"] for r in image_results]
    flags = {
        "vs_rest": [
            get4.quality_flags(r["quality"], [q for j, q in enumerate(refs) if j != i])
            for i, r in enumerate(image_results)
        ],
        "shifted": get4.quality_flags({**refs[0], "median": refs[0]["median"] + 0.2, "separability": 0.5}, refs),
        "no_reference": get4.quality_flags(refs[0], []),
    }
    metas = [get4.read_meta(p) for p in bse_tiffs]
    targets = {
        "fast_bin2": get4.resolve_target(metas, get4_args("."), None),
        "target_px": get4.resolve_target(metas, get4_args(".", target_px=40.0), None),
        "baseline": get4.resolve_target(metas, get4_args("."), {"target_pixel_nm": 75.0}),
        "no_pixel_sizes": get4.resolve_target([{"pixel_size_nm": None}], get4_args("."), None),
    }
    with pytest.raises(ValueError):
        get4.resolve_target(metas + [{"pixel_size_nm": None}], get4_args("."), None)
    check_golden("analysis_get4/quality_flags_and_target", {"flags": flags, "targets": targets})


def test_compare_lots(image_results, tmp_path):
    def lot(results, name):
        path = tmp_path / f"{name}.json"
        images = [{"image": r["image"], "imaging_flags": []} for r in results]
        path.write_text(json.dumps({"phases": get4.analyse_batch(results), "target_pixel_nm": 50.0, "images": images}))
        return path

    a, b = lot(image_results[:2], "a"), lot(image_results[1:], "b")
    single = lot(image_results[:1], "single")
    result = {
        "two_vs_two": get4.compare_lots(a, b, {"pore": 0.02}, 0.10),
        "single_vs_two": get4.compare_lots(single, b, {}, 0.05),
    }
    check_golden("analysis_get4/compare_lots", drop_keys(result, {"lot_a", "lot_b"}))


def test_collect_images(bse_tiffs, triplet_tiffs):
    folder = triplet_tiffs["BSE"].parent
    assert get4.collect_images([str(folder)]) == [triplet_tiffs["BSE"]]
    assert get4.collect_images([str(folder)], "etd") == [triplet_tiffs["ETD"]]
    assert len(get4.collect_images([str(folder)], "all")) == 3
    assert get4.collect_images([str(p) for p in bse_tiffs]) == bse_tiffs
    assert get4._location_of("img_AbC12_BSE (2).tif") == "abc12"
    assert get4._location_of("scan.tif") is None


# ---------------------------------------------------------------- the CLI, as the backend runs it

VOLATILE = {"lot_a", "lot_b"}


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    done = subprocess.run(
        [sys.executable, "-m", "analysis.get4", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    assert done.returncode == 0, done.stdout[-2000:] + done.stderr[-4000:]
    return done


@pytest.fixture(scope="module")
def cli_runs(bse_tiffs, tmp_path_factory) -> dict:
    """`python -m analysis.get4 --fast` on three images; then two of them against that run as --baseline;
    then --compare of the two batch JSONs."""
    root = tmp_path_factory.mktemp("get4_cli")
    a, b, cmp_dir = root / "lot_a", root / "lot_b", root / "compare"
    _run_cli(*map(str, bse_tiffs), "--fast", "--out", str(a))
    baseline = a / "batch_uncertainty.json"
    _run_cli(str(bse_tiffs[0]), str(bse_tiffs[2]), "--fast", "--baseline", str(baseline), "--out", str(b))
    stdout = _run_cli("--compare", str(baseline), str(b / "batch_uncertainty.json"), "--out", str(cmp_dir)).stdout
    return {"a": a, "b": b, "compare": cmp_dir, "compare_stdout": stdout}


def _outputs(folder) -> dict:
    return {p.name: drop_keys(json.loads(p.read_text()), VOLATILE) for p in sorted(folder.glob("*.json"))}


def test_cli_fast_batch(cli_runs):
    a = cli_runs["a"]
    out = _outputs(a)
    assert sorted(out) == [
        "analysis_report.json",
        "batch_uncertainty.json",
        "img_aaa111_BSE_uncertainty.json",
        "img_bbb222_BSE_uncertainty.json",
        "img_ccc333_BSE_uncertainty.json",
    ]
    assert out["analysis_report.json"] == out["batch_uncertainty.json"]
    assert (a / "batch_uncertainty.png").is_file()
    assert not list(a.glob("img_*_uncertainty.png"))  # --fast skips per-image plots
    check_golden("analysis_get4/cli_fast", out)


def test_cli_baseline_and_compare(cli_runs):
    out = {"baseline_run": _outputs(cli_runs["b"]), "compare": _outputs(cli_runs["compare"])}
    assert "strongest_evidence" in out["compare"]["comparison.json"]
    check_golden("analysis_get4/cli_baseline_compare", out)


def test_cli_rejects_bad_arguments():
    done = subprocess.run(
        [sys.executable, "-m", "analysis.get4", "--list-only"], cwd=REPO_ROOT, capture_output=True, text=True
    )
    assert done.returncode == 2
    assert "--list-only requires --project" in done.stderr


def test_float_images_are_not_rescaled_by_dtype(tmp_path):
    """Float TIFFs are scaled by their maximum, integer TIFFs by the dtype range."""
    from _support import write_tiff

    arr = np.full((64, 64), 0.5, np.float32)
    arr[0, 0] = 2.0
    path = write_tiff(tmp_path / "float.tif", arr)
    img, info = get4.load_image(path, get4.read_meta(path), bin_factor=1)
    assert info["full_scale"] == pytest.approx(2.0)
    assert float(img[1, 1]) == pytest.approx(0.25)
