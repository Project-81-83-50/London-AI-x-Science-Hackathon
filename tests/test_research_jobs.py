import hashlib
import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_research_facts import sample

from app.research import jobs
from app.research.config import ResearchError
from app.research.jobs import ReportJobs
from app.research.models import Report


def fake_report(document, *_args, **_kwargs):
    data = json.loads(document)
    return Report(
        research_status="not_needed",
        explanations={data["sample_id"]: "- Checked example"},
        claims=[],
        facts={},
        sources={},
        markdown="## Example\n- Checked example",
        audit={"cache_hit": False},
    )


@pytest.fixture
def folder(tmp_path):
    run = tmp_path / "runs" / "example"
    (run / "output").mkdir(parents=True)
    (run / "output/facts.json").write_text(json.dumps(sample()))
    return run


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(jobs, "environment", lambda: {"ANTHROPIC_API_KEY": "test-only-not-a-real-key"})


def test_atomic_publication_preserves_input(folder, tmp_path, configured):
    manager = ReportJobs(tmp_path / "store", runner=fake_report)
    original = (folder / "output/facts.json").read_bytes()
    result = manager.start(folder, background=False)
    assert result["status"] == "done" and result["version"] == "crag-v1"
    assert result["audit"]["input_bytes_hash"] == hashlib.sha256(original).hexdigest()
    assert (folder / "output/facts.json").read_bytes() == original
    assert manager.read(folder) == result


def test_changed_input_is_not_served_as_current(folder, tmp_path, configured):
    manager = ReportJobs(tmp_path / "store", runner=fake_report)
    manager.start(folder, background=False)
    changed = sample()
    changed["decision"]["answer"] = "Batch_1"
    (folder / "output/facts.json").write_text(json.dumps(changed))
    assert manager.read(folder)["status"] == "none"


def test_duplicate_request_uses_shared_lease(folder, tmp_path, configured, monkeypatch):
    class DeferredThread:
        def __init__(self, **kwargs):
            pass

        def start(self):
            pass

    monkeypatch.setattr(jobs.threading, "Thread", DeferredThread)
    manager = ReportJobs(tmp_path / "store", runner=fake_report)
    assert manager.start(folder)["status"] == "running"
    duplicate = ReportJobs(tmp_path / "store", runner=fake_report).start(folder)
    assert "already" in duplicate["stage"]
    assert manager.cancel(folder)["status"] == "running"
    state = json.loads((folder / "output/report_status.json").read_text())
    assert manager.cancelled(str(folder.resolve()), state["generation"])


def test_old_cancel_does_not_cancel_new_generation(folder, tmp_path, configured):
    manager = ReportJobs(tmp_path / "store", runner=fake_report)
    with manager.connect() as db:
        db.execute("INSERT INTO jobs VALUES(?,?,?,1)", (str(folder.resolve()), "old-token", time.time() - 1))
    assert manager.start(folder, background=False)["status"] == "done"


def test_worker_error_never_publishes_a_partial_report(folder, tmp_path, configured):
    def fail(*_args, **_kwargs):
        raise ResearchError("test_failure", "A safe test error")

    manager = ReportJobs(tmp_path / "store", runner=fail)
    result = manager.start(folder, background=False)
    assert result["status"] == "error"
    assert not (folder / "output/report.json").exists()


def test_interrupted_job_is_retryable(folder, tmp_path):
    (folder / "output/report_status.json").write_text(json.dumps({"status": "running", "generation": "old"}))
    assert ReportJobs(tmp_path / "store").read(folder)["code"] == "interrupted"


def test_report_routes_are_compatible_and_do_not_require_gpu_python(folder, monkeypatch):
    from app.routers import v3

    monkeypatch.setattr(v3, "RUNS", folder.parent)
    monkeypatch.setattr(v3, "v3_python", lambda: pytest.fail("Research must not require a GPU interpreter"))
    monkeypatch.setattr(ReportJobs, "start", lambda self, run, force=False: {"status": "running", "stage": "analyzing"})
    monkeypatch.setattr(ReportJobs, "read", lambda self, run: {"status": "done", "markdown": "report", "check": []})
    monkeypatch.setattr(
        ReportJobs, "cancel", lambda self, run: {"status": "running", "stage": "Cancellation requested"}
    )
    app = FastAPI()
    app.include_router(v3.router)
    client = TestClient(app)
    assert client.post("/v3/jobs/example/report").json()["status"] == "running"
    assert client.get("/v3/jobs/example/report").json()["markdown"] == "report"
    assert client.post("/v3/jobs/example/report/cancel").json()["stage"] == "Cancellation requested"
    assert client.post("/v3/jobs/missing/report").status_code == 409
    assert client.post("/v3/jobs/bad.name/report").status_code == 404


def test_missing_key_fails_before_starting_a_job(folder, tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "environment", lambda: {})
    with pytest.raises(ResearchError, match="ANTHROPIC_API_KEY"):
        ReportJobs(tmp_path / "store").start(folder)
    assert not (folder / "output/report_status.json").exists()


def test_report_api_runs_the_complete_research_graph(folder, tmp_path, configured, monkeypatch):
    from types import SimpleNamespace

    from test_research_engine import Client, Provider, draft, passage, supported

    from app.research.engine import explain
    from app.research.facts import decode
    from app.research.models import Analysis, Grades, Question, Review, SearchPlan
    from app.research.store import Store
    from app.routers import v3

    document = decode(sample())
    source = passage(status="candidate")
    output = draft(document)
    from app.research.models import Citation, Claim

    output.explanations[0].claims.insert(
        1,
        Claim(
            id="science",
            sample_id="sample_one",
            kind="interpretation",
            text="ETD-dark solid {F0_0} is a detector-dependent contrast observation, not a unique chemical identification.",
            citations=[Citation(source_id=source.id, quote=source.text)],
        ),
    )
    writer = Client(
        [
            Analysis(
                done=True,
                reason="Interpret the selected detector proxy",
                questions=[Question(concept="detector_contrast", sample_ids=["sample_one"])],
            ),
            SearchPlan(focus="limitations", reason="Inspect detector guidance"),
            Grades(items=[supported(source)]),
            output,
            Review(findings=[]),
        ]
    )

    def runner(raw, store, settings, env, **kwargs):
        return explain(raw, store, settings, env, client=writer, provider=Provider([source]), **kwargs)

    class InlineThread:
        def __init__(self, target, args, daemon):
            self.target, self.args = target, args

        def start(self):
            self.target(*self.args)

    manager = ReportJobs(tmp_path / "corpus", runner=runner)
    monkeypatch.setattr(jobs, "threading", SimpleNamespace(Thread=InlineThread))
    monkeypatch.setattr(jobs, "ReportJobs", lambda: manager)
    monkeypatch.setattr(Store, "seed", lambda *_args: None)
    monkeypatch.setattr(v3, "RUNS", folder.parent)
    app = FastAPI()
    app.include_router(v3.router)
    client = TestClient(app)
    original = (folder / "output/facts.json").read_bytes()
    assert client.post("/v3/jobs/example/report").status_code == 200
    result = client.get("/v3/jobs/example/report").json()
    assert result["status"] == "done", result
    assert result["audit"]["validator_passed"] and result["audit"]["reviewer_passed"]
    assert list(result["explanations"]) == ["sample_one"]
    assert [step["route"] for step in result["audit"]["trace"] if step["stage"] == "corrective_retrieval"] == [
        "unsupported",
        "supported",
    ]
    assert (folder / "output/facts.json").read_bytes() == original
    assert (folder / "output/report.md").read_text() == result["markdown"]


def test_late_failure_cannot_overwrite_a_newer_generation(folder, tmp_path):
    from app.research.models import Settings

    manager = ReportJobs(tmp_path / "corpus", runner=fake_report)
    with manager.connect() as db:
        db.execute("INSERT INTO jobs VALUES(?,?,?,0)", (str(folder.resolve()), "new", time.time() + 200))
    state = {"status": "running", "stage": "new job", "generation": "new"}
    (folder / "output/report_status.json").write_text(json.dumps(state))
    manager.execute(folder, "old", Settings(), {})
    assert manager.read(folder) == state
