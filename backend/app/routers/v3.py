"""lucas-sem-analysis v3 live: the v3 batch decision on the unknown batch, the Demo page (run v3 on one uploaded
location) and the Pipeline page (every step's output, plus a multi-agent Claude report).

v3's models need PyTorch and the trained weights, which live in lucas-sem-analysis-v3/ (V3_PROJECT_DIR; models are a
release asset, see README) and a Python with PyTorch (V3_PYTHON, or the path in lucas-sem-analysis-v3/website/v3_python.txt,
which START_WEBSITE.bat writes). Runs are stored in lucas-sem-analysis-v3/website/runs.
"""

import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import numpy as np
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from PIL import Image

from ..paths import CLASSIFICATION_PATH, LUCAS_DIR, REPO_ROOT

router = APIRouter()
Image.MAX_IMAGE_PIXELS = None
V3_PROJECT_DIR = Path(os.environ.get("V3_PROJECT_DIR") or (LUCAS_DIR if (LUCAS_DIR / "website" / "agents.py").is_file()
                                                           else REPO_ROOT.parents[1]))
RUNS = V3_PROJECT_DIR / "website" / "runs"
EVAL_PATH = LUCAS_DIR / "outputs" / "metrics" / "v3_eval.json"
DETECTORS = ("BSE", "Inlens", "ETD")
STEPS = ["read_preprocess_s", "segmentation_s", "features_s", "dino_s", "classify_explain_s", "known_location_s",
         "get4_range_rule_s", "total_s", "kpi_s", "decision_s"]
JOBS = {}            # running / finished demo runs in this backend session
RUN_ID = re.compile(r"^[A-Za-z0-9_]+$")


def v3_python():
    """The Python that runs lucas-sem-analysis (with PyTorch): V3_PYTHON, else <V3_PROJECT_DIR>/website/v3_python.txt."""
    if os.environ.get("V3_PYTHON"):
        return os.environ["V3_PYTHON"]
    cfg = V3_PROJECT_DIR / "website" / "v3_python.txt"
    if cfg.is_file() and Path(cfg.read_text(encoding="utf-8").strip()).is_file():
        return cfg.read_text(encoding="utf-8").strip()
    raise RuntimeError(f"set V3_PYTHON or write the path of a Python with PyTorch into {cfg}")


def run_dir(job):
    if not RUN_ID.fullmatch(job):
        raise HTTPException(404, "unknown run")
    return RUNS / job


def preview(tif, out, width=1400):
    if out.exists():
        return
    a = np.asarray(Image.open(tif))
    a = (a[..., 1] if a.ndim == 3 else a).astype(np.float32)
    lo, hi = np.percentile(a[::4, ::4], [0.5, 99.5])
    im = Image.fromarray(np.clip((a - lo) / max(hi - lo, 1) * 255, 0, 255).astype(np.uint8))
    im.resize((width, round(im.height * width / im.width)), Image.LANCZOS).save(out, quality=85)


# ---------------------------------------------------------------- current method: KPI call + v3 explanation

W_KPI, W_MATERIAL = 0.9, 0.1   # final probability = 90 % KPI model + 10 % v3 material model (U-Net + DINOv2)
KPI_MEANING = {"etd_dark_solid": "area that is dark in ETD but solid in BSE (sub-surface pores, shadowed edges or binder)"}


def _fmt(v, unit, scale):
    x = v * (scale or 1)
    return f"{x:.1f} %" if unit == "%" else f"{x:.2f} {unit}"


B12_PATH = LUCAS_DIR / "outputs" / "metrics" / "same_batch.json"
B12_UNET = {"pore_all_frac": ("total porosity (U-Net segmentation)", "%"),
            "pore_open_excess": ("open, grey-floored pores", "%"),
            "pore_deep_frac": ("deep (BSE-black) pores", "%"),
            "siox_frac": ("SiOx area", "%"),
            "siox_ecd_aw": ("SiOx particle size, area-weighted", "um"),
            "bse_siox_contrast_ratio": ("SiOx-to-graphite brightness in BSE", "ratio"),
            "etd_graphite_roughness": ("graphite surface texture in ETD", "a.u.")}
B12_KPI = {"etd_dark_solid": "hidden sub-surface pores (dark in ETD, solid in BSE)",
           "porosity_confirmed_etd": "pores confirmed in ETD",
           "pore_interface_density": "pore-solid interface density",
           "bruggeman_tortuosity": "pore-network tortuosity (lower = more open)",
           "pore_ecd_d50": "median pore size"}
B12_IMAGING = {"bse_siox_contrast_ratio", "etd_graphite_roughness"}


def batch12_block(f, kc):
    """How Batch_1 and Batch_2 differ (reference data), and where this location sits between them."""
    rows = []
    if B12_PATH.is_file():
        es = json.loads(B12_PATH.read_text(encoding="utf-8")).get("B1_vs_B2_effect_sizes", {})
        for key, (name, unit) in B12_UNET.items():
            if key in es:
                e = es[key]
                lo, hi = e["ci95"]
                rows.append({"measure": name, "unit": unit, "source": "U-Net segmentation / v3 measurements",
                             "Batch_1_mean": round(e["B1_mean"], 3), "Batch_2_mean": round(e["B2_mean"], 3),
                             "Batch_2_minus_Batch_1": round(e["B2_minus_B1"], 3), "ci95": [round(lo, 3), round(hi, 3)],
                             "evidence": "clear (95 % interval excludes zero)" if lo * hi > 0 else "weak (interval includes zero)",
                             "may_reflect_imaging": key in B12_IMAGING})
    kpis = {r["id"]: r for r in kc.get("all_kpis", [])}
    for key, name in B12_KPI.items():
        if key in kpis:
            r = kpis[key]
            rows.append({"measure": name, "unit": r["unit"], "source": "KPI model measurements (Guanyi)",
                         "Batch_1_mean": r["batch_means"].get("Batch_1"), "Batch_2_mean": r["batch_means"].get("Batch_2"),
                         "this_location": r["value"], "may_reflect_imaging": key == "etd_dark_solid"})
    pore = f["phases"]["three_class_pct"]["pore"]
    p1 = next((r["Batch_1_mean"] for r in rows if r["measure"].startswith("total porosity")), None)
    p2 = next((r["Batch_2_mean"] for r in rows if r["measure"].startswith("total porosity")), None)
    where = None
    if p1 is not None and p2 is not None:
        where = (f"this location's porosity is {pore:.1f} %, " +
                 ("closer to Batch_1's mean" if abs(pore - p1) < abs(pore - p2) else "closer to Batch_2's mean") +
                 f" ({p1:.1f} % vs {p2:.1f} %)")
    return {"summary": ("Batch_1 and Batch_2 differ, but subtly. Batch_2 is more porous on average (about 3.5 percentage "
                        "points more pores, with more open and hidden sub-surface pores and a more open pore network); "
                        "Batch_1 has slightly more and larger SiOx particles, a lower SiOx-to-graphite brightness in BSE "
                        "and a rougher graphite surface texture in ETD. The batches' location ranges overlap (porosity "
                        "about 11-17 % in Batch_1 vs 14-23 % in Batch_2), so a single location in the overlap is hard to "
                        "call, even though the batches differ."),
            "differences": rows, "this_location": where,
            "caveat": "7 reference locations per batch; differences marked may_reflect_imaging can partly come from how "
                      "the images were taken or prepared"}


def current_method(folder, bse, inlens=None, etd=None, rerun_kpi=True):
    """Decision = Guanyi's KPI classifier (analysis.kpi_single); explanation = v3 (segmentation, DINOv2 evidence,
    composition with GET4 sampling error bars, known-spot and range checks). No fingerprint, no texture model."""
    out = folder / "output"
    cmd = [sys.executable, "-m", "analysis.kpi_single", "--bse", str(bse), "--out", str(out / "kpi_call.json")]
    if inlens:
        cmd += ["--inlens", str(inlens)]
    if etd:
        cmd += ["--etd", str(etd)]
    if rerun_kpi or not (out / "kpi_call.json").is_file():
        r = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            raise RuntimeError("KPI model failed: " + r.stdout[-800:] + r.stderr[-800:])
    kc = json.loads((out / "kpi_call.json").read_text(encoding="utf-8"))
    f = json.loads((out / "facts.json").read_text(encoding="utf-8"))
    old = f.get("decision", {})
    mat_pick = (old.get("material_side_pick") or old.get("material_model_pick")
                or (f.get("material_model") or {}).get("predicted_batch"))
    mat_cal = old.get("material_side_calibrated") or old.get("material_model_calibrated")
    if mat_cal:
        final = {b: round(W_KPI * kc["probabilities"][b] + W_MATERIAL * mat_cal[b], 4) for b in kc["probabilities"]}
    else:
        final = dict(kc["probabilities"])
    d0 = kc["drivers"][0]
    means = ", ".join(f"{b.replace('_', ' ')} {_fmt(v, d0['unit'], d0['scale'])}" for b, v in d0["batch_means"].items())
    driver = (f"{d0['name']} ({KPI_MEANING.get(d0['feature'], d0['feature'])}) is "
              f"{_fmt(d0['value'], d0['unit'], d0['scale'])}; batch means {means}")
    if old.get("answer_type") in ("refused", "known_location"):
        decision = {k: old[k] for k in ("answer", "answer_type", "confidence", "reasons") if k in old}
        if old.get("answer_type") == "known_location":
            decision["confidence"] = "High (known location)"
    else:
        ans = max(final, key=final.get)
        agree = mat_pick == ans
        kpi_top = max(kc["probabilities"].values())
        tier = "High" if kpi_top >= 0.5 and agree else "Low"   # two tiers only
        decision = {"answer": ans, "answer_type": "specific", "confidence": tier,
                    "method": "90 % KPI classifier (Guanyi: diagonal LDA on the most batch-separating measured KPI, "
                              "fitted on the 31 reference locations) + 10 % v3 material model (U-Net segmentation + "
                              "DINOv2, calibrated; no fingerprint)",
                    "probabilities": final, "weights": {"kpi_model": W_KPI, "v3_material_model": W_MATERIAL},
                    "kpi_probabilities": kc["probabilities"],
                    "prediction_set": [b for b, p in final.items() if p >= 0.2],
                    "material_model_pick": mat_pick, "material_model_agrees": agree,
                    "material_model_calibrated": mat_cal,
                    "reasons": [f"Final probability = {W_KPI:.0%} KPI model + {W_MATERIAL:.0%} v3 material model.",
                                f"KPI model: {driver}.",
                                f"Our material model (U-Net segmentation + DINOv2) picks {mat_pick}: "
                                + ("agrees." if agree else "disagrees, so the confidence is Low.")]
                    + ([] if kpi_top >= 0.5 else [f"The KPI model's top probability is {kpi_top:.0%}, below 50 %, "
                                                   "so the confidence is Low."])
                    + ["Confidence rule: High when the KPI model is at least 50 % sure and the v3 material model "
                       "agrees; otherwise Low."]}
    decision["basis"] = old.get("basis", "")
    decision["statistics_note"] = "track-record statistics for this combined method have not been recomputed"
    f["decision"] = decision
    f["kpi_model"] = kc
    f["batch_1_vs_batch_2"] = batch12_block(f, kc)
    rr = f.get("material_range_rule") or {}
    if rr.get("phases"):
        f["phases"]["sampling_uncertainty_95"] = {q["phase"]: q["ci95"] for q in rr["phases"]}
    for k in ("fingerprint_model", "texture_model", "decision_v2", "forced_mode",
              # old-method leftovers: the material model's own 3-level tier, its outdated statistics, and the
              # frontend copies (only reference-location facts need those)
              "confidence", "validation_reference", "frontend_compat_note", "loo_prediction"):
        f.pop(k, None)
    for k in ("confidence", "validation_reference"):
        (f.get("material_model") or {}).pop(k, None)
    (f.get("inputs") or {}).pop("detectors_used_by_fingerprint", None)
    ph, check = f["phases"], f.get("known_location_check") or {}
    t, ci = ph["three_class_pct"], ph.get("sampling_uncertainty_95", {})

    def interval(name):
        return f" [{ci[name][0]:.1f} to {ci[name][1]:.1f}]" if name in ci else ""

    best = max((m.get("best_score_sd", 0) for m in check.get("matches", [])), default=None)
    first = f"Answer: {decision['answer']} ({decision['confidence']} confidence)"
    if decision["answer_type"] == "specific":
        first += (f", {final[decision['answer']]:.0%} ({W_KPI:.0%} KPI model + {W_MATERIAL:.0%} v3 material model); "
                  f"the v3 material model alone picks {mat_pick} "
                  f"({'agrees' if decision.get('material_model_agrees') else 'disagrees'}).")
    else:
        first += "."
    sents = [first, f"KPI evidence: {driver}.",
             f"Composition (U-Net segmentation, 95 % sampling interval from GET4): pore {t['pore']:.1f} %{interval('pore')}, "
             f"carbon {t['carbon (graphite + binder)']:.1f} %{interval('carbon')}, SiOx {t['SiOx']:.1f} %{interval('SiOx')}."]
    sents += (f.get("material_model", {}).get("map_text", {}).get("sentences") or [])[:4]
    if check.get("status") == "new" and best is not None:
        sents.append(f"Not a training image and not a known location (best edge-map match {best:.0f} SD; a match needs 15).")
    if rr.get("phases"):
        sents.append("GET4 range check: " + (f"the composition fits only {rr['answer']}" if rr.get("answer")
                                              else "the composition fits the ranges of more than one batch, so it gives no answer") + ".")
    b12 = f["batch_1_vs_batch_2"]
    sents.append("Batch_1 vs Batch_2: they differ subtly. Batch_2 is more porous on average (more open and hidden "
                  "sub-surface pores); Batch_1 has slightly more and larger SiOx particles. Their ranges overlap, so a "
                  "single location between them is the hardest call" + (f"; {b12['this_location']}." if b12.get("this_location") else "."))
    f["summary_sentences"] = sents
    f["field_guide"] = ("Read `decision` first: the answer comes from the KPI model (`kpi_model`, Guanyi's classifier); our "
                        "material model (`material_model`: U-Net segmentation + DINOv2) is a check that raises or lowers "
                        "confidence and supplies the explanation (`material_model.map_text` describes the maps in words). "
                        "`phases` is the composition with GET4 sampling intervals. Only `summary_sentences` is generated text.")
    order = ["summary_sentences", "field_guide", "sample_id", "true_batch", "decision", "phases", "batch_1_vs_batch_2", "kpi_model",
             "known_location_check", "material_range_rule", "material_model"]
    f = {**{k: f[k] for k in order if k in f}, **{k: v for k, v in f.items() if k not in order}}
    (out / "facts.json").write_text(json.dumps(f, indent=1, ensure_ascii=False), encoding="utf-8")
    return f


def convert_existing_runs(force=False):
    """Apply the current method to runs made before it; force=True re-applies it (reusing the saved KPI calls)."""
    done = []
    for folder in sorted(RUNS.iterdir()):
        facts = folder / "output" / "facts.json"
        if not facts.is_file() or (not force and "kpi_model" in json.loads(facts.read_text(encoding="utf-8"))):
            continue
        if folder.name.startswith("unknown_"):
            lid = folder.name.split("_", 1)[1]
            raw = {d: REPO_ROOT / "data" / "raw" / "unknown" / f"img_{lid}_{d}.tif" for d in DETECTORS}
        else:
            raw = {d: folder / "input" / f"img_{folder.name}_{d}.tif" for d in DETECTORS}
        if not raw["BSE"].is_file():
            continue
        current_method(folder, raw["BSE"], raw["Inlens"] if raw["Inlens"].is_file() else None,
                       raw["ETD"] if raw["ETD"].is_file() else None)
        done.append(folder.name)
    return done


# ---------------------------------------------------------------- unknown batch: v3 decision per location

@router.get("/v3/unknown")
def v3_unknown():
    """v3's decision for every analysed unknown location, next to the KPI classifier's call and the session hint."""
    team = {}
    if CLASSIFICATION_PATH.is_file():
        for loc in json.loads(CLASSIFICATION_PATH.read_text(encoding="utf-8")).get("locations", []):
            team[loc["location_id"]] = {"batch": f"Batch_{loc['predicted_batch']}", "confidence": loc.get("confidence"),
                                        "probabilities": loc.get("probabilities"), "session_hint": loc.get("session_hint")}
    out = []
    for facts_path in sorted(RUNS.glob("unknown_*/output/facts.json")):
        facts = json.loads(facts_path.read_text(encoding="utf-8"))
        location = facts_path.parent.parent.name.split("_", 1)[1]
        d = facts["decision"]
        out.append({"location_id": location, "run": facts_path.parent.parent.name, "answer": d["answer"],
                    "answer_type": d["answer_type"], "confidence": d["confidence"],
                    "probabilities": d.get("probabilities") or d.get("average_calibrated_probabilities"),
                    "material_model_pick": d.get("material_model_pick"), "material_model_agrees": d.get("material_model_agrees"),
                    "composition": facts["phases"]["three_class_pct"],
                    "sampling_uncertainty_95": facts["phases"].get("sampling_uncertainty_95"),
                    "summary": facts.get("summary_sentences", [])[:6], "kpi_classifier": team.get(location)})
    return {"locations": out, "track_record": None,
            "note": "track-record statistics on page 1 are outdated (computed for earlier versions of the methods)"}


# ---------------------------------------------------------------- demo: run v3 on one uploaded location

@router.post("/v3/jobs")
def v3_new_job():
    if any(j["status"] == "running" for j in JOBS.values()):
        raise HTTPException(409, "a run is already in progress; wait for it to finish")
    job = "demo_" + time.strftime("%H%M%S") + "_" + uuid.uuid4().hex[:4]
    (RUNS / job / "input").mkdir(parents=True)
    JOBS[job] = {"status": "created", "steps": [], "error": None, "started": None}
    return {"job": job}


@router.put("/v3/jobs/{job}/input/{detector}")
async def v3_upload(job: str, detector: str, request: Request):
    folder = run_dir(job)
    if job not in JOBS or JOBS[job]["status"] != "created" or detector not in DETECTORS:
        raise HTTPException(400, "upload BSE, Inlens or ETD to a new run")
    data = await request.body()
    if data[:4] not in (b"II*\x00", b"MM\x00*"):
        raise HTTPException(400, f"{detector}: the file is not a TIFF image")
    tif = folder / "input" / f"img_{job}_{detector}.tif"
    tif.write_bytes(data)
    preview(tif, folder / "input" / f"{detector}.jpg")
    return {"detector": detector, "bytes": len(data)}


def _run(job):
    try:
        _run_inner(job)
    except Exception as e:  # noqa: BLE001 - shown on the Demo page instead of hanging
        JOBS[job].update(status="error", error=f"{type(e).__name__}: {e}")


def _run_inner(job):
    folder, j = RUNS / job, JOBS[job]
    tif = {d: folder / "input" / f"img_{job}_{d}.tif" for d in DETECTORS}
    cmd = [v3_python(), "-u", "-m", "src.bid_explain", "predict", "--bse", str(tif["BSE"]), "--inlens", str(tif["Inlens"]),
           "--out", str(folder / "output")]
    if tif["ETD"].exists():
        cmd += ["--etd", str(tif["ETD"])]
    with open(folder / "log.txt", "w", encoding="utf-8") as log:
        proc = subprocess.Popen(cmd, cwd=V3_PROJECT_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                encoding="utf-8", errors="replace")
        for line in proc.stdout:
            log.write(line)
            log.flush()
            if line.startswith("STEP "):
                j["steps"].append(line.split()[1])
        proc.wait()
    ok = proc.returncode == 0 and (folder / "output" / "facts.json").exists()
    if not ok:
        j["status"], j["error"] = "error", (folder / "log.txt").read_text(encoding="utf-8")[-1500:]
        return
    j["steps"].append("kpi_s")
    current_method(folder, tif["BSE"], tif["Inlens"], tif["ETD"] if tif["ETD"].exists() else None)
    j["steps"].append("decision_s")
    j["status"] = "done"


@router.post("/v3/jobs/{job}/run")
def v3_run(job: str):
    folder = run_dir(job)
    if job not in JOBS or JOBS[job]["status"] != "created":
        raise HTTPException(400, "this run cannot be started")
    missing = [d for d in ("BSE", "Inlens") if not (folder / "input" / f"img_{job}_{d}.tif").exists()]
    if missing:
        raise HTTPException(400, f"missing images: {', '.join(missing)}")
    JOBS[job].update(status="running", started=time.time())
    threading.Thread(target=_run, args=(job,), daemon=True).start()
    return {"job": job, "status": "running"}


@router.get("/v3/jobs")
def v3_jobs():
    return sorted(p.parent.parent.name for p in RUNS.glob("*/output/facts.json"))


@router.get("/v3/jobs/{job}")
def v3_job(job: str):
    folder = run_dir(job)
    if job in JOBS:
        j = JOBS[job]
        state = {"status": j["status"], "steps": j["steps"], "error": j["error"],
                 "elapsed": round(time.time() - j["started"]) if j["started"] else 0}
    elif (folder / "output" / "facts.json").exists():
        state = {"status": "done", "steps": STEPS, "error": None, "elapsed": None}
    else:
        raise HTTPException(404, "unknown run")
    if state["status"] == "done":
        state["facts"] = json.loads((folder / "output" / "facts.json").read_text(encoding="utf-8"))
        state["inputs"] = [d for d in DETECTORS if (folder / "input" / f"{d}.jpg").exists()]
    return state


@router.get("/v3/runs/{job}/{sub}/{name}")
def v3_run_file(job: str, sub: str, name: str):
    folder = run_dir(job)
    if sub not in ("input", "output") or not re.fullmatch(r"[A-Za-z0-9_.]+\.(jpg|png)", name):
        raise HTTPException(404)
    path = folder / sub / name
    if not path.is_file() and sub == "input" and job.startswith("unknown_"):
        # input previews of the unknown batch are made on first request from data/raw/unknown
        tif = REPO_ROOT / "data" / "raw" / "unknown" / f"img_{job.split('_', 1)[1]}_{name.removesuffix('.jpg')}.tif"
        if tif.is_file():
            path.parent.mkdir(exist_ok=True)
            preview(tif, path)
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path)


# ---------------------------------------------------------------- multi-agent report (Claude Sonnet, text only)

@router.post("/v3/jobs/{job}/report")
def v3_report_start(job: str):
    folder = run_dir(job)
    if not (folder / "output" / "facts.json").exists():
        raise HTTPException(409, "the run has not finished")
    status = folder / "output" / "report_status.json"
    if status.exists() and json.loads(status.read_text(encoding="utf-8")).get("status") == "running":
        return json.loads(status.read_text(encoding="utf-8"))
    status.write_text(json.dumps({"status": "running", "stage": "starting the agents"}), encoding="utf-8")
    subprocess.Popen([v3_python(), "-m", "website.agents", str(folder)], cwd=V3_PROJECT_DIR,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"status": "running", "stage": "starting the agents"}


@router.get("/v3/jobs/{job}/report")
def v3_report(job: str):
    out = run_dir(job) / "output"
    status = out / "report_status.json"
    if status.exists():
        s = json.loads(status.read_text(encoding="utf-8"))
        if s.get("status") == "done" and (out / "report.json").exists():
            return json.loads((out / "report.json").read_text(encoding="utf-8"))
        return s
    if (out / "report.json").exists():
        return json.loads((out / "report.json").read_text(encoding="utf-8"))
    return {"status": "none"}
