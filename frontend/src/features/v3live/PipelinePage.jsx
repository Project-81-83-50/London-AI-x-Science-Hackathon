// Pipeline: every step's output for one v3 run, a clickable step diagram, and the multi-agent report.
import { useCallback, useEffect, useRef, useState } from "react";
import { apiJson } from "../../lib/api";
import { V3_BATCHES, humanize, percent } from "../../lib/v3format";
import { PIPELINE_STEPS } from "./pipelineSteps";
import { CompositionBar, Markdown, ProbBars, Table, Tier } from "./V3Widgets";

function Section({ id, title, children }) {
  return (
    <section className="v3-card" id={`v3-step-${id}`}>
      <h3>{title}</h3>
      {children}
    </section>
  );
}

function Report({ apiUrl, run, onDone }) {
  const [r, setR] = useState(null);
  const [error, setError] = useState("");
  const timer = useRef(null);
  useEffect(() => {
    apiJson(`${apiUrl}/v3/jobs/${run}/report`)
      .then((x) => {
        setR(x);
        if (x.status === "done") onDone();
      })
      .catch(() => setR({ status: "none" }));
    return () => clearInterval(timer.current);
  }, [apiUrl, run, onDone]);
  async function start() {
    setError("");
    try {
      setR(await apiJson(`${apiUrl}/v3/jobs/${run}/report`, { method: "POST" }));
      clearInterval(timer.current);
      timer.current = setInterval(async () => {
        const x = await apiJson(`${apiUrl}/v3/jobs/${run}/report`);
        setR(x);
        if (x.status !== "running") {
          clearInterval(timer.current);
          if (x.status === "done") onDone();
        }
      }, 1500);
    } catch (e) {
      setError(e.message);
    }
  }
  if (!r) return null;
  return (
    <>
      {r.status === "none" && (
        <p>
          <span className="v3-small v3-muted">
            Three Claude Sonnet agents (evidence analyst → materials expert with the team knowledge base → skeptic and
            writer) read only the text facts file — no images — and may quote only numbers that are in it.{" "}
          </span>
          <button className="v3-button" onClick={start}>
            Generate report
          </button>
        </p>
      )}
      {r.status === "running" && <span className="v3-step v3-active">{r.stage}</span>}
      {r.status === "error" && (
        <>
          <p className="v3-error">{r.error}</p>
          <button className="v3-button" onClick={start}>
            Try again
          </button>
        </>
      )}
      {r.status === "done" && (
        <>
          <Markdown text={r.markdown} />
          {r.check && (
            <p className={`v3-small ${r.check.length ? "v3-warn" : "v3-good"}`}>
              Number check:{" "}
              {r.check.length
                ? `numbers not found in facts.json: ${r.check.join(", ")}`
                : "every number in the report appears in facts.json ✓"}
            </p>
          )}
          {r.notes && (
            <details className="v3-details">
              <summary>Agent notes (analyst and materials expert)</summary>
              <h4>Evidence analyst</h4>
              <Markdown text={r.notes.analyst} />
              <h4>Materials expert</h4>
              <Markdown text={r.notes.expert} />
            </details>
          )}
          <p>
            <button className="v3-button v3-ghost" onClick={start}>
              Regenerate
            </button>{" "}
            <a
              className="v3-small"
              download={`report_${run}.md`}
              href={`data:text/markdown;charset=utf-8,${encodeURIComponent(r.markdown)}`}
            >
              Download (.md)
            </a>
          </p>
        </>
      )}
      {error && <p className="v3-error">{error}</p>}
    </>
  );
}

export default function PipelinePage({ apiUrl, run: requested }) {
  const [runs, setRuns] = useState([]);
  // Polled run state and report status, each tagged with its run so switching runs shows nothing stale.
  const [runState, setRunState] = useState(null);
  const [error, setError] = useState("");
  const [reportDoneRun, setReportDoneRun] = useState(null);
  const [zoom, setZoom] = useState(null);
  const timer = useRef(null);
  const run = requested || runs[runs.length - 1];
  const state = runState?.run === run ? runState.data : null;
  const reportDone = reportDoneRun === run;
  const markReportDone = useCallback(() => setReportDoneRun(run), [run]);

  useEffect(() => {
    apiJson(`${apiUrl}/v3/jobs`)
      .then(setRuns)
      .catch((e) => setError(e.message));
  }, [apiUrl, requested]);
  useEffect(() => {
    if (!run) return undefined;
    const load = () =>
      apiJson(`${apiUrl}/v3/jobs/${run}`)
        .then((s) => {
          setRunState({ run, data: s });
          if (s.status !== "running") clearInterval(timer.current);
        })
        .catch((e) => {
          setError(e.message);
          clearInterval(timer.current);
        });
    load();
    timer.current = setInterval(load, 1000);
    return () => clearInterval(timer.current);
  }, [apiUrl, run]);

  const f = state?.facts;
  const img = (sub, name) => `${apiUrl}/v3/runs/${run}/${sub}/${name}`;
  const Img = ({ src, alt }) => <img className="v3-img" src={src} alt={alt} onClick={() => setZoom(src)} />;
  return (
    <div className="content-wrap">
      <section className="page-heading">
        <div>
          <p className="eyebrow">PIPELINE · SEM PIPELINE V3</p>
          <h1>From images to a batch call, step by step</h1>
        </div>
      </section>
      <div className="v3-card">
        <label className="v3-small v3-muted">
          Run:{" "}
          <select
            value={run || ""}
            onChange={(e) => {
              window.location.hash = `pipeline/${e.target.value}`;
            }}
          >
            {[...new Set([...(run ? [run] : []), ...runs])].map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </label>
        <div className="v3-flow" style={{ marginTop: 10 }}>
          {PIPELINE_STEPS.map((s, i) => {
            const done = s.key ? state?.steps?.includes(s.key) : reportDone;
            const active =
              !done &&
              state?.status === "running" &&
              s.key &&
              (i === 0 || state.steps.includes(PIPELINE_STEPS[i - 1].key));
            return (
              <span key={s.id} style={{ display: "contents" }}>
                {i > 0 && <span className="v3-arrow">→</span>}
                <span
                  className={`v3-step ${done ? "v3-done" : active ? "v3-active" : ""}`}
                  onClick={() => document.getElementById(`v3-step-${s.id}`)?.scrollIntoView({ behavior: "smooth" })}
                >
                  {i + 1}. {s.name}
                </span>
              </span>
            );
          })}
        </div>
        {state?.status === "running" && <p className="v3-small v3-muted">Running… {state.elapsed} s</p>}
        {!run && <p className="v3-muted">No runs yet. Upload a location on the Demo page.</p>}
      </div>
      {error && <p className="v3-error">{error}</p>}
      {state?.status === "error" && <pre className="v3-error">{state.error}</pre>}
      {f && <Panels f={f} state={state} img={img} Img={Img} />}
      {f && (
        <Section id="rep" title="9 · Agent report (Claude Sonnet: analyst → materials expert → skeptic/writer)">
          <Report apiUrl={apiUrl} run={run} onDone={markReportDone} />
        </Section>
      )}
      {zoom && (
        <div className="v3-zoom" onClick={() => setZoom(null)}>
          <img src={zoom} alt="enlarged" />
        </div>
      )}
    </div>
  );
}

function Panels({ f, state, img, Img }) {
  const d = f.decision,
    m = f.material_model,
    rr = f.material_range_rule || {},
    kc = f.known_location_check || {};
  const ph = f.phases,
    mt = m.map_text || {},
    three = ph.three_class_pct,
    ci = ph.sampling_uncertainty_95 || {};
  const k = f.kpi_model;
  const probs = d.probabilities || d.average_calibrated_probabilities;
  const iv = (key) => (ci[key] ? `${ci[key][0].toFixed(1)} – ${ci[key][1].toFixed(1)}` : "–");
  const fmt = (v, unit, scale) =>
    unit === "%" ? `${(v * (scale || 1)).toFixed(1)}%` : `${(v * (scale || 1)).toFixed(2)} ${unit}`;
  return (
    <>
      <Section id="dec" title="Result">
        <div className={`v3-big ${d.answer_type === "unsure" ? "v3-unsure" : ""}`}>{humanize(d.answer)}</div>
        <Tier value={d.confidence} /> <span className="v3-small v3-muted">{d.method}</span>
        {probs && <ProbBars probabilities={probs} highlight={d.answer} />}
        {d.weights && (
          <div className="v3-grid3" style={{ marginTop: 6 }}>
            <div>
              <b className="v3-small">KPI model · weight {percent(d.weights.kpi_model)}</b>
              <ProbBars probabilities={d.kpi_probabilities} />
            </div>
            <div>
              <b className="v3-small">
                v3 material model (U-Net + DINOv2) · weight {percent(d.weights.v3_material_model)}
              </b>
              <ProbBars probabilities={d.material_model_calibrated} />
            </div>
            <div className="v3-small v3-muted" style={{ alignSelf: "center" }}>
              Final = {percent(d.weights.kpi_model)} KPI model + {percent(d.weights.v3_material_model)} v3 material
              model. No imaging fingerprint is used.
            </div>
          </div>
        )}
        {d.material_model_pick && (
          <p className={`v3-small ${d.material_model_agrees ? "" : "v3-warn"}`}>
            Material model check (U-Net segmentation + DINOv2): <b>{humanize(d.material_model_pick)}</b> —{" "}
            {d.material_model_agrees ? "agrees with the KPI call." : "disagrees, so the confidence is Low."}
          </p>
        )}
        <ul className="v3-small">
          {(d.reasons || []).map((x) => (
            <li key={x}>{x}</li>
          ))}
        </ul>
        <p className="v3-small v3-muted">{d.statistics_note}</p>
      </Section>
      <Section id="inputs" title="1 · Inputs and quality check">
        <div className="v3-thumbs">
          {(state.inputs || []).map((x) => (
            <figure key={x}>
              <Img src={img("input", `${x}.jpg`)} alt={x} />
              <figcaption>{x}</figcaption>
            </figure>
          ))}
        </div>
        <p className="v3-small">
          Excluded area {f.qc.excluded_pct}% · Cu foil: {String(f.qc.cu_foil_detected)} · novelty flags:{" "}
          {(f.novelty.unusual_features_abs_robust_z_ge_3 || []).join(", ") || "none"}
        </p>
      </Section>
      <Section id="seg" title="2 · U-Net segmentation (BSE + Inlens, 50 nm/px)">
        <Img src={img("output", "overlay.jpg")} alt="segmentation overlay" />
        <p className="v3-small v3-muted">blue pore · purple graphite · orange SiOx · green binder · red excluded</p>
        <CompositionBar pore={three.pore} carbon={three["carbon (graphite + binder)"]} siox={three.SiOx} />
        <Table
          head={["phase", "%", "95% sampling interval (GET4)"]}
          rows={[
            ["pore", three.pore, iv("pore")],
            ["carbon (graphite + binder)", three["carbon (graphite + binder)"], iv("carbon")],
            ["SiOx", three.SiOx, iv("SiOx")],
          ]}
        />
        <p className="v3-small">
          4 classes: pore {ph.four_class_pct.pore}% · graphite {ph.four_class_pct.graphite}% · SiOx{" "}
          {ph.four_class_pct.SiOx}% · binder {ph.four_class_pct.CBD}% (binder is experimental). {ph.reliability}
        </p>
        {mt.spatial?.grid_3x3_pct && (
          <details className="v3-details">
            <summary>Composition on a 3 × 3 grid</summary>
            <Table
              head={["region", "pore", "graphite", "SiOx", "binder"]}
              rows={Object.entries(mt.spatial.grid_3x3_pct).map(([key, v]) => [key, v.pore, v.graphite, v.SiOx, v.CBD])}
            />
          </details>
        )}
      </Section>
      <Section id="feat" title="3 · Material features from the segmentation">
        <Table
          head={["feature", "value", "robust z"]}
          rows={Object.entries(m.features_S).map(([key, v]) => [key, v.value, v.robust_z])}
        />
      </Section>
      <Section id="dino" title="4 · DINOv2 texture evidence (material)">
        <Img src={img("output", "evidence.jpg")} alt="evidence map" />
        <p className="v3-small v3-muted">red = pushed toward {humanize(m.predicted_batch)}, blue = against</p>
        <ul className="v3-small">
          {(mt.sentences || []).map((x) => (
            <li key={x}>{x}</li>
          ))}
        </ul>
      </Section>
      <Section
        id="mat"
        title="5 · v3 material model (segmentation features + DINOv2): 10% of the decision, and the check"
      >
        <Table
          head={["head", ...V3_BATCHES.map(humanize)]}
          rows={Object.entries(m.probabilities).map(([key, p]) => [key, ...V3_BATCHES.map((b) => percent(p[b], 1))])}
        />
      </Section>
      <Section id="known" title="6 · Training-image guard and known-spot matcher">
        <p>
          <b>{kc.status}</b> · {kc.note}
        </p>
        {kc.matches && (
          <Table
            head={["view", "best match (SD)", "location", "next location (SD)"]}
            rows={kc.matches.map((x) => [
              x.view,
              x.best_score_sd,
              `${x.location} (${humanize(x.batch)})`,
              x.next_best_other_score_sd,
            ])}
          />
        )}
        <p className="v3-small v3-muted">A known spot needs ≥ 15 SD and 2 × the next location.</p>
      </Section>
      <Section id="get4" title="7 · GET4 sampling intervals and range rule">
        {rr.phases && (
          <Table
            head={["phase", "%", "95% interval", "fits the range of"]}
            rows={rr.phases.map((q) => [
              q.phase,
              q.pct,
              q.ci95.join(" – "),
              q.fits_ranges_of.map(humanize).join(", ") || "none",
            ])}
          />
        )}
        <p className="v3-small">
          Range-rule answer: <b>{rr.answer ? humanize(rr.answer) : "none (fits more than one batch)"}</b>
        </p>
      </Section>
      {k && (
        <Section id="kpi" title="8 · KPI model: 90% of the decision">
          <ProbBars probabilities={k.probabilities} highlight={k.predicted_batch} />
          <Table
            head={["KPI", "this location", ...V3_BATCHES.map(humanize), "support"]}
            rows={k.drivers.map((x) => [
              x.name,
              fmt(x.value, x.unit, x.scale),
              ...V3_BATCHES.map((b) => fmt(x.batch_means[b], x.unit, x.scale)),
              x.support_for_answer,
            ])}
          />
          <p className="v3-small v3-muted">{k.method}</p>
          {k.nearest_reference_locations && (
            <p className="v3-small">
              Nearest reference locations:{" "}
              {k.nearest_reference_locations
                .map((r) => `${r.location_id} (${humanize(r.batch)}, distance ${r.distance})`)
                .join(" · ")}
            </p>
          )}
          {k.reference_validation?.loo_balanced_accuracy != null && (
            <p className="v3-small">
              KPI model's own held-out test: {percent(k.reference_validation.loo_balanced_accuracy)} balanced accuracy
              on the 31 reference locations (chance 33%, permutation p ={" "}
              {Number(k.reference_validation.permutation_p).toFixed(3)}).
            </p>
          )}
          {k.measurement && (
            <p className="v3-small v3-muted">
              Measured at {Math.round(k.measurement.analysis_pixel_nm)} nm/px · {k.measurement.segmentation} ·
              segmentation {k.measurement.segmentation_confidence} · compared with{" "}
              {(k.measurement.views_compared || []).join(", ") || "no other view"}.
            </p>
          )}
          {k.all_kpis && (
            <details className="v3-details">
              <summary>All {k.all_kpis.length} KPIs, most batch-separating first</summary>
              <Table
                head={["#", "KPI", "this location", ...V3_BATCHES.map(humanize), "closest", "meaning"]}
                rows={k.all_kpis.map((r) => [
                  r.separation_rank,
                  r.used_by_model ? <b key="name">{r.name}</b> : r.name,
                  r.value ?? "–",
                  ...V3_BATCHES.map((b) => r.batch_means[b] ?? "–"),
                  humanize(r.closest_batch_mean),
                  r.description,
                ])}
              />
            </details>
          )}
          {k.session_hint && (
            <p className="v3-small v3-muted">
              Session hint (context only, not used by any model): imaged at {k.session_hint.image_height_px} px height,
              like {(k.session_hint.reference_locations_same_height || []).join(", ") || "no reference location"}.
            </p>
          )}
        </Section>
      )}
      <Section id="tim" title="Timings">
        <p className="v3-small">
          {Object.entries(f.timings_s || {})
            .filter(([key]) => !/fingerprint|texture/.test(key))
            .map(([key, v]) => `${key.replace(/_s$/, "")} ${v} s`)
            .join(" · ")}
        </p>
      </Section>
    </>
  );
}
