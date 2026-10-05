// Four-phase segmentation views shared by the Detailed report: phase legend, per-location composition bars and
// v3's batch-decision table. Data comes from GET /batches/{id}/segmentation-report.
import { useTooltip } from "../../hooks/useTooltip";

// Chart colours: an ordinal orange ramp in order of BSE brightness (pore darkest, SiOx lightest),
// validated against the dark surface (darkest step 2.9:1). Bars and the legend follow this order.
// The SEM pipeline's overlay images keep their own colours, stated in their caption.
const PHASES = [
  { key: "pore", label: "Pore", color: "#b0341b" },
  { key: "CBD", label: "Carbon-binder (CBD)", color: "#e04a20" },
  { key: "graphite", label: "Graphite", color: "#fb7350" },
  { key: "SiOx", label: "SiOx", color: "#ffbca6" },
];
const pct = (v, digits = 1) => (Number.isFinite(v) ? `${v.toFixed(digits)}%` : "—");

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
          {trackRecord
            ? ` · all batches: answers ${trackRecord.coverage}, ${overall?.correct} right when answering`
            : ""}
        </span>
      </div>
      <p className="kpi-card-note">
        Each location is decided with models trained without it. An imaging-fingerprint model (noise, banding, grey
        levels) and a material model (segmentation + DINOv2) must agree; when they point to Batch 1 and Batch 2
        differently the answer is “Batch 1 or Batch 2”, otherwise “unsure”. Batches 1 and 2 look alike in this data, and
        the fingerprint reads how an image was taken, so treat answers as leads.
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
                    {d
                      ? `${d.imaging_side_pick?.replace("_", " ") ?? "—"} / ${d.material_side_pick?.replace("_", " ") ?? "—"}`
                      : "—"}
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
