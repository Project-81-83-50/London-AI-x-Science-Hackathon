// General report: one batch at a glance, from the SEM pipeline (v3) four-phase segmentation. The same view
// serves the reference batches and the unknown batch (whose locations are compared with the references).
import { useJson } from "../../hooks/useJson";
import { useTooltip } from "../../hooks/useTooltip";
import { DIFFERENCE_LABEL, differenceKind, formatP, formatValue, reportSubject } from "../../lib/v3format";
import "../../styles/report.css";
import "./V3Report.css";

const HEADLINE = ["pore_pct", "carbon_pct", "SiOx_pct"];
const COMPARED = [
  "pore_pct",
  "carbon_pct",
  "SiOx_pct",
  "pore_open_pct",
  "siox_per_1000um2",
  "siox_area_d50_um",
  "siox_clark_evans",
];
const CHIP = { robust: "", session: "kpi-chip-moderate", none: "kpi-chip-includes-zero" };

function CompositionTiles({ data, subject }) {
  const { general, metrics } = data;
  return (
    <div className="kpi-tiles v3-tiles">
      {HEADLINE.map((id) => {
        const def = metrics.find((m) => m.id === id);
        const stat = general.comparison[id];
        const own = stat.batch[subject.key];
        const kind = differenceKind(stat);
        return (
          <article className="kpi-tile" key={id}>
            <span className="kpi-tile-label">{def.name}</span>
            <strong className="kpi-tile-value">{formatValue(own?.mean, def.unit)}</strong>
            <span className="kpi-tile-meta">
              {own?.n > 1 ? `SD ${formatValue(own.sd, def.unit)}` : "1 location"} ·{" "}
              {subject.unknown ? "batches" : "other batches"}{" "}
              {subject.others.map((b) => `${b.slice(-1)}: ${formatValue(stat.batch[b].mean, def.unit)}`).join(", ")}
            </span>
            {subject.unknown ? (
              <span className="kpi-chip">closest to batch {stat.unknown_closest?.slice(-1) ?? "—"}</span>
            ) : (
              <span className={`kpi-chip ${CHIP[kind]}`}>{DIFFERENCE_LABEL[kind]}</span>
            )}
          </article>
        );
      })}
    </div>
  );
}

// Per metric, every batch mean on a shared row scale (min..max of all locations); the report's own batch is
// the emphasised mark with its location range, the others recede and carry their batch number.
function ComparisonChart({ data, subject }) {
  const { frame, handlers, layer, width } = useTooltip(720);
  const label = Math.min(230, width * 0.36);
  const plot = Math.max(120, width - label - 16);
  const pitch = 40;
  return (
    <div className="kpi-chart-frame" ref={frame}>
      <svg
        viewBox={`0 0 ${width} ${COMPARED.length * pitch + 8}`}
        className="kpi-chart"
        role="img"
        aria-label={`${subject.name} against the ${subject.unknown ? "reference" : "other"} batches on ${COMPARED.length} segmentation metrics; values in the detailed report`}
      >
        {COMPARED.map((id, row) => {
          const def = data.metrics.find((m) => m.id === id);
          const stat = data.general.comparison[id];
          const keys = [...subject.others, subject.key].filter((b) => stat.batch[b]);
          const lo = Math.min(...keys.map((b) => stat.batch[b].min));
          const hi = Math.max(...keys.map((b) => stat.batch[b].max));
          const x = (v) => label + ((v - lo) / (hi - lo || 1)) * plot;
          const y = row * pitch + 22;
          const kind = differenceKind(stat);
          return (
            <g key={id}>
              <text x="0" y={y + 4} className="kpi-row-label">
                {def.name}
              </text>
              <line x1={label} x2={label + plot} y1={y} y2={y} className="v3-track" />
              {keys.map((b, i) => {
                const s = stat.batch[b];
                const mine = b === subject.key;
                const crowded =
                  !mine &&
                  i > 0 &&
                  keys.slice(0, i).some((p) => p !== subject.key && Math.abs(x(s.mean) - x(stat.batch[p].mean)) < 14);
                return (
                  <g
                    key={b}
                    className="kpi-hit"
                    {...handlers([
                      {
                        value: formatValue(s.mean, def.unit),
                        label: `${b === "unknown" ? "Unknown" : b.replace("_", " ")} mean`,
                      },
                      {
                        value: `${formatValue(s.min, def.unit)} – ${formatValue(s.max, def.unit)}`,
                        label: `range, ${s.n} location${s.n === 1 ? "" : "s"}`,
                      },
                      { value: formatP(stat.kruskal_p), label: "reference batches differ: p" },
                      { value: formatP(stat.session_stratified_p), label: "within-session p" },
                    ])}
                  >
                    <rect x={x(s.mean) - 10} y={y - 14} width="20" height="28" fill="transparent" />
                    {mine && s.n > 1 && <line x1={x(s.min)} x2={x(s.max)} y1={y} y2={y} className="v3-range" />}
                    <circle cx={x(s.mean)} cy={y} r={mine ? 6 : 4.5} className={mine ? "v3-dot-own" : "v3-dot-other"} />
                    <text
                      x={x(s.mean)}
                      y={mine || crowded ? y + 19 : y - 9}
                      textAnchor="middle"
                      className="v3-dot-label"
                    >
                      {b === "unknown" ? "U" : b.slice(-1)}
                    </text>
                  </g>
                );
              })}
              {kind !== "none" && (
                <text x={label + plot} y={y + 16} textAnchor="end" className="v3-row-flag">
                  {kind === "robust" ? "batches differ, also within sessions" : "batches differ (session?)"}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      {layer}
      <p className="v3-legend">
        <span>
          <i className="v3-key v3-key-own" /> {subject.name} mean{subject.unknown ? " (U)" : ""}, with its location
          range
        </span>
        <span>
          <i className="v3-key v3-key-other" /> {subject.unknown ? "reference" : "other"} batches&apos; means (numbered)
        </span>
        <span>each row has its own scale, from the lowest to the highest location</span>
      </p>
    </div>
  );
}

function GeneralReport({ apiUrl, batch }) {
  const report = useJson(`${apiUrl}/batches/${batch}/v3-report`);
  if (report.status === "loading")
    return (
      <div className="notice" role="status">
        Loading the general report…
      </div>
    );
  if (report.status === "error")
    return (
      <div className="notice notice-error" role="alert">
        Could not load the general report ({report.error}).
      </div>
    );
  const data = report.data;
  const subject = reportSubject(data);
  const g = data.general;
  const q = g.quality;
  const d = g.decision_summary;
  const k = g.image_kpi_summary;
  return (
    <section className="section-block kpi-report" aria-labelledby="v3-general-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">GENERAL REPORT / SEM PIPELINE V3 / {subject.name.toUpperCase()}</p>
          <h2 id="v3-general-title">{subject.name} at a glance</h2>
        </div>
        <span className="section-count">
          {g.n_locations} LOCATION{g.n_locations === 1 ? "" : "S"} · {g.sessions.length} IMAGING SESSION
          {g.sessions.length === 1 ? "" : "S"}
        </span>
      </div>

      <p className="kpi-card-note v3-intro">
        {subject.unknown
          ? `Each unknown location is segmented by the SEM pipeline (v3) into pore, graphite, SiOx and binder, and compared with ${g.reference_basis}. Composition is shown as three phases (binder merged into carbon). This describes the material; the batch calls are in the Classification tab.`
          : `Built on the SEM pipeline (v3): a machine-learning segmentation of each location's BSE and InLens images into pore, graphite, SiOx and binder. Composition is shown as three phases (binder merged into carbon) because that split agrees with an independent annotator ${Math.round(q.annotator_agreement_3_phase * 100)}% of the time. The Detailed report has every location and statistic.`}
      </p>

      <CompositionTiles data={data} subject={subject} />

      <div className="kpi-card">
        <div className="kpi-card-heading">
          <h3>How {subject.name} compares</h3>
          <span className="kpi-card-note">hover a mark for its values and tests</span>
        </div>
        <ComparisonChart data={data} subject={subject} />
      </div>

      <div className="kpi-card">
        <h3>Key findings</h3>
        {g.findings.length === 0 ? (
          <p className="kpi-card-note">No segmentation metric differs between the reference batches (all p ≥ 0.05).</p>
        ) : (
          <ul className="v3-findings">
            {g.findings.map((f) => (
              <li key={f.metric}>
                <span className={`kpi-chip ${f.robust ? "" : "kpi-chip-moderate"}`}>
                  {f.robust ? "holds within sessions" : "may be session"}
                </span>
                {f.text}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="kpi-tiles v3-tiles">
        <article className="kpi-tile">
          <span className="kpi-tile-label">Segmentation accuracy (v3)</span>
          <strong className="kpi-tile-value">{Math.round(q.annotator_agreement_3_phase * 100)}%</strong>
          <span className="kpi-tile-meta">
            3 phases · 4 phases {Math.round(q.annotator_agreement_4_phase * 100)}% · binder precision{" "}
            {q.per_phase_precision.CBD}
            {q.models_used ? ` · here: ${q.models_used.join(", ")}` : ""}
          </span>
        </article>
        {d && (
          <article className="kpi-tile">
            <span className="kpi-tile-label">v3 batch decision on this batch</span>
            <strong className="kpi-tile-value">
              {d.right}/{d.answered}
            </strong>
            <span className="kpi-tile-meta">
              right of {d.answered} answered ({d.locations} locations) · all batches {d.all_batches?.correct} right,
              answers {d.coverage_all_batches}
            </span>
          </article>
        )}
        {k && (
          <article className="kpi-tile">
            <span className="kpi-tile-label">Image KPIs (supplementary)</span>
            <strong className="kpi-tile-value">
              {k.surviving_fdr}/{k.n}
            </strong>
            <span className="kpi-tile-meta">
              survive multiple-testing correction · {k.nominal_p_below_0_05} nominal p &lt; 0.05 · {k.session_robust}{" "}
              hold within sessions
            </span>
          </article>
        )}
        {Object.entries(q.single_detector_validation ?? {}).map(([det, v]) => (
          <article className="kpi-tile" key={det}>
            <span className="kpi-tile-label">One-detector model ({det === "SE2" ? "ETD / SE" : det})</span>
            <strong className="kpi-tile-value">{Math.round(v.pixel_agreement_with_teacher * 100)}%</strong>
            <span className="kpi-tile-meta">
              pixel agreement with the two-detector teacher on {v.held_out_locations.length} held-out reference
              locations · pore {v.fraction_difference_pp.pore.mean >= 0 ? "+" : ""}
              {v.fraction_difference_pp.pore.mean} pp on average
            </span>
          </article>
        ))}
      </div>

      {g.skipped?.length > 0 && (
        <div className="kpi-card">
          <h3>Not segmented</h3>
          <ul className="v3-caveats">
            {g.skipped.map((s) => (
              <li key={s.location_id}>
                {s.location_id}: {s.reason} ({s.views.join(", ")}).
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="kpi-card">
        <h3>Read with care</h3>
        <ul className="v3-caveats">
          {g.caveats.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
      </div>
    </section>
  );
}

export default GeneralReport;
