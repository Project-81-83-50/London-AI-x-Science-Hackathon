// Detailed report: every location, metric and test for one batch, from the SEM pipeline (v3). The same view
// serves the reference batches and the unknown batch (whose locations are compared with the references).
import { useJson } from "../../hooks/useJson";
import { useTooltip } from "../../hooks/useTooltip";
import { V3_BATCHES, differenceKind, formatNumber, formatP, reportSubject, unitLabel } from "../../lib/v3format";
import { CompositionBars, DecisionTable, PhaseLegend } from "./SegmentationCharts";
import "../../styles/report.css";
import "./V3Report.css";

const GROUPS = [
  { id: "composition", label: "Composition (three phases)" },
  { id: "four_phase", label: "Four phases and pore types" },
  { id: "siox", label: "SiOx particles" },
];
const KIND_CHIP = { robust: "", session: "kpi-chip-moderate", none: "kpi-chip-includes-zero" };
const KIND_TEXT = { robust: "holds within sessions", session: "may be session", none: "—" };
const keyName = (b) => (b === "unknown" ? "Unknown" : b.replace("_", " "));

function LocationTable({ data, subject }) {
  const { locations } = data.detailed;
  const m = Object.fromEntries(data.metrics.map((d) => [d.id, d]));
  const se = (v) => (Number.isFinite(v) ? ` ± ${v.toFixed(1)}` : "");
  const cols = [
    "graphite_pct",
    "CBD_pct",
    "pore_deep_pct",
    "pore_open_pct",
    "siox_per_1000um2",
    "siox_area_d50_um",
    "siox_clark_evans",
  ];
  const footer = subject.unknown ? [...V3_BATCHES, "unknown"] : V3_BATCHES;
  return (
    <div className="kpi-table-scroll">
      <table className="kpi-table v3-table">
        <thead>
          <tr>
            <th scope="col">Location</th>
            <th scope="col">Session</th>
            <th scope="col">Pore</th>
            <th scope="col">Carbon</th>
            <th scope="col">SiOx</th>
            {cols.map((c) => (
              <th scope="col" key={c}>
                {m[c].name}
                {unitLabel(m[c].unit) && <small className="v3-unit">{unitLabel(m[c].unit)}</small>}
              </th>
            ))}
            <th scope="col">Stability (max SD)</th>
            <th scope="col">{subject.unknown ? "Segmented by" : "v3 decision"}</th>
          </tr>
        </thead>
        <tbody>
          {locations.map((l) => {
            const sd = Math.max(...Object.values(l.stability_sd_pp ?? {}).filter(Number.isFinite));
            return (
              <tr key={l.sample_id}>
                <th scope="row">{l.sample_id}</th>
                <td>{l.session}</td>
                <td className="kpi-num">
                  {formatNumber(l.metrics.pore_pct, "%")}
                  {se(l.standard_error_pp?.pore)}
                </td>
                <td className="kpi-num">
                  {formatNumber(l.metrics.carbon_pct, "%")}
                  {se(l.standard_error_pp?.carbon)}
                </td>
                <td className="kpi-num">
                  {formatNumber(l.metrics.SiOx_pct, "%")}
                  {se(l.standard_error_pp?.SiOx)}
                </td>
                {cols.map((c) => (
                  <td className="kpi-num" key={c}>
                    {formatNumber(l.metrics[c], m[c].unit)}
                  </td>
                ))}
                <td className="kpi-num">{Number.isFinite(sd) ? `${sd.toFixed(2)} pp` : "—"}</td>
                <td>
                  {subject.unknown ? (
                    <>
                      {l.model_label}
                      <small className="v3-unit">{l.segmented_from?.join(" + ")}</small>
                    </>
                  ) : l.decision ? (
                    l.decision.answer_type === "unsure" ? (
                      "unsure"
                    ) : (
                      `${l.decision.answer.replaceAll("_", " ")} (${l.decision.confidence})`
                    )
                  ) : (
                    "—"
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
        <tfoot>
          {footer.map((b) => (
            <tr key={b} className={b === subject.key ? "v3-row-own" : ""}>
              <th scope="row" colSpan={2}>
                {keyName(b)} mean
              </th>
              {["pore_pct", "carbon_pct", "SiOx_pct", ...cols].map((c) => (
                <td className="kpi-num" key={c}>
                  {formatNumber(data.detailed.reference_means[c]?.[b], m[c].unit)}
                </td>
              ))}
              <td colSpan={2} />
            </tr>
          ))}
        </tfoot>
      </table>
    </div>
  );
}

function StatisticsTable({ data, subject }) {
  const comparison = data.general.comparison;
  const keys = subject.unknown ? [...V3_BATCHES, "unknown"] : V3_BATCHES;
  return (
    <div className="kpi-table-scroll">
      <table className="kpi-table v3-table">
        <thead>
          <tr>
            <th scope="col">Metric</th>
            {keys.map((b) => (
              <th scope="col" key={b}>
                {keyName(b)} mean ± SD
              </th>
            ))}
            <th scope="col">Kruskal-Wallis p (q)</th>
            <th scope="col">Within-session p</th>
            <th scope="col">Pairwise Holm p (1v2 · 1v3 · 2v3)</th>
            <th scope="col">
              {subject.unknown ? "Closest batch (z vs 1 / 2 / 3)" : `Cliff's δ, ${subject.name} vs rest`}
            </th>
            <th scope="col">Reading</th>
          </tr>
        </thead>
        {GROUPS.map((group) => (
          <tbody key={group.id}>
            <tr className="v3-group-row">
              <th scope="rowgroup" colSpan={keys.length + 6}>
                {group.label}
              </th>
            </tr>
            {data.metrics
              .filter((d) => d.group === group.id)
              .map((d) => {
                const s = comparison[d.id];
                const kind = differenceKind(s);
                return (
                  <tr key={d.id}>
                    <th scope="row">
                      <span>{d.name}</span>
                      <small>
                        {d.description}
                        {unitLabel(d.unit) ? ` · ${unitLabel(d.unit)}` : ""}
                      </small>
                    </th>
                    {keys.map((b) => (
                      <td className={`kpi-num ${b === subject.key ? "v3-cell-own" : ""}`} key={b}>
                        {s.batch[b]
                          ? `${formatNumber(s.batch[b].mean, d.unit)}${s.batch[b].n > 1 ? ` ± ${formatNumber(s.batch[b].sd, d.unit)}` : ""}`
                          : "—"}
                      </td>
                    ))}
                    <td className="kpi-num">
                      {formatP(s.kruskal_p)} ({formatP(s.kruskal_q)})
                    </td>
                    <td className="kpi-num">{formatP(s.session_stratified_p)}</td>
                    <td className="kpi-num">
                      {["1v2", "1v3", "2v3"].map((k) => formatP(s.pairwise_holm_p[k])).join(" · ")}
                    </td>
                    <td className="kpi-num">
                      {subject.unknown
                        ? s.unknown_z
                          ? `${s.unknown_closest.slice(-1)} (${V3_BATCHES.map((b) => s.unknown_z[b].toFixed(1)).join(" / ")})`
                          : "—"
                        : s.cliffs_delta_vs_rest[subject.key].toFixed(2)}
                    </td>
                    <td>
                      <span className={`kpi-chip ${KIND_CHIP[kind]}`}>{KIND_TEXT[kind]}</span>
                    </td>
                  </tr>
                );
              })}
          </tbody>
        ))}
      </table>
    </div>
  );
}

// Share of SiOx area per size bin (log-spaced diameters): this batch emphasised, the others as recessive lines.
function SioxSizeChart({ data, subject }) {
  const { frame, handlers, layer, width } = useTooltip(720);
  const { edges_um: edges, batches } = data.detailed.siox_size_histogram;
  const left = 44;
  const height = 210;
  const plotW = Math.max(160, width - left - 16);
  const plotH = height - 42;
  const others = subject.others.filter((b) => batches[b]);
  const series = [...others, subject.key];
  const top = Math.ceil(Math.max(...series.flatMap((b) => batches[b].area_share)) * 10) / 10 || 0.1;
  const n = edges.length - 1;
  const x = (i) => left + ((i + 0.5) / n) * plotW;
  const y = (v) => 12 + plotH - (v / top) * plotH;
  const dash = ["", "v3-line-dashed", "v3-line-dotted"];
  const keyDash = ["", "v3-key-dashed", "v3-key-dotted"];
  return (
    <div className="kpi-chart-frame" ref={frame}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="kpi-chart"
        role="img"
        aria-label={`Share of SiOx area by particle diameter, ${subject.name} against the other batches`}
      >
        {[0, top / 2, top].map((t) => (
          <g key={t}>
            <line x1={left} x2={left + plotW} y1={y(t)} y2={y(t)} className="v3-grid" />
            <text x={left - 6} y={y(t) + 4} textAnchor="end" className="kpi-row-label">
              {Math.round(t * 100)}%
            </text>
          </g>
        ))}
        {edges.map((e, i) =>
          i % 2 === 0 ? (
            <text key={e} x={left + (i / n) * plotW} y={height - 10} textAnchor="middle" className="kpi-row-label">
              {e < 1 ? e.toFixed(1) : e.toFixed(0)}
            </text>
          ) : null,
        )}
        {series.map((b) => (
          <polyline
            key={b}
            className={b === subject.key ? "v3-line-own" : `v3-line-other ${dash[others.indexOf(b)]}`}
            points={batches[b].area_share.map((v, i) => `${x(i)},${y(v)}`).join(" ")}
          />
        ))}
        {batches[subject.key].area_share.map((v, i) => (
          <g
            key={i}
            className="kpi-hit"
            {...handlers(
              series.map((b) => ({
                value: `${(batches[b].area_share[i] * 100).toFixed(1)}%`,
                label: `${keyName(b)} · ${edges[i]}–${edges[i + 1]} µm`,
              })),
            )}
          >
            <rect x={x(i) - plotW / n / 2} y="12" width={plotW / n} height={plotH} fill="transparent" />
            <circle cx={x(i)} cy={y(v)} r="4" className="v3-dot-own" />
          </g>
        ))}
      </svg>
      {layer}
      <p className="v3-legend">
        <span>
          <i className="v3-key v3-key-own" /> {subject.name} ({batches[subject.key].n_particles} particles)
        </span>
        {others.map((b, i) => (
          <span key={b}>
            <i className={`v3-key-line ${keyDash[i]}`} /> {keyName(b)} ({batches[b].n_particles})
          </span>
        ))}
        <span>x-axis: particle diameter, µm (log scale)</span>
      </p>
    </div>
  );
}

function ImageKpiTable({ data, subject }) {
  const values = Object.values(data.detailed.image_kpi_values);
  return (
    <details className="kpi-table-toggle">
      <summary>Show the {data.detailed.image_kpis.length} supplementary image KPIs</summary>
      <p className="kpi-card-note">{data.detailed.image_kpi_note}</p>
      <div className="kpi-table-scroll">
        <table className="kpi-table v3-table">
          <thead>
            <tr>
              <th scope="col">Image KPI</th>
              {V3_BATCHES.map((b) => (
                <th scope="col" key={b}>
                  {keyName(b)} mean
                </th>
              ))}
              <th scope="col">{subject.name} locations (range)</th>
              <th scope="col">Kruskal-Wallis p (q)</th>
              <th scope="col">Within-session p</th>
              <th scope="col">Session flag</th>
            </tr>
          </thead>
          <tbody>
            {data.detailed.image_kpis.map((k) => {
              const v = values.map((row) => row[k.id]).filter(Number.isFinite);
              return (
                <tr key={k.id}>
                  <th scope="row">
                    <span>{k.name}</span>
                    {k.unit && <small>{k.unit}</small>}
                  </th>
                  {V3_BATCHES.map((b) => (
                    <td className={`kpi-num ${b === subject.key ? "v3-cell-own" : ""}`} key={b}>
                      {Number.isFinite(k.batch_mean[b]) ? k.batch_mean[b].toPrecision(3) : "—"}
                    </td>
                  ))}
                  <td className="kpi-num">
                    {v.length ? `${Math.min(...v).toPrecision(3)} – ${Math.max(...v).toPrecision(3)}` : "—"}
                  </td>
                  <td className="kpi-num">
                    {formatP(k.kruskal_p)} ({formatP(k.kruskal_q)})
                  </td>
                  <td className="kpi-num">{formatP(k.session_stratified_p)}</td>
                  <td>{k.flag ? <span className="kpi-chip kpi-chip-moderate">{k.flag}</span> : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </details>
  );
}

function Overlays({ apiUrl, locations }) {
  return (
    <div className="kpi-locations">
      {locations.map((l) => (
        <article className="kpi-location" key={l.sample_id}>
          <a href={`${apiUrl}${l.overlay}`} target="_blank" rel="noreferrer" className="kpi-overlay-link">
            <img
              src={`${apiUrl}${l.overlay}`}
              alt={`v3 four-phase segmentation of ${l.sample_id}`}
              loading="lazy"
              decoding="async"
            />
          </a>
          <div className="kpi-location-body">
            <div className="kpi-location-heading">
              <h4>{l.sample_id}</h4>
              <span className="kpi-chip">session {l.session}</span>
            </div>
            <p className="kpi-location-file">
              {l.model_label} · {l.segmented_from?.join(" + ")}
            </p>
          </div>
        </article>
      ))}
    </div>
  );
}

function DetailedReport({ apiUrl, batch }) {
  const report = useJson(`${apiUrl}/batches/${batch}/v3-report`);
  const unknownBatch = batch === "unknown";
  const segmentation = useJson(unknownBatch ? null : `${apiUrl}/batches/${batch}/segmentation-report`);
  if (report.status === "loading")
    return (
      <div className="notice" role="status">
        Loading the detailed report…
      </div>
    );
  if (report.status === "error")
    return (
      <div className="notice notice-error" role="alert">
        Could not load the detailed report ({report.error}).
      </div>
    );
  const data = report.data;
  const subject = reportSubject(data);
  const q = data.general.quality;
  const locations = data.detailed.locations;
  const samples = locations.map((l) => ({
    sample_id: l.sample_id,
    phases_pct: {
      pore: l.metrics.pore_pct,
      graphite: l.metrics.graphite_pct,
      SiOx: l.metrics.SiOx_pct,
      CBD: l.metrics.CBD_pct,
    },
  }));
  const overlays = locations.filter((l) => l.overlay);
  const maxStability = q.stability_sd_pp ? Math.max(...Object.values(q.stability_sd_pp).map((s) => s.max)) : null;
  return (
    <section className="section-block kpi-report" aria-labelledby="v3-detailed-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">DETAILED REPORT / SEM PIPELINE V3 / {subject.name.toUpperCase()}</p>
          <h2 id="v3-detailed-title">{subject.name}: every location and test</h2>
        </div>
        <span className="section-count">
          {locations.length} LOCATION{locations.length === 1 ? "" : "S"}
        </span>
      </div>

      <div className="kpi-card">
        <div className="kpi-card-heading">
          <h3>Locations</h3>
          <span className="kpi-card-note">
            {subject.unknown
              ? "reference means below are from the same model as the unknown locations"
              : "± is v3's standard error in percentage points · stability is the largest SD of a phase fraction when the segmentation is re-run on shifted inputs"}
          </span>
        </div>
        <LocationTable data={data} subject={subject} />
      </div>

      <div className="kpi-card">
        <div className="kpi-card-heading">
          <h3>Four-phase composition by location</h3>
          <PhaseLegend />
        </div>
        <p className="kpi-card-note">
          Binder (CBD) precision is about {q.per_phase_precision.CBD}, so read it as an indication.
        </p>
        <CompositionBars samples={samples} />
      </div>

      <div className="kpi-card">
        <div className="kpi-card-heading">
          <h3>Batch comparison, every segmentation metric</h3>
          <span className="kpi-card-note">
            {subject.unknown
              ? "p-values test the reference batches; z is the distance of the unknown mean to each batch mean in pooled SDs"
              : "within-session p shuffles batch labels only inside imaging sessions; q is Benjamini-Hochberg across these metrics"}
          </span>
        </div>
        <StatisticsTable data={data} subject={subject} />
      </div>

      <div className="kpi-card">
        <div className="kpi-card-heading">
          <h3>SiOx particle sizes</h3>
          <span className="kpi-card-note">share of SiOx area in each diameter bin</span>
        </div>
        <SioxSizeChart data={data} subject={subject} />
      </div>

      {overlays.length > 0 && (
        <div className="kpi-card">
          <div className="kpi-card-heading">
            <h3>Segmentation overlays</h3>
            <span className="kpi-card-note">
              v3 colours: blue pore, purple graphite, orange SiOx, green binder, red excluded
            </span>
          </div>
          <Overlays apiUrl={apiUrl} locations={overlays} />
        </div>
      )}

      {!unknownBatch && segmentation.status === "ready" && (
        <DecisionTable
          samples={segmentation.data.samples}
          batch={segmentation.data.batch_id}
          trackRecord={segmentation.data.decision_track_record}
        />
      )}

      {data.detailed.image_kpis.length > 0 && (
        <div className="kpi-card">
          <h3>Supplementary: image KPIs</h3>
          <ImageKpiTable data={data} subject={subject} />
        </div>
      )}

      <div className="kpi-card">
        <h3>Segmentation quality</h3>
        <p className="kpi-card-note">
          {q.note} Agreement: three phases {Math.round(q.annotator_agreement_3_phase * 100)}%, four phases{" "}
          {Math.round(q.annotator_agreement_4_phase * 100)}% (95% CI{" "}
          {q.annotator_agreement_4_phase_ci95.map((v) => `${Math.round(v * 100)}%`).join("–")}). Precision per phase:{" "}
          {Object.entries(q.per_phase_precision)
            .map(([k, v]) => `${k} ${v}`)
            .join(", ")}
          .
          {maxStability !== null &&
            ` Re-running on shifted inputs moves a phase fraction by at most ${maxStability.toFixed(2)} percentage points.`}
        </p>
        {Object.entries(q.single_detector_validation ?? {}).map(([det, v]) => (
          <p className="kpi-card-note" key={det}>
            One-detector model ({det === "SE2" ? "ETD / SE" : det}): {Math.round(v.pixel_agreement_with_teacher * 100)}%
            pixel agreement with the two-detector teacher on held-out reference locations{" "}
            {v.held_out_locations.join(", ")}; mean phase-fraction difference{" "}
            {Object.entries(v.fraction_difference_pp)
              .map(([c, dd]) => `${c} ${dd.mean >= 0 ? "+" : ""}${dd.mean} pp (max ${dd.max_abs})`)
              .join(", ")}
            .
          </p>
        ))}
      </div>
    </section>
  );
}

export default DetailedReport;
