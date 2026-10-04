// Demo: upload the BSE + Inlens (+ ETD) images of one location, run v3 (trained on batches 1-3), show batch + confidence.
import { useEffect, useRef, useState } from "react";
import { ProbBars, STEPS, Tier, apiJson, nice, pct } from "./common";

const DETECTORS = [
  { id: "BSE", required: true },
  { id: "Inlens", required: true },
  { id: "ETD", required: false },
];

export default function DemoPage({ apiUrl }) {
  const [files, setFiles] = useState({});
  const [job, setJob] = useState(null);
  const [state, setState] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const timer = useRef(null);
  useEffect(() => () => clearInterval(timer.current), []);

  async function run() {
    setError("");
    setState(null);
    if (!files.BSE || !files.Inlens) { setError("Choose at least the BSE and the Inlens image."); return; }
    setBusy(true);
    try {
      const { job: id } = await apiJson(`${apiUrl}/v3/jobs`, { method: "POST" });
      for (const d of DETECTORS) {
        if (!files[d.id]) continue;
        setState({ status: "uploading", steps: [], note: `Uploading ${d.id}…` });
        await apiJson(`${apiUrl}/v3/jobs/${id}/input/${d.id}`, { method: "PUT", body: files[d.id] });
      }
      await apiJson(`${apiUrl}/v3/jobs/${id}/run`, { method: "POST" });
      setJob(id);
      timer.current = setInterval(async () => {
        try {
          const s = await apiJson(`${apiUrl}/v3/jobs/${id}`);
          setState(s);
          if (s.status !== "running") { clearInterval(timer.current); setBusy(false); }
        } catch (e) { clearInterval(timer.current); setBusy(false); setError(e.message); }
      }, 1000);
    } catch (e) {
      setBusy(false);
      setError(e.message);
    }
  }

  const d = state?.facts?.decision;
  const probs = d?.probabilities || d?.average_calibrated_probabilities;
  const top = probs ? Math.max(...Object.values(probs)) : null;
  return (
    <div className="content-wrap">
      <section className="page-heading">
        <div>
          <p className="eyebrow">DEMO · LUCAS-SEM-ANALYSIS V3</p>
          <h1>Which batch is this location from?</h1>
          <p className="page-subtitle">
            Upload the images of one location — the same spot imaged with different detectors. BSE and Inlens are required;
            ETD/SE is optional and sharpens the imaging fingerprint. The models are trained on batches 1–3 only.
          </p>
        </div>
      </section>
      <div className="v3-card">
        <div className="v3-grid3">
          {DETECTORS.map((det) => (
            <label key={det.id} className={`v3-drop ${files[det.id] ? "v3-has" : ""}`}>
              <b>{det.id}</b> {!det.required && <span className="v3-muted">(optional)</span>}
              <br />
              <input type="file" accept=".tif,.tiff" onChange={(e) => setFiles((f) => ({ ...f, [det.id]: e.target.files[0] }))} />
              <div className="v3-small v3-muted">{files[det.id]?.name}</div>
            </label>
          ))}
        </div>
        <p>
          <button className="v3-button" onClick={run} disabled={busy}>Identify the batch</button>{" "}
          <span className="v3-small v3-muted">about 30–40 s on the GPU</span>
        </p>
        {error && <p className="v3-error">{error}</p>}
        {state && (
          <>
            <div className="v3-flow">
              {STEPS.filter((s) => s.key).map((s, i) => {
                const done = state.steps?.includes(s.key);
                const active = !done && state.status === "running" && (i === 0 || state.steps?.includes(STEPS[i - 1].key));
                return (
                  <span key={s.id} style={{ display: "contents" }}>
                    {i > 0 && <span className="v3-arrow">→</span>}
                    <span className={`v3-step ${done ? "v3-done" : active ? "v3-active" : ""}`}>{s.name}</span>
                  </span>
                );
              })}
            </div>
            <p className="v3-small v3-muted">{state.note || (state.elapsed != null ? `${state.elapsed} s` : "")}</p>
          </>
        )}
        {state?.status === "error" && <pre className="v3-error">{state.error}</pre>}
      </div>
      {d && (
        <a className="v3-card v3-result" href={`#pipeline/${job}`} style={{ display: "block", textDecoration: "none", color: "inherit" }}>
          <div className={`v3-big ${d.answer_type === "unsure" ? "v3-unsure" : ""}`}>{nice(d.answer)}</div>
          <Tier value={d.confidence} /> {top != null && <b> {pct(top)} probability</b>}
          {probs && <ProbBars probabilities={probs} highlight={d.answer} />}
          <p className="v3-small">{(d.reasons || []).join(" ")}</p>
          <span className="v3-button v3-ghost">See every step in the pipeline →</span>
        </a>
      )}
    </div>
  );
}
