import { useState } from "react";
import { useJson } from "../../hooks/useJson";
import { useTooltip } from "../../hooks/useTooltip";
import Tabs from "../../components/Tabs";
import { tabPanelProps } from "../../lib/tabPanel";
import { batchLabel } from "../../lib/batchLabel";
import "./KpiReport.css";

// The three classes are intensity classes (pore darkest, bright phase lightest), so the charts use an
// ordinal orange ramp, dark to light, validated against the dark surface for monotone lightness,
// visible steps and a darkest step that still stands out (3.3:1). The overlay images keep their own
// high-visibility tints, which their captions state.
const PHASE_COLORS = {
  pore: "#c0361a",
  graphite: "#f4511e",
  bright: "#ffc4b0",
};
const PHASES = [
  { id: "porosity", key: "pore", label: "Pore" },
  { id: "graphite_fraction", key: "graphite", label: "Graphite" },
  { id: "bright_fraction", key: "bright", label: "Bright phase" },
];
const DIGITS = { "%": 1, pp: 1, "µm": 2, ratio: 2, "per 100 µm²": 1, "µm / µm²": 3 };

function formatValue(value, kpi, withUnit = true) {
  if (!Number.isFinite(value)) return "—";
  const shown = (value * (kpi.display_scale ?? 1)).toFixed(DIGITS[kpi.unit] ?? 2);
  if (!withUnit || kpi.unit === "ratio") return shown;
  return kpi.unit === "%" ? `${shown}%` : `${shown} ${kpi.unit}`;
}

function formatInterval(kpi) {
  return Array.isArray(kpi.ci95)
    ? `${formatValue(kpi.ci95[0], kpi, false)}–${formatValue(kpi.ci95[1], kpi)}`
    : "—";
}

function ReferenceStrip({ kpiId, batchId, summary }) {
  const { frame, handlers, layer } = useTooltip();
  const points = (summary?.batches ?? [])
    .map((batch) => ({
      batch: batch.batch_id,
      kpi: batch.kpis.find((kpi) => kpi.id === kpiId),
    }))
    .filter((point) => Number.isFinite(point.kpi?.mean));
  if (points.length < 2) return null;
  const values = points.map((point) => point.kpi.mean);
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const x = (v) => (hi === lo ? 70 : 10 + ((v - lo) / (hi - lo)) * 120);
  return (
    <div className="kpi-strip-frame" ref={frame}>
      <svg
        className="kpi-reference-strip"
        viewBox="0 0 140 30"
        role="img"
        aria-label={`Reference batch means: ${points
          .map((p) => `batch ${p.batch} ${formatValue(p.kpi.mean, p.kpi)}`)
          .join(", ")}`}
      >
        <line x1="10" x2="130" y1="11" y2="11" className="kpi-axis" />
        {points.map((point) => {
          const current = point.batch === batchId;
          return (
            <g
              key={point.batch}
              className="kpi-hit"
              {...handlers([
                {
                  value: formatValue(point.kpi.mean, point.kpi),
                  label: `Batch ${point.batch} mean`,
                },
              ])}
            >
              <circle cx={x(point.kpi.mean)} cy="11" r="12" fill="transparent" />
              <circle
                cx={x(point.kpi.mean)}
                cy="11"
                r="4.5"
                className={current ? "kpi-dot-current" : "kpi-dot-other"}
              />
              <text x={x(point.kpi.mean)} y="28" className="kpi-strip-label">
                {point.batch}
              </text>
            </g>
          );
        })}
      </svg>
      {layer}
    </div>
  );
}

function HeadlineTiles({ report, summary }) {
  const kpis = Object.fromEntries(
    report.kpi_groups.flatMap((group) => group.kpis).map((kpi) => [kpi.id, kpi]),
  );
  return (
    <div className="kpi-tiles">
      {report.headline.map((id) => {
        const kpi = kpis[id];
        if (!kpi) return null;
        return (
          <article className="kpi-tile" key={id}>
            <span className="kpi-tile-label">{kpi.name}</span>
            <strong className="kpi-tile-value">{formatValue(kpi.mean, kpi)}</strong>
            <span className="kpi-tile-meta">
              95% CI {formatInterval(kpi)} · n={kpi.n}
            </span>
            <span className={`kpi-chip kpi-chip-${kpi.consistency?.replace(/\s/g, "-")}`}>
              {kpi.consistency}
            </span>
            <ReferenceStrip kpiId={id} batchId={report.batch_id} summary={summary} />
          </article>
        );
      })}
    </div>
  );
}

function Legend({ colors }) {
  return (
    <ul className="kpi-legend" aria-label="Phase legend">
      {PHASES.map((phase) => (
        <li key={phase.key}>
          <span className="kpi-swatch" style={{ background: colors[phase.key] }} />
          {phase.label}
        </li>
      ))}
    </ul>
  );
}

function CompositionChart({ locations, colors }) {
  const { frame, handlers, layer, width } = useTooltip();
  const labelWidth = 92;
  const valueWidth = 96;
  const bar = 16;
  const pitch = 26;
  const plot = width - labelWidth - valueWidth;
  const height = locations.length * pitch + 6;
  return (
    <div className="kpi-chart-frame" ref={frame}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="kpi-chart"
        role="img"
        aria-label="Phase composition of each location; values are listed in the table below"
      >
        {locations.map((location, row) => {
          const y = row * pitch + 4;
          let offset = 0;
          return (
            <g key={location.location_id} opacity={location.included ? 1 : 0.35}>
              <text x="0" y={y + bar - 3} className="kpi-row-label">
                {location.location_id}
              </text>
              {PHASES.map((phase, index) => {
                const share = location.kpis[phase.id] ?? 0;
                const x = labelWidth + offset * plot;
                offset += share;
                const w = Math.max(0, share * plot - (index < 2 ? 2 : 0));
                return (
                  <rect
                    key={phase.key}
                    x={x}
                    y={y}
                    width={w}
                    height={bar}
                    rx={index === 2 ? 4 : 0}
                    fill={colors[phase.key]}
                    className="kpi-hit kpi-segment"
                    {...handlers(
                      PHASES.map((p) => ({
                        color: colors[p.key],
                        value: `${((location.kpis[p.id] ?? 0) * 100).toFixed(1)}%`,
                        label: `${p.label} · ${location.location_id}`,
                      })),
                    )}
                  />
                );
              })}
              <text x={width} y={y + bar - 3} className="kpi-row-value" textAnchor="end">
                {location.included
                  ? `${(location.kpis.porosity * 100).toFixed(1)}% pore`
                  : "excluded"}
              </text>
            </g>
          );
        })}
      </svg>
      {layer}
    </div>
  );
}

function DotStrip({ kpi }) {
  const { frame, handlers, layer } = useTooltip();
  const values = kpi.per_location.map((p) => p.value).filter(Number.isFinite);
  if (values.length === 0) return <span className="kpi-muted">—</span>;
  const extent = [...values, ...(kpi.ci95 ?? [])];
  let lo = Math.min(...extent);
  let hi = Math.max(...extent);
  if (hi === lo) {
    lo -= Math.abs(lo) * 0.1 || 1;
    hi += Math.abs(hi) * 0.1 || 1;
  }
  const x = (v) => 8 + ((v - lo) / (hi - lo)) * 164;
  return (
    <div className="kpi-strip-frame" ref={frame}>
      <svg
        viewBox="0 0 180 26"
        className="kpi-dot-strip"
        role="img"
        aria-label={`${kpi.name} by location: ${kpi.per_location
          .map((p) => `${p.location_id} ${formatValue(p.value, kpi)}`)
          .join(", ")}`}
      >
        <line x1="8" x2="172" y1="13" y2="13" className="kpi-axis" />
        {kpi.ci95 && (
          <rect
            x={x(kpi.ci95[0])}
            y="7"
            width={Math.max(1, x(kpi.ci95[1]) - x(kpi.ci95[0]))}
            height="12"
            rx="3"
            className="kpi-ci-band"
          />
        )}
        <line x1={x(kpi.mean)} x2={x(kpi.mean)} y1="4" y2="22" className="kpi-mean-tick" />
        {kpi.per_location.map((point) => (
          <g
            key={point.location_id}
            className="kpi-hit"
            {...handlers([{ value: formatValue(point.value, kpi), label: point.location_id }])}
          >
            <circle cx={x(point.value)} cy="13" r="12" fill="transparent" />
            <circle cx={x(point.value)} cy="13" r="4" className="kpi-dot" />
          </g>
        ))}
      </svg>
      {layer}
    </div>
  );
}

function KpiGroup({ group }) {
  return (
    <section className="kpi-group" aria-labelledby={`kpi-group-${group.id}`}>
      <div className="kpi-group-heading">
        <h4 id={`kpi-group-${group.id}`}>{group.title}</h4>
        <p>{group.description}</p>
      </div>
      <div className="kpi-table-scroll">
        <table className="kpi-table">
          <thead>
            <tr>
              <th scope="col">KPI</th>
              <th scope="col">Mean</th>
              <th scope="col">95% CI</th>
              <th scope="col">SD</th>
              <th scope="col">CV</th>
              <th scope="col">Spread</th>
              <th scope="col">By location (bar = 95% CI, tick = mean)</th>
            </tr>
          </thead>
          <tbody>
            {group.kpis.map((kpi) => (
              <tr key={kpi.id}>
                <th scope="row">
                  <span>{kpi.name}</span>
                  <small>{kpi.definition}</small>
                </th>
                <td className="kpi-num">{formatValue(kpi.mean, kpi)}</td>
                <td className="kpi-num">{formatInterval(kpi)}</td>
                <td className="kpi-num">{formatValue(kpi.sd, kpi, false)}</td>
                <td className="kpi-num">
                  {Number.isFinite(kpi.cv) ? `${(kpi.cv * 100).toFixed(0)}%` : "—"}
                </td>
                <td>
                  <span className={`kpi-chip kpi-chip-${kpi.consistency?.replace(/\s/g, "-")}`}>
                    {kpi.consistency ?? "—"}
                  </span>
                </td>
                <td>
                  <DotStrip kpi={kpi} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Histogram({ distribution, color }) {
  const { frame, handlers, layer, width } = useTooltip(320);
  const height = 160;
  const left = 34;
  const top = 12;
  const bottom = 22;
  const shares = distribution.shares;
  const peak = Math.max(...shares, 0.01);
  const step = (width - left) / shares.length;
  const barWidth = Math.min(24, step - 2);
  const y = (share) => top + (height - bottom - top) * (1 - share / peak);
  const ticks = [0.1, 0.25, 0.5, 1, 2, 5, 10, 20].filter(
    (t) => t >= distribution.edges[0] && t <= distribution.edges.at(-1),
  );
  const logLo = Math.log(distribution.edges[0]);
  const logHi = Math.log(distribution.edges.at(-1));
  const xOf = (v) => left + ((Math.log(v) - logLo) / (logHi - logLo)) * (width - left);
  return (
    <figure className="kpi-figure">
      <figcaption>
        {distribution.label} · {distribution.total.toLocaleString()} regions
      </figcaption>
      <div className="kpi-chart-frame" ref={frame}>
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="kpi-chart"
          role="img"
          aria-label={`${distribution.label} histogram, share of regions per size bin`}
        >
          {[0.5, 1].map((f) => (
            <g key={f}>
              <line x1={left} x2={width} y1={y(peak * f)} y2={y(peak * f)} className="kpi-grid" />
              <text x={left - 5} y={y(peak * f) + 3} className="kpi-tick" textAnchor="end">
                {(peak * f * 100).toFixed(0)}%
              </text>
            </g>
          ))}
          <line x1={left} x2={width} y1={height - bottom} y2={height - bottom} className="kpi-axis" />
          {shares.map((share, i) => {
            const top = y(share);
            const h = height - bottom - top;
            return (
              <g
                key={i}
                className="kpi-hit"
                {...handlers([
                  {
                    value: `${(share * 100).toFixed(1)}% of regions`,
                    label: `${distribution.edges[i].toFixed(2)}–${distribution.edges[i + 1].toFixed(2)} µm`,
                  },
                ])}
              >
                <rect x={left + i * step} y={top} width={step} height={height - bottom - top} fill="transparent" />
                {h > 0 && (
                  <path
                    className="kpi-bar"
                    fill={color}
                    d={`M${left + i * step + (step - barWidth) / 2},${height - bottom}
                        v${-Math.max(h - 4, 0)} q0,-4 4,-4 h${barWidth - 8} q4,0 4,4
                        v${Math.max(h - 4, 0)} z`}
                  />
                )}
              </g>
            );
          })}
          {ticks.map((t) => (
            <text key={t} x={xOf(t)} y={height - 6} className="kpi-tick" textAnchor="middle">
              {t}
            </text>
          ))}
        </svg>
        {layer}
      </div>
      <p className="kpi-axis-note">Equivalent circle diameter (µm, log scale)</p>
    </figure>
  );
}

function ProfileChart({ profile, color, label }) {
  const { frame, handlers, layer, width } = useTooltip(320);
  const height = 190;
  const left = 46;
  const top = 8;
  const bottom = 24;
  const n = profile.mean.length;
  if (!n) return null;
  const hi = Math.max(...profile.max, 0.01) * 1.05;
  const x = (v) => left + (v / hi) * (width - left - 8);
  const y = (i) => top + ((i + 0.5) / n) * (height - top - bottom);
  const line = profile.mean.map((v, i) => `${i ? "L" : "M"}${x(v)},${y(i)}`).join(" ");
  const band =
    profile.max.map((v, i) => `${i ? "L" : "M"}${x(v)},${y(i)}`).join(" ") +
    profile.min
      .map((v, i) => [v, i])
      .reverse()
      .map(([v, i]) => `L${x(v)},${y(i)}`)
      .join(" ") +
    "Z";
  const ticks = [0, hi / 2, hi].map((v) => Math.round(v * 1000) / 1000);
  return (
    <figure className="kpi-figure">
      <figcaption>{label}: mean of locations with min–max range</figcaption>
      <div className="kpi-chart-frame" ref={frame}>
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="kpi-chart"
          role="img"
          aria-label={`${label} from image top to bottom: ${profile.mean
            .map((v) => `${(v * 100).toFixed(1)}%`)
            .join(", ")}`}
        >
          {ticks.map((t) => (
            <g key={t}>
              <line x1={x(t)} x2={x(t)} y1={top} y2={height - bottom} className="kpi-grid" />
              <text x={x(t)} y={height - 8} className="kpi-tick" textAnchor="middle">
                {(t * 100).toFixed(0)}%
              </text>
            </g>
          ))}
          <text x={left - 6} y={top + 8} className="kpi-tick" textAnchor="end">
            top
          </text>
          <text x={left - 6} y={height - bottom} className="kpi-tick" textAnchor="end">
            bottom
          </text>
          <path d={band} fill={color} opacity="0.1" />
          <path d={line} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
          {profile.mean.map((v, i) => (
            <g
              key={i}
              className="kpi-hit"
              {...handlers([
                { value: `${(v * 100).toFixed(1)}%`, label: `Band ${i + 1} of ${n} mean`, color },
                {
                  value: `${(profile.min[i] * 100).toFixed(1)}–${(profile.max[i] * 100).toFixed(1)}%`,
                  label: "Range across locations",
                },
              ])}
            >
              <rect
                x={left}
                y={y(i) - (height - top - bottom) / n / 2}
                width={width - left}
                height={(height - top - bottom) / n}
                fill="transparent"
              />
            </g>
          ))}
        </svg>
        {layer}
      </div>
    </figure>
  );
}

function LocationCard({ location, overlayUrl }) {
  const badge = { clean: "BSE analysed", usable: "Lower confidence", excluded: "No BSE view" }[
    location.confidence
  ];
  return (
    <article className={`kpi-location kpi-location-${location.confidence}`}>
      <a href={overlayUrl} target="_blank" rel="noreferrer" className="kpi-overlay-link">
        <img
          src={overlayUrl}
          alt={`Segmentation overlay for location ${location.location_id}: pores blue, bright phase orange`}
          loading="lazy"
          decoding="async"
        />
      </a>
      <div className="kpi-location-body">
        <div className="kpi-location-heading">
          <h4>Location {location.location_id}</h4>
          <span className={`kpi-chip kpi-chip-${location.confidence}`}>{badge}</span>
        </div>
        <p className="kpi-location-file">
          Analysed <code>{location.location_id}_{location.analysed_detector}</code> ·{" "}
          {location.field_um[0]} × {location.field_um[1]} µm
          {location.location_recovered === false ? " · name assigned" : ""}
        </p>
        <dl className="kpi-location-values">
          <div>
            <dt>Pore</dt>
            <dd>{(location.kpis.porosity * 100).toFixed(1)}%</dd>
          </div>
          <div>
            <dt>Graphite</dt>
            <dd>{(location.kpis.graphite_fraction * 100).toFixed(1)}%</dd>
          </div>
          <div>
            <dt>Bright</dt>
            <dd>{(location.kpis.bright_fraction * 100).toFixed(1)}%</dd>
          </div>
        </dl>
        {location.flags.length > 0 && (
          <ul className="kpi-flags">
            {location.flags.map((flag) => (
              <li key={flag}>{flag}</li>
            ))}
          </ul>
        )}
        <details className="kpi-views">
          <summary>Detectors ({location.views.length} views)</summary>
          <ul>
            {location.views.map((view) => (
              <li key={view.filename}>
                <span>
                  {location.location_id}_{view.detector}
                  {view.analysed ? " · analysed" : ""}
                </span>
                <span>{view.detector_confidence} confidence</span>
              </li>
            ))}
          </ul>
        </details>
      </div>
    </article>
  );
}

function KpiReport({ apiUrl, batch }) {
  const report = useJson(`${apiUrl}/batches/${batch}/kpi-report`);
  const summary = useJson(`${apiUrl}/kpi-reports/summary`);
  const [groupId, setGroupId] = useState(null);
  const [showOverlays, setShowOverlays] = useState(false);

  if (report.status === "loading")
    return (
      <div className="notice" role="status">
        Loading {batchLabel(batch)} KPI report…
      </div>
    );
  if (report.status === "error")
    return (
      <div className="notice notice-error" role="alert">
        Could not load the {batchLabel(batch)} KPI report ({report.error}).
      </div>
    );

  const data = report.data;
  const colors = PHASE_COLORS;
  const activeGroup = data.kpi_groups.find((g) => g.id === groupId) ?? data.kpi_groups[0];
  const inv = data.inventory;
  return (
    <section className="section-block kpi-report" aria-labelledby="kpi-report-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">MICROSTRUCTURE KPIS / {batchLabel(data.batch_id).toUpperCase()}</p>
          <h2 id="kpi-report-title">{batchLabel(data.batch_id)} analysis report</h2>
        </div>
        <span className="section-count">
          {inv.locations_analysed} OF {inv.locations} LOCATIONS ANALYSED ·{" "}
          {(inv.field_area_um2 / 1e6).toFixed(3)} MM² IMAGED
        </span>
      </div>

      <div className="kpi-card">
        <h3>Key findings</h3>
        <ul className="kpi-findings">
          {data.findings.map((finding) => (
            <li key={finding}>{finding}</li>
          ))}
        </ul>
      </div>

      <HeadlineTiles report={data} summary={summary.data} />
      {summary.status === "ready" && (
        <p className="kpi-axis-note">
          The dot strip under each tile places this batch&apos;s mean (filled) among the
          reference batches&apos; means (numbered).
        </p>
      )}

      <div className="kpi-card">
        <div className="kpi-card-heading">
          <h3>Phase composition by location</h3>
          <Legend colors={colors} />
        </div>
        <CompositionChart locations={data.locations} colors={colors} />
        <details className="kpi-table-toggle">
          <summary>Show composition table</summary>
          <table className="kpi-table">
            <thead>
              <tr>
                <th scope="col">Location</th>
                <th scope="col">Pore</th>
                <th scope="col">Graphite</th>
                <th scope="col">Bright phase</th>
                <th scope="col">Status</th>
              </tr>
            </thead>
            <tbody>
              {data.locations.map((location) => (
                <tr key={location.location_id}>
                  <th scope="row">{location.location_id}</th>
                  {PHASES.map((phase) => (
                    <td key={phase.key} className="kpi-num">
                      {(location.kpis[phase.id] * 100).toFixed(1)}%
                    </td>
                  ))}
                  <td>{location.confidence}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      </div>

      <div className="kpi-card">
        <h3>KPI breakdown</h3>
        <p className="kpi-card-note">{data.method.statistics} {data.method.consistency_bands}</p>
        <Tabs
          tabs={data.kpi_groups.map((g) => ({ id: g.id, label: g.title, badge: g.kpis.length }))}
          active={activeGroup.id}
          onChange={setGroupId}
          label="KPI groups"
          idPrefix="kpi-group"
          size="sm"
        />
        <div {...tabPanelProps("kpi-group", activeGroup.id)}>
          <KpiGroup group={activeGroup} />
        </div>
      </div>

      <div className="kpi-figures">
        <div className="kpi-card">
          <h3>Size distributions</h3>
          <Histogram distribution={data.distributions.bright_ecd} color={colors.bright} />
          <Histogram distribution={data.distributions.pore_ecd} color={colors.pore} />
        </div>
        <div className="kpi-card">
          <h3>Vertical profiles</h3>
          <ProfileChart profile={data.profiles.porosity} color={colors.pore} label="Porosity" />
          <ProfileChart
            profile={data.profiles.bright_fraction}
            color={colors.bright}
            label="Bright-phase fraction"
          />
        </div>
      </div>

      <div className="kpi-card">
        <div className="kpi-card-heading">
          <h3>Locations and segmentation overlays</h3>
          <button
            type="button"
            className="toggle-button"
            aria-expanded={showOverlays}
            onClick={() => setShowOverlays((v) => !v)}
          >
            {showOverlays ? "Hide overlays" : `Show overlays (${data.locations.length})`}
          </button>
        </div>
        {showOverlays && (
          <p className="kpi-card-note">Pores tinted blue, bright phase orange, graphite left grey.</p>
        )}
        {showOverlays && (
        <div className="kpi-locations">
          {data.locations.map((location) => (
            <LocationCard
              key={location.location_id}
              location={location}
              overlayUrl={`${apiUrl}/batches/${data.batch_id}/kpi-report/overlays/${encodeURIComponent(location.location_id)}`}
            />
          ))}
        </div>
        )}
      </div>

      <details className="kpi-card kpi-method">
        <summary>Method and caveats</summary>
        <dl>
          <dt>View selection</dt>
          <dd>{data.method.view_selection}</dd>
          <dt>Segmentation</dt>
          <dd>{data.method.segmentation}</dd>
          <dt>Analysis pixel size</dt>
          <dd>{data.method.analysis_pixel_um * 1000} nm</dd>
          <dt>Generated</dt>
          <dd>{new Date(data.generated).toLocaleString()}</dd>
        </dl>
        <ul>
          {data.caveats.map((caveat) => (
            <li key={caveat}>{caveat}</li>
          ))}
        </ul>
      </details>
    </section>
  );
}

export default KpiReport;
