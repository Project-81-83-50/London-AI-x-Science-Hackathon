"""FastAPI backend (backend/app) through TestClient, with every data path redirected to a temporary folder.

app.paths defines the data locations, but routers import them by name (`from ..paths import RAW_DATA_DIR`) and
derive more (unknown.UNKNOWN_DIR, ANALYSIS_LOG, ...). The `api` fixture therefore rewrites EVERY Path attribute
under <repo>/data in every loaded app.* module, so no test reads or writes the repository's data/ folder.
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from _support import REPO_ROOT, synthetic_image, write_tiff
from fastapi.testclient import TestClient

REPO_DATA = REPO_ROOT / "data"


class _InlineThread:
    def __init__(self, target, daemon=None):
        self.target = target

    def start(self):
        self.target()


def _redirect(value, tmp_data: Path):
    if isinstance(value, Path):
        try:
            return tmp_data / value.relative_to(REPO_DATA)
        except ValueError:
            return None
    return None


@pytest.fixture()
def api(tmp_path, monkeypatch):
    """TestClient on app.main.app with data/ -> tmp_path/data and the unknown-batch job runner stubbed out."""
    from app import main, paths  # noqa: F401  (imports every router module)
    from app.routers import unknown

    tmp_data = tmp_path / "data"
    patched = []
    for name, module in list(sys.modules.items()):
        if name != "app" and not name.startswith("app."):
            continue
        for attr, value in list(vars(module).items()):
            new = _redirect(value, tmp_data)
            if new is not None:
                monkeypatch.setattr(module, attr, new)
                patched.append(f"{name}.{attr}")
    assert "app.paths.RAW_DATA_DIR" in patched and "app.routers.unknown.UNKNOWN_DIR" in patched

    runs = []
    monkeypatch.setattr(unknown, "_run_analysis", lambda: runs.append("analysis"))
    # run the job "thread" synchronously, so the stub has run when the request returns
    monkeypatch.setattr(unknown, "threading", SimpleNamespace(Thread=_InlineThread))
    monkeypatch.setattr(unknown, "_job", {"state": "idle", "started": None, "finished": None, "returncode": None})

    class Api:
        client = TestClient(main.app)
        raw = tmp_data / "raw"
        processed = tmp_data / "processed"
        job_runs = runs
        unknown_module = unknown

    return Api


def test_no_app_path_points_into_repo_data(api):
    for name, module in sys.modules.items():
        if name == "app" or name.startswith("app."):
            for attr, value in vars(module).items():
                if isinstance(value, Path):
                    assert not value.is_relative_to(REPO_DATA), f"{name}.{attr} = {value}"


def test_health(api):
    r = api.client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def _batch_with_images(api, batch="batch_1") -> Path:
    folder = api.raw / batch
    img = synthetic_image(60, (64, 80), np.uint8)
    for name in ("img_ab12_BSE.tif", "img_ab12_ETD.tif", "img_cd34_Inlens.tif", "img_ab12_SE (2).tif"):
        write_tiff(folder / name, img)
    (folder / "notes.txt").write_text("not an image")
    return folder


def test_list_images_grouped_by_filename(api):
    _batch_with_images(api)
    r = api.client.get("/batches/1/images")
    assert r.status_code == 200
    assert r.json() == [
        {
            "specimen_id": "ab12",
            "grouping": "filename",
            "images": [
                {"filter": "BSE", "filename": "img_ab12_BSE.tif"},
                {"filter": "ETD", "filename": "img_ab12_ETD.tif"},
                {"filter": "SE", "filename": "img_ab12_SE (2).tif"},
            ],
        },
        {
            "specimen_id": "cd34",
            "grouping": "filename",
            "images": [{"filter": "Inlens", "filename": "img_cd34_Inlens.tif"}],
        },
    ]


def test_list_images_uses_matching_field_manifest(api):
    _batch_with_images(api)
    manifest = {
        "fields": [
            {
                "field_id": "F01",
                "location": "ab12",
                "location_recovered": True,
                "confidence": "strong",
                "filename_codes": ["ab12", "cd34"],
                "views": [
                    {"filename": "img_cd34_Inlens.tif", "detector": "InLens"},
                    {"filename": "img_ab12_BSE.tif", "detector": "BSE"},
                    {"filename": "img_ab12_ETD.tif", "detector": "ETD"},
                ],
            },
            {
                "field_id": "F02",
                "confidence": "single view",
                "filename_codes": ["ab12"],
                "views": [{"filename": "img_ab12_SE (2).tif", "detector": "ETD"}],
            },
        ]
    }
    (api.processed / "fields").mkdir(parents=True)
    (api.processed / "fields" / "batch_1.json").write_text(json.dumps(manifest))
    body = api.client.get("/batches/1/images").json()
    assert [g["specimen_id"] for g in body] == ["F02", "ab12"]
    assert all(g["grouping"] == "matched" for g in body)
    assert [i["filename"] for i in body[1]["images"]] == ["img_ab12_BSE.tif", "img_cd34_Inlens.tif", "img_ab12_ETD.tif"]


def test_images_unknown_batch_and_missing_folder(api):
    assert api.client.get("/batches/abc/images").status_code == 404
    assert api.client.get("/batches/7/images").status_code == 404  # numeric but no folder
    (api.raw / "unknown").mkdir(parents=True)
    assert api.client.get("/batches/unknown/images").json() == []


def test_image_preview_and_download(api):
    folder = _batch_with_images(api)
    r = api.client.get("/batches/1/images/img_ab12_BSE.tif", params={"download": True})
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/tiff"
    assert r.content == (folder / "img_ab12_BSE.tif").read_bytes()
    r = api.client.get("/batches/1/images/img_ab12_BSE.tif")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert len(list((api.processed / "previews" / "batch_1").glob("img_ab12_BSE_*.jpg"))) == 1
    assert api.client.get("/batches/1/images/notes.txt").status_code == 404
    assert api.client.get("/batches/1/images/img_zz99_BSE.tif").status_code == 404


# ---------------------------------------------------------------- generated reports


def test_get4_reports(api):
    assert api.client.get("/batches/1/uncertainty").status_code == 404
    assert api.client.get("/batches/1/uncertainty", params={"detector": "XYZ"}).status_code == 422
    assert api.client.get("/batches/x/uncertainty").status_code == 404
    folder = api.processed / "get4" / "batch_1" / "BSE"
    folder.mkdir(parents=True)
    report = {"detector": "BSE", "phases": {"pore": {"phi": 0.2}}}
    (folder / "batch_uncertainty.json").write_text(json.dumps(report))
    (folder / "analysis_report.json").write_text("{not json")
    assert api.client.get("/batches/1/uncertainty", params={"detector": "bse"}).json() == report
    assert api.client.get("/batches/1/analysis-report").status_code == 500
    unknown = api.processed / "get4" / "unknown" / "INLENS"
    unknown.mkdir(parents=True)
    (unknown / "analysis_report.json").write_text(json.dumps({"ok": True}))
    assert api.client.get("/batches/unknown/analysis-report", params={"detector": "Inlens"}).json() == {"ok": True}


def test_kpi_reports(api):
    r = api.client.get("/batches/2/kpi-report")
    assert r.status_code == 404
    assert "analysis.kpis" in r.json()["detail"]
    assert api.client.get("/kpi-reports/summary").status_code == 404
    folder = api.processed / "batch_kpis" / "batch_2"
    (folder / "overlays").mkdir(parents=True)
    (folder / "report.json").write_text(json.dumps({"batch": "2", "locations": []}), encoding="utf-8")
    (folder / "overlays" / "L1.jpg").write_bytes(b"\xff\xd8\xff\xe0jpeg")
    assert api.client.get("/batches/2/kpi-report").json() == {"batch": "2", "locations": []}
    assert api.client.get("/batches/2/kpi-report/overlays/L1").content == b"\xff\xd8\xff\xe0jpeg"
    assert api.client.get("/batches/2/kpi-report/overlays/L2").status_code == 404
    assert api.client.get("/batches/2/kpi-report/overlays/..%2Fx").status_code == 404


def test_unknown_reports_missing(api):
    assert api.client.get("/unknown/classification").status_code == 404
    assert api.client.get("/unknown/batch-match").status_code == 404
    assert api.client.get("/unknown/batch-match/evaluation").status_code == 404
    classification = api.processed / "classification" / "unknown.json"
    classification.parent.mkdir(parents=True)
    classification.write_text(json.dumps({"locations": []}))
    assert api.client.get("/unknown/classification").json() == {"locations": []}


# ---------------------------------------------------------------- unknown-batch uploads


def _tiff_bytes(tmp_path, seed=61) -> bytes:
    return write_tiff(tmp_path / f"upload_{seed}.tif", synthetic_image(seed, (32, 32), np.uint8)).read_bytes()


@pytest.mark.parametrize(
    "name",
    [
        "scan.tif",
        "img_ab12_BSE.tiff",
        "img_ab_12_BSE.tif",
        "img_ab12_XYZ.tif",
        "img_ab12_BSE.png",
        "img_ab12_BSE (2).tif",
    ],
)
def test_upload_rejects_bad_names(api, tmp_path, name):
    r = api.client.put(f"/batches/unknown/images/{name}", content=_tiff_bytes(tmp_path))
    assert r.status_code == 422
    assert not (api.raw / "unknown").is_dir() or not list((api.raw / "unknown").iterdir())


def test_upload_rejects_non_tiff_and_empty(api):
    r = api.client.put("/batches/unknown/images/img_ab12_BSE.tif", content=b"\x89PNG\r\n\x1a\n" + b"0" * 100)
    assert r.status_code == 415
    r = api.client.put("/batches/unknown/images/img_ab12_BSE.tif", content=b"")
    assert r.status_code == 422
    assert list((api.raw / "unknown").iterdir()) == []  # no partial / temporary file left


def test_upload_overwrite_duplicate_and_delete(api, tmp_path):
    data = _tiff_bytes(tmp_path)
    r = api.client.put("/batches/unknown/images/img_ab12_BSE.tif", content=data)
    assert r.status_code == 200
    assert r.json() == {"filename": "img_ab12_BSE.tif", "bytes": len(data), "replaced": False}
    assert (api.raw / "unknown" / "img_ab12_BSE.tif").read_bytes() == data
    assert api.client.put("/batches/unknown/images/img_ab12_BSE.tif", content=data).status_code == 409
    assert api.client.put("/batches/unknown/images/img_cd34_BSE.tif", content=data).status_code == 409  # same bytes
    other = _tiff_bytes(tmp_path, seed=62)
    r = api.client.put("/batches/unknown/images/img_ab12_BSE.tif", params={"overwrite": True}, content=other)
    assert r.status_code == 200 and r.json()["replaced"] is True
    assert api.job_runs == []  # uploading never starts the analysis

    assert api.client.delete("/batches/unknown/images/img_zz99_BSE.tif").status_code == 404
    assert api.client.delete("/batches/unknown/images/bad.tif").status_code == 422
    r = api.client.delete("/batches/unknown/images/img_ab12_BSE.tif")
    assert r.json() == {"deleted": "img_ab12_BSE.tif", "remaining": 0}


def test_unknown_analysis_job(api, tmp_path):
    assert api.client.post("/unknown/analysis").status_code == 422  # no images yet
    api.client.put("/batches/unknown/images/img_ab12_BSE.tif", content=_tiff_bytes(tmp_path))
    r = api.client.post("/unknown/analysis")
    assert r.status_code == 200
    assert r.json()["state"] == "running" and r.json()["images"] == 1
    assert api.job_runs == ["analysis"]  # the stub ran instead of the real subprocess chain
    # while "running", uploads, deletes and a second start are refused
    assert api.client.post("/unknown/analysis").status_code == 409
    assert (
        api.client.put("/batches/unknown/images/img_cd34_BSE.tif", content=_tiff_bytes(tmp_path, 63)).status_code == 409
    )
    assert api.client.delete("/batches/unknown/images/img_ab12_BSE.tif").status_code == 409
