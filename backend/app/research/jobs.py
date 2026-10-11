import hashlib
import json
import logging
import os
import sqlite3
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .config import ResearchError, environment, require_key, settings_from_env, store_path
from .engine import explain
from .store import Store

logger = logging.getLogger(__name__)


def atomic_json(path: Path, value: dict) -> None:
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2))


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(value)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class ReportJobs:
    def __init__(self, directory: Path | None = None, runner=explain):
        self.directory = directory if directory is not None else store_path()
        self.runner = runner

    @contextmanager
    def connect(self):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        db = sqlite3.connect(self.directory / "jobs.sqlite3", timeout=10)
        try:
            db.execute(
                "CREATE TABLE IF NOT EXISTS jobs(job TEXT PRIMARY KEY, token TEXT, expires REAL, cancelled INTEGER)"
            )
            with db:
                yield db
        finally:
            db.close()

    def cancelled(self, job: str, token: str) -> bool:
        with self.connect() as db:
            row = db.execute("SELECT token,cancelled FROM jobs WHERE job=?", (job,)).fetchone()
        return row is None or row[0] != token or bool(row[1])

    def start(self, folder: Path, force: bool = False, background: bool = True) -> dict:
        env = environment()
        require_key(env)
        settings = settings_from_env(env)
        job, token = str(folder.resolve()), uuid.uuid4().hex
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT expires FROM jobs WHERE job=?", (job,)).fetchone()
            if row and row[0] > time.time():
                return {"status": "running", "stage": "Existing report job is already running"}
            active = db.execute("SELECT COUNT(*) FROM jobs WHERE expires>?", (time.time(),)).fetchone()[0]
            if active >= 2:
                raise ResearchError("capacity", "Two report jobs are active. Please retry after one finishes.")
            db.execute(
                "INSERT OR REPLACE INTO jobs VALUES(?,?,?,0)", (job, token, time.time() + settings.deadline + 45)
            )
        status = {"status": "running", "stage": "Starting evidence analysis", "generation": token}
        try:
            atomic_json(folder / "output/report_status.json", status)
            if background:
                threading.Thread(target=self.execute, args=(folder, token, settings, env, force), daemon=True).start()
            else:
                self.execute(folder, token, settings, env, force)
                return self.read(folder)
        except Exception:
            with self.connect() as db:
                db.execute("UPDATE jobs SET expires=0 WHERE job=? AND token=?", (job, token))
            raise
        return status

    def execute(self, folder: Path, token: str, settings, env: dict, force: bool = False) -> None:
        job, out = str(folder.resolve()), folder / "output"
        status_path = out / "report_status.json"
        store = None

        def progress(stage):
            if self.cancelled(job, token):
                raise ResearchError("cancelled", "Report generation was cancelled.")
            atomic_json(status_path, {"status": "running", "stage": stage.replace("_", " "), "generation": token})

        try:
            raw = (out / "facts.json").read_bytes()
            store = Store(self.directory)
            from ..paths import REPO_ROOT, SEM_BATCH_ID_FACTS_DIR
            from .baselines import reference_records

            store.seed(REPO_ROOT / "knowledge/SiC_SEM_reference_verified.json")
            references, _ = reference_records(SEM_BATCH_ID_FACTS_DIR)
            result = self.runner(
                raw.decode("utf-8-sig"),
                store,
                settings,
                env,
                progress=progress,
                cancelled=lambda: self.cancelled(job, token),
                force=force,
                references=references,
            )
            if self.cancelled(job, token):
                raise ResearchError("cancelled", "Report generation was cancelled.")
            if (out / "facts.json").read_bytes() != raw:
                raise ResearchError(
                    "input_changed", "The facts changed while the report was being generated; please retry."
                )
            payload = {
                **result.model_dump(),
                "generation": token,
                "check": [],
                "validation": "typed facts, citations and substantive review",
            }
            payload["audit"]["input_bytes_hash"] = hashlib.sha256(raw).hexdigest()
            atomic_text(out / "report.md", result.markdown)
            atomic_json(out / "report.json", payload)
            atomic_json(status_path, {"status": "done", "stage": "done", "generation": token})
        except Exception as exc:
            code = exc.code if isinstance(exc, ResearchError) else "internal"
            message = (
                str(exc) if isinstance(exc, ResearchError) else f"Report generation failed ({type(exc).__name__})."
            )
            logger.warning("Research report %s failed: %s", folder.name, code)
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                owner = db.execute("SELECT token FROM jobs WHERE job=?", (job,)).fetchone()
                if owner and owner[0] == token:
                    atomic_json(
                        status_path,
                        {
                            "status": "cancelled" if code == "cancelled" else "error",
                            "error": message,
                            "code": code,
                            "generation": token,
                        },
                    )
        finally:
            if store is not None:
                store.close()
            with self.connect() as db:
                db.execute("UPDATE jobs SET expires=0 WHERE job=? AND token=?", (job, token))

    def cancel(self, folder: Path) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT token,expires FROM jobs WHERE job=?", (str(folder.resolve()),)).fetchone()
            if not row or row[1] <= time.time():
                return self.read(folder)
            db.execute("UPDATE jobs SET cancelled=1 WHERE job=? AND token=?", (str(folder.resolve()), row[0]))
        return {"status": "running", "stage": "Cancellation requested"}

    def read(self, folder: Path) -> dict[str, Any]:
        out = folder / "output"
        path = out / "report_status.json"
        state = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        if (self.directory / "jobs.sqlite3").is_file():
            with self.connect() as db:
                active = db.execute("SELECT token,expires FROM jobs WHERE job=?", (str(folder.resolve()),)).fetchone()
            if active and active[1] > time.time() and active[0] != state.get("generation"):
                return {"status": "running", "stage": "Starting evidence analysis", "generation": active[0]}
        if state.get("status") == "running":
            with self.connect() as db:
                row = db.execute("SELECT token,expires FROM jobs WHERE job=?", (str(folder.resolve()),)).fetchone()
            if not row or row[1] <= time.time() or row[0] != state.get("generation"):
                return {
                    "status": "error",
                    "code": "interrupted",
                    "error": "The previous report job was interrupted. It is safe to retry.",
                }
            return state
        if state.get("status") in {"error", "cancelled"}:
            return state
        result_path = out / "report.json"
        if not result_path.is_file():
            return {"status": "none"}
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if state.get("generation") and result.get("generation") != state["generation"]:
            return {"status": "error", "error": "No complete result exists for the latest generation."}
        expected = result.get("audit", {}).get("input_bytes_hash")
        if expected and (
            not (out / "facts.json").is_file()
            or hashlib.sha256((out / "facts.json").read_bytes()).hexdigest() != expected
        ):
            return {"status": "none", "reason": "The input facts changed; generate a new report."}
        return result
