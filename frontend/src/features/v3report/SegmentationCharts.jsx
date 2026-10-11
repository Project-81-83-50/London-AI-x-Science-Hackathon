// Four-phase segmentation views shared by the Detailed report: phase legend, per-location composition bars and
// the batch-decision table on held-out locations. Data comes from GET /batches/{id}/v3-report.
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

const humanBatch = (b) => (b ? b.replaceAll("_", " ") : "—");
const share = (v) => (Number.isFinite(v) ? `${Math.round(v * 100)}%` : "—"); // 0-1 as a percentage

// The current decision rule (90 % KPI model + 10 % material model) on this batch's locations, each decided by
// models trained without it (analysis.v3_report: held_out_decisions).
export function DecisionTable({ heldOut, batch }) {
  const rows = heldOut.locations;
  const right = rows.filter((r) => r.correct).length;
  const high = heldOut.by_confidence.High;
  const low = heldOut.by_confidence.Low;
  return (
    <div className="kpi-card">
      <div className="kpi-card-heading">
        <h3>Batch decision (leave-one-location-out)</h3>
        <span className="kpi-card-note">
          Batch {batch}: {right} of {rows.length} right · all batches: {heldOut.overall.right} of {heldOut.overall.n}{" "}
          right, balanced accuracy {share(heldOut.balanced_accuracy)}
        </span>
      </div>
      <p className="kpi-card-note">
        Each location is decided as an uploaded image would be, by models trained without it: 90 % the KPI model, 10 %
        the material model (U-Net segmentation + DINOv2). Confidence is High when the KPI model is at least 50 % sure
        and the material model picks the same batch. Across all 31 locations, High answers were right {high.right} of{" "}
        {high.n} times ({share(high.accuracy)}), Low answers {low.right} of {low.n} ({share(low.accuracy)}).
      </p>
      <div className="kpi-table-scroll">
        <table className="kpi-table">
          <thead>
            <tr>
              <th scope="col">Location</th>
              <th scope="col">Answer</th>
              <th scope="col">Confidence</th>
              <th scope="col">KPI model</th>
              <th scope="col">Material model</th>
              <th scope="col">Result</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.sample_id}>
                <th scope="row">{r.sample_id}</th>
                <td>
                  {humanBatch(r.answer)} <small>{share(r.probability)}</small>
                </td>
                <td>{r.confidence}</td>
                <td>
                  {humanBatch(r.kpi_pick)} <small>{share(r.kpi_top_probability)}</small>
                </td>
                <td>{humanBatch(r.material_pick)}</td>
                <td>
                  <span className={`kpi-chip ${r.correct ? "" : "kpi-chip-variable"}`}>
                    {r.correct ? "✓ right" : "✗ wrong"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
