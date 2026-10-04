import { useState } from "react";
import { useJson } from "../../hooks/useJson";
import { useTooltip } from "../../hooks/useTooltip";
import "../kpi/KpiReport.css";
import "./LucasReport.css";

// Chart colours: an ordinal orange ramp in order of BSE brightness (pore darkest, SiOx lightest),
// validated against the dark surface (darkest step 2.9:1). Bars, tiles and the legend follow this order.
// The lucas-sem-analysis overlay images keep their own colours, stated in their caption.
const PHASES = [
  { key: "pore", label: "Pore", color: "#b0341b" },
  { key: "CBD", label: "Carbon-binder (CBD)", color: "#e04a20" },
  { key: "graphite", label: "Graphite", color: "#fb7350" },
  { key: "SiOx", label: "SiOx", color: "#ffbca6" },
];
const pct = (v, digits = 1) => (Number.isFinite(v) ? `${v.toFixed(digits)}%` : "—");

function PhaseTiles({ stats }) {
  return (
    <div className="kpi-tiles lucas-tiles">
      {PHASES.map((phase) => {
        const s = stats.find((row) => row.class === phase.key);
        if (!s) return null;
        const differs = Number.isFinite(s.kruskal_p) && s.kruskal_p < 0.05;
        return (
          <article className="kpi-tile" key={phase.key}>
            <span className="kpi-tile-label">
              <span className="kpi-swatch" style={{ background: phase.color }} /> {phase.label}
            </span>
            <strong className="kpi-tile-value">{pct(s.mean_pct)}</strong>
            <span className="kpi-tile-meta">
              SD {pct(s.sd_pct)} · range {pct(s.min_pct)}–{pct(s.max_pct)} · n={s.n}
            </span>
            <span className={`kpi-chip ${differs ? "kpi-chip-moderate" : ""}`}>
              {differs ? "differs between batches" : "no clear batch difference"} · p ={" "}
              {s.kruskal_p?.toFixed(3)}
            </span>
          </article>
        );
      })}
    </div>
  );
}

export function PhaseLegend() {
  return (
    <ul className="kpi-legend" aria-label="Phase legend">
      {PHASES.map((p) => (
        <li key={p.key}>
          <span className="kpi-swatch" style={{ background: p.color }} />
          {p.label}
        </li>
      ))}
    </ul>
  );
}

export function CompositionBars({ samples }) {
  const { frame, handlers, layer, width } = useTooltip();
  const labelWidth = 92;
  const valueWidth = 110;
  const bar = 16;
  const pitch = 26;
  const plot = Math.max(120, width - labelWidth - valueWidth);
  return (
    <div className="kpi-chart-frame" ref={frame}>
      <svg
        viewBox={`0 0 ${width} ${samples.length * pitch + 6}`}
        className="kpi-chart"
        role="img"
        aria-label="Four-phase composition of each sample; values are in the table below"
      >
        {samples.map((sample, row) => {
          const y = row * pitch + 4;
          const total = PHASES.reduce((sum, p) => sum + (sample.phases_pct[p.key] ?? 0), 0) || 100;
          let offset = 0;
          const rows = PHASES.map((p) => ({
            color: p.color,
            value: pct(sample.phases_pct[p.key]),
            label: `${p.label} · ${sample.sample_id}`,
          }));
          return (
            <g key={sample.sample_id}>
              <text x="0" y={y + bar - 3} className="kpi-row-label">
                {sample.sample_id}
              </text>
              {PHASES.map((p, i) => {
                const share = (sample.phases_pct[p.key] ?? 0) / total;
                const x = labelWidth + offset * plot;
                offset += share;
                return (
                  <rect
                    key={p.key}
                    x={x}
                    y={y}
                    width={Math.max(0, share * plot - (i < PHASES.length - 1 ? 2 : 0))}
                    height={bar}
                    rx={i === PHASES.length - 1 ? 4 : 0}
                    fill={p.color}
                    className="kpi-hit kpi-segment"
                    {...handlers(rows)}
                  />
                );
              })}
              <text x={width} y={y + bar - 3} className="kpi-row-value" textAnchor="end">
                {pct(sample.phases_pct.pore)} pore
              </text>
            </g>
          );
        })}
      </svg>
      {layer}
    </div>
  );
}

const ANSWER_LABEL = { specific: "", pair: "either", unsure: "unsure" };

function answerText(decision) {
  if (!decision) return "—";
  if (decision.answer_type === "unsure") return "Unsure";
  return decision.answer.replaceAll("_", " ");
}

// v3's batch decision per location: the imaging-fingerprint and material models combined by agreement.
export function DecisionTable({ samples, batch, trackRecord }) {
  const answered = samples.filter((s) => s.decision && s.decision.answer_type !== "unsure");
  const right = answered.filter((s) => s.decision.correct).length;
  const overall = trackRecord?.accuracy_when_answering;
  return (
    <div className="kpi-card">
      <div className="kpi-card-heading">
        <h3>Batch decision (leave-one-location-out)</h3>
        <span className="kpi-card-note">
          Batch {batch}: {answered.length} of {samples.length} locations answered, {right} right
          {trackRecord ? ` · all batches: answers ${trackRecord.coverage}, ${overall?.correct} right when answering` : ""}
        </span>
      </div>
      <p className="kpi-card-note">
        Each location is decided with models trained without it. An imaging-fingerprint model (noise, banding,
        grey levels) and a material model (segmentation + DINOv2) must agree; when they point to Batch 1 and
        Batch 2 differently the answer is “Batch 1 or Batch 2”, otherwise “unsure”. Batches 1 and 2 look alike in
        this data, and the fingerprint reads how an image was taken, so treat answers as leads.
      </p>
      <div className="kpi-table-scroll">
        <table className="kpi-table">
          <thead>
            <tr>
              <th scope="col">Location</th>
              <th scope="col">Session</th>
              <th scope="col">Answer</th>
              <th scope="col">Confidence</th>
              <th scope="col">Imaging / material pick</th>
              <th scope="col">Result</th>
            </tr>
          </thead>
          <tbody>
            {samples.map((s) => {
              const d = s.decision;
              const result = !d ? "—" : d.answer_type === "unsure" ? "abstained" : d.correct ? "✓ right" : "✗ wrong";
              return (
                <tr key={s.sample_id}>
                  <th scope="row">
                    <span>{s.sample_id}</span>
                    {d?.reasons?.length > 0 && <small>{d.reasons.join("; ")}</small>}
                  </th>
                  <td>{s.session}</td>
                  <td>
                    {answerText(d)}
                    {d && ANSWER_LABEL[d.answer_type] === "either" ? " (either)" : ""}
                  </td>
                  <td>{d?.confidence ?? "—"}</td>
                  <td>
                    {d ? `${d.imaging_side_pick?.replace("_", " ") ?? "—"} / ${d.material_side_pick?.replace("_", " ") ?? "—"}` : "—"}
                  </td>
                  <td>
                    <span
                      className={`kpi-chip ${d?.correct === false ? "kpi-chip-variable" : d?.answer_type === "unsure" ? "kpi-chip-moderate" : ""}`}
                    >
                      {result}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function LucasReport({ apiUrl, batch }) {
  const report = useJson(`${apiUrl}/batches/${batch}/lucas-report`);
  const [showOverlays, setShowOverlays] = useState(false);
  if (report.status === "loading")
    return (
      <div className="notice" role="status">
        Loading the further analysis for Batch {batch}…
      </div>
    );
  if (report.status === "error")
    return (
      <div className="notice notice-error" role="alert">
        Could not load the further analysis for Batch {batch} ({report.error}).
      </div>
    );
  const data = report.data;
  const overlays = data.samples.filter((s) => s.overlay).length;
  return (
    <section className="section-block kpi-report" aria-labelledby="lucas-report-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">FURTHER ANALYSIS / LUCAS-SEM-ANALYSIS V3 / BATCH {data.batch_id}</p>
          <h2 id="lucas-report-title">Further analysis: four-phase segmentation and batch decision</h2>
        </div>
        <span className="section-count">
          {data.samples.length} SAMPLES · {overlays} OVERLAYS
        </span>
      </div>

      <div className="kpi-card">
        <p className="kpi-card-note lucas-intro">
          A deeper follow-up to the KPI report. lucas-sem-analysis v3 segments each location&apos;s BSE and
          InLens images into four phases with a machine-learning model (pore, including open grey-floored
          pores; graphite; SiOx; carbon-binder domain, CBD), then decides the batch with two independent
          models. Results are Lucas&apos;s committed v3 outputs for data/raw/batch_{data.batch_id}. Pore,
          carbon and SiOx agree with an independent annotator 87% of the time; the graphite-vs-binder split
          is experimental (binder precision about 50%).
        </p>
      </div>

      <PhaseTiles stats={data.batch_stats} />
      <p className="kpi-axis-note">
        p is a Kruskal-Wallis test across the three reference batches. Imaging sessions differ between
        batches, which can inflate these differences.
      </p>

      <div className="kpi-card">
        <div className="kpi-card-heading">
          <h3>Composition by sample</h3>
          <PhaseLegend />
        </div>
        <CompositionBars samples={data.samples} />
        <details className="kpi-table-toggle">
          <summary>Show composition table</summary>
          <table className="kpi-table">
            <thead>
              <tr>
                <th scope="col">Sample</th>
                {PHASES.map((p) => (
                  <th scope="col" key={p.key}>
                    {p.label}
                  </th>
                ))}
                <th scope="col">Deep / open pore</th>
                <th scope="col">SiOx particles per 1000 µm²</th>
                <th scope="col">SiOx median diameter</th>
              </tr>
            </thead>
            <tbody>
              {data.samples.map((s) => (
                <tr key={s.sample_id}>
                  <th scope="row">{s.sample_id}</th>
                  {PHASES.map((p) => (
                    <td className="kpi-num" key={p.key}>
                      {pct(s.phases_pct[p.key])}
                    </td>
                  ))}
                  <td className="kpi-num">
                    {pct(s.pore_deep_pct)} / {pct(s.pore_open_pct)}
                  </td>
                  <td className="kpi-num">{s.siox_particles.per_1000um2 ?? "—"}</td>
                  <td className="kpi-num">
                    {Number.isFinite(s.siox_particles.median_diameter_um)
                      ? `${s.siox_particles.median_diameter_um.toFixed(2)} µm`
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      </div>

      <DecisionTable samples={data.samples} batch={data.batch_id} trackRecord={data.decision_track_record} />

      <div className="kpi-card">
        <div className="kpi-card-heading">
          <h3>Segmentation overlays</h3>
          {overlays > 0 && (
            <button
              type="button"
              className="toggle-button"
              aria-expanded={showOverlays}
              onClick={() => setShowOverlays((v) => !v)}
            >
              {showOverlays ? "Hide overlays" : `Show overlays (${overlays})`}
            </button>
          )}
        </div>
        <div className="kpi-card-heading">
          <span className="kpi-card-note">
            Overlay colours: blue pore, purple graphite, orange SiOx, green CBD, red excluded
            {data.overlay_source === "teacher_cpu"
              ? " · overlays rebuilt on CPU from the LightGBM teacher (the delivered U-Net needs a GPU)"
              : ""}
          </span>
        </div>
        {overlays === 0 && (
          <div className="notice">
            No overlays yet. Run <code>python run_cpu_pipeline.py</code> in lucas-sem-analysis to
            build them from data/raw.
          </div>
        )}
        {showOverlays && (
        <div className="kpi-locations">
          {data.samples
            .filter((s) => s.overlay)
            .map((s) => {
              const url = `${apiUrl}/batches/${data.batch_id}/lucas-report/overlays/${encodeURIComponent(s.sample_id)}`;
              return (
                <article className="kpi-location" key={s.sample_id}>
                  <a href={url} target="_blank" rel="noreferrer" className="kpi-overlay-link">
                    <img
                      src={url}
                      alt={`Four-phase segmentation overlay for ${s.sample_id}`}
                      loading="lazy"
                      decoding="async"
                    />
                  </a>
                  <div className="kpi-location-body">
                    <div className="kpi-location-heading">
                      <h4>{s.sample_id}</h4>
                      <span className="kpi-chip">session {s.session}</span>
                    </div>
                    <dl className="kpi-location-values">
                      {PHASES.map((p) => (
                        <div key={p.key}>
                          <dt>{p.key}</dt>
                          <dd>{pct(s.phases_pct[p.key])}</dd>
                        </div>
                      ))}
                    </dl>
                    {s.teacher_cpu_phases_pct && (
                      <p className="kpi-location-file">
                        Overlay model (teacher):{" "}
                        {PHASES.map((p) => `${p.key} ${pct(s.teacher_cpu_phases_pct[p.key])}`).join(" · ")}
                      </p>
                    )}
                  </div>
                </article>
              );
            })}
        </div>
        )}
      </div>
    </section>
  );
}

export default LucasReport;
