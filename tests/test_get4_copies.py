"""The two other GET4 entry points (batch_match/get4.py, sem_pipeline/src/get4.py), now shims over analysis.get4:
golden outputs of the functions their callers use, and that they agree exactly with analysis.get4.

The golden files under batch_match_get4/ were recorded from the former, older stand-alone batch_match copy,
whose analyse_image and CLI wrote fewer keys. Since the shim, batch_match gives analysis.get4's output (a
superset); those goldens are checked on the keys they contain (`_restricted_to`), so every value they pin
must still be reproduced unchanged."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from _get4_cases import (
    analyse_image_results,
    file_outputs,
    get4_args,
    material_outputs,
    phase_outputs,
    pooling_outputs,
    preprocessing_outputs,
)
from _support import REPO_ROOT, check_golden, compare, drop_keys, jsonable, load_golden


def _restricted_to(data, template):
    """`data` with only the dict keys that also occur in `template` (recursively; lists element-wise)."""
    if isinstance(data, dict) and isinstance(template, dict):
        return {k: _restricted_to(v, template[k]) for k, v in data.items() if k in template}
    if isinstance(data, list) and isinstance(template, list) and len(data) == len(template):
        return [_restricted_to(d, t) for d, t in zip(data, template, strict=True)]
    return data


def _check_legacy_golden(name: str, data) -> None:
    """check_golden on the part of `data` covered by a golden recorded from the former batch_match copy."""
    golden = load_golden(name)
    check_golden(name, data if golden is None else _restricted_to(jsonable(data), golden))


def _cases(g4, bse_float, striped_float, bse_tiffs, plain_tiff) -> dict:
    return {
        "file": file_outputs(g4, bse_tiffs[1], plain_tiff),
        "preprocessing": preprocessing_outputs(g4, bse_float, striped_float),
        "phase": phase_outputs(g4, bse_float),
        "pooling": pooling_outputs(g4),
        "material": material_outputs(g4, bse_tiffs[0]),
    }


@pytest.fixture(scope="module")
def outputs(analysis_get4, batch_match_modules, sem_get4, bse_float, striped_float, bse_tiffs, plain_tiff):
    """Every case run through each copy (JSON-able, arrays summarised)."""
    copies = {"analysis": analysis_get4, "batch_match": batch_match_modules.get4, "sem_pipeline": sem_get4}
    return {name: jsonable(_cases(g4, bse_float, striped_float, bse_tiffs, plain_tiff)) for name, g4 in copies.items()}


@pytest.fixture(scope="module")
def image_results(analysis_get4, batch_match_modules, sem_get4, bse_tiffs, tmp_path_factory):
    """analyse_image + analyse_batch through each entry point (--fast arguments: no per-image plots)."""
    copies = {"analysis": analysis_get4, "batch_match": batch_match_modules.get4, "sem_pipeline": sem_get4}
    out = {}
    for name, g4 in copies.items():
        results = analyse_image_results(g4, bse_tiffs, tmp_path_factory.mktemp(f"images_{name}"), get4_args)
        out[name] = {"images": jsonable(results), "batch": jsonable(g4.analyse_batch(results))}
    return out


@pytest.mark.parametrize("copy", ["batch_match", "sem_pipeline"])
@pytest.mark.parametrize("case", ["file", "preprocessing", "phase", "pooling", "material"])
def test_copy_golden(outputs, copy, case):
    check_golden(f"{copy}_get4/{case}", outputs[copy][case])


def test_shims_reexport_analysis(analysis_get4, batch_match_modules, sem_get4):
    """Both shims expose every analysis.get4 name as the very same object (plus batch_match's segment_bse)."""
    for shim in (batch_match_modules.get4, sem_get4):
        for name in analysis_get4.__all__:
            assert getattr(shim, name) is getattr(analysis_get4, name), name
    assert batch_match_modules.get4.segment_bse is analysis_get4.segment_intensity_classes


def test_material_golden_analysis(outputs):
    """batch_classifier.material_percentages' GET4 steps, through analysis.get4."""
    check_golden("analysis_get4/material", outputs["analysis"]["material"])


@pytest.mark.parametrize("copy", ["batch_match", "sem_pipeline"])
def test_copy_analyse_image_golden(image_results, copy):
    _check_legacy_golden(f"{copy}_get4/analyse_image_and_batch", image_results[copy])


@pytest.mark.parametrize("copy", ["batch_match", "sem_pipeline"])
@pytest.mark.parametrize("case", ["file", "preprocessing", "phase", "pooling", "material"])
def test_copy_matches_analysis(outputs, copy, case):
    """The numerical functions give identical results through every entry point (batch_match's segment_bse is
    segment_intensity_classes)."""
    diffs = compare(outputs["analysis"][case], outputs[copy][case], rtol=0.0, atol=0.0)
    assert not diffs, "\n".join(diffs[:20])


# Keys analysis.get4's analyse_image writes that the former batch_match copy did not (its goldens lack them).
ANALYSIS_ONLY_IMAGE_KEYS = {"detector", "max_autocorrelation_lag_px", "class_names"}


@pytest.mark.parametrize("copy", ["batch_match", "sem_pipeline"])
def test_copy_analyse_image_matches_analysis(image_results, copy):
    """Per-image results and batch pooling are identical (same keys, same values) through every entry point."""
    diffs = compare(image_results["analysis"], image_results[copy], rtol=0.0, atol=0.0)
    assert not diffs, "\n".join(diffs[:20])


def test_analyse_image_keys(image_results):
    """Every entry point writes the same per-image keys; batch_match now also writes the keys its former copy
    lacked (the intended change of the shim refactor)."""
    keys = {name: sorted(r["images"][0]) for name, r in image_results.items()}
    assert keys["sem_pipeline"] == keys["analysis"] == keys["batch_match"]
    assert set(keys["batch_match"]) >= ANALYSIS_ONLY_IMAGE_KEYS


# ---------------------------------------------------------------- the entry points' command lines


def _cli(cmd: list[str], cwd) -> None:
    done = subprocess.run(
        [sys.executable, *cmd], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300
    )
    assert done.returncode == 0, done.stdout[-2000:] + done.stderr[-4000:]


def _jsons(folder: Path) -> dict:
    return {p.name: json.loads(p.read_text()) for p in sorted(folder.glob("*.json"))}


@pytest.fixture(scope="module")
def cli_outputs(bse_tiffs, tmp_path_factory) -> dict:
    """The same three images through `python -m analysis.get4 --fast`, `python -m src.get4 --fast` (cwd
    sem_pipeline) and `python get4.py --bin 2` (cwd batch_match; the former copy's invocation, which had no
    --fast: --bin 2 is the same scale, but a full run, so it also writes the per-image plots)."""
    root = tmp_path_factory.mktemp("get4_copies_cli")
    images = [str(p) for p in bse_tiffs]
    _cli(["-m", "analysis.get4", *images, "--fast", "--out", str(root / "analysis")], REPO_ROOT)
    _cli(["-m", "src.get4", *images, "--fast", "--out", str(root / "sem_pipeline")], REPO_ROOT / "sem_pipeline")
    _cli(["get4.py", *images, "--bin", "2", "--out", str(root / "batch_match")], REPO_ROOT / "batch_match")
    outputs = {name: _jsons(root / name) for name in ("analysis", "sem_pipeline", "batch_match")}
    outputs["batch_match_png"] = sorted(p.name for p in (root / "batch_match").glob("*.png"))
    return outputs


def test_cli_sem_pipeline_identical_to_analysis(cli_outputs):
    assert cli_outputs["sem_pipeline"] == cli_outputs["analysis"]


def test_cli_batch_match(cli_outputs):
    """batch_match's CLI is now analysis.get4's: the same files and values as `--fast` at the same scale; only
    the run-mode settings differ (full run, per-image plots written). Values pinned from the former copy's
    smaller report format still hold."""
    ours, ref = cli_outputs["batch_match"], cli_outputs["analysis"]
    assert sorted(ours) == sorted(ref)
    for name in ("batch_uncertainty.json", "analysis_report.json"):
        assert ours[name]["analysis_settings"]["mode"] == "full"
        assert ours[name]["analysis_settings"]["per_image_plots_generated"] is True
    assert drop_keys(ours, {"analysis_settings"}) == drop_keys(ref, {"analysis_settings"})
    assert cli_outputs["batch_match_png"] == sorted(
        ["batch_uncertainty.png"] + [n.replace(".json", ".png") for n in ours if n.startswith("img_")]
    )
    _check_legacy_golden("batch_match_get4/cli_bin2", ours)
