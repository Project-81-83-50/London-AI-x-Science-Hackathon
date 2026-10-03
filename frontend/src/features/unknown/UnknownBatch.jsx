import { useState } from "react";
import { useJson } from "../../hooks/useJson";
import { useTooltip } from "../../hooks/useTooltip";
import Tabs from "../../components/Tabs";
import { tabPanelProps } from "../../lib/tabPanel";
import "../kpi/KpiReport.css";
import "./UnknownBatch.css";

const BATCHES = ["1", "2", "3"];
const DIGITS = { "%": 1, pp: 1, "µm": 2, ratio: 2, "per 100 µm²": 1, "µm / µm²": 3 };

function formatKpi(value, driver) {
  if (!Number.isFinite(value)) return "—";
  const shown = (value * (driver.scale ?? 1)).toFixed(DIGITS[driver.unit] ?? 2);
  if (driver.unit === "ratio") return shown;
  return driver.unit === "%" ? `${shown}%` : `${shown} ${driver.unit}`;
}

// One bar per reference batch; the predicted batch is the emphasised mark, the others recede.
function ProbabilityBars({ probabilities, predicted }) {
  const { frame, handlers, layer, width } = useTooltip(300);
  const label = 64;
  const value = 44;
  const plot = Math.max(80, width - label - value);
  return (
    <div className="kpi-chart-frame" ref={frame}>
      <svg
        viewBox={`0 0 ${width} 84`}
        className="kpi-chart"
        role="img"
        aria-label={`Probability by reference batch: ${BATCHES.map((b) => `batch ${b} ${Math.round(probabilities[b] * 100)}%`).join(", ")}`}
      >
        {BATCHES.map((b, i) => {
          const p = probabilities[b] ?? 0;
          const y = i * 28 + 4;
          const w = Math.max(p * plot, p > 0 ? 2 : 0);
          return (
            <g key={b} className="kpi-hit" {...handlers([{ value: `${(p * 100).toFixed(1)}%`, label: `Batch ${b}` }])}>
              <rect x="0" y={y - 4} width={width} height="28" fill="transparent" />
              <text x="0" y={y + 13} className="kpi-row-label">
                Batch {b}
              </text>
              <rect x={label} y={y} width={plot} height="18" rx="4" className="unknown-track" />
              {w > 0 && (
                <rect
                  x={label}
                  y={y}
                  width={w}
                  height="18"
                  rx="4"
                  className={b === predicted ? "unknown-bar-predicted" : "unknown-bar-other"}
                />
              )}
              <text x={width} y={y + 13} className="kpi-row-value" textAnchor="end">
                {Math.round(p * 100)}%
              </text>
            </g>
          );
        })}
      </svg>
      {layer}
    </div>
  );
}

function LocationResult({ result, images, apiUrl }) {
  const predicted = result.predicted_batch;
  const session = result.session_hint;
  return (
    <article className="kpi-card unknown-location">
      <div className="unknown-location-head">
        <div>
          <p className="eyebrow">UNKNOWN LOCATION</p>
          <h3>{result.location_id}</h3>
        </div>
        <div className="unknown-verdict">
          <span className="unknown-verdict-label">Classified as</span>
          <strong>Batch {predicted}</strong>
          <span className={`kpi-chip kpi-chip-${result.confidence === "low" ? "variable" : result.confidence === "medium" ? "moderate" : "consistent"}`}>
            {result.confidence} confidence
          </span>
        </div>
      </div>

      <div className="unknown-images">
        {images.map((image) => {
          const url = `${apiUrl}/batches/unknown/images/${encodeURIComponent(image.filename)}`;
          return (
            <figure key={image.filename}>
              <a href={url} target="_blank" rel="noreferrer">
                <img src={url} alt={`${image.display_name ?? image.filename} view`} loading="lazy" decoding="async" />
              </a>
              <figcaption>{image.display_name ?? image.filename}</figcaption>
            </figure>
          );
        })}
        <figure>
          <a href={`${apiUrl}/batches/unknown/kpi-report/overlays/${encodeURIComponent(result.location_id)}`} target="_blank" rel="noreferrer">
            <img
              src={`${apiUrl}/batches/unknown/kpi-report/overlays/${encodeURIComponent(result.location_id)}`}
              alt={`BSE segmentation of ${result.location_id}: pores blue, bright phase orange`}
              loading="lazy"
              decoding="async"
            />
          </a>
          <figcaption>BSE segmentation (pore blue, bright orange)</figcaption>
        </figure>
      </div>

      <div className="unknown-evidence">
        <section>
          <h4>Probability by reference batch</h4>
          <ProbabilityBars probabilities={result.probabilities} predicted={predicted} />
        </section>

        <section>
          <h4>Strongest evidence</h4>
          <table className="kpi-table unknown-drivers">
            <thead>
              <tr>
                <th scope="col">Feature</th>
                <th scope="col">This location</th>
                <th scope="col">Batch 1 / 2 / 3 mean</th>
                <th scope="col">Points to</th>
              </tr>
            </thead>
            <tbody>
              {result.drivers.map((d) => (
                <tr key={d.feature}>
                  <th scope="row">{d.name}</th>
                  <td className="kpi-num">{formatKpi(d.value, d)}</td>
                  <td className="kpi-num">
                    {BATCHES.map((b) => formatKpi(d.batch_means[b], d)).join(" / ")}
                  </td>
                  <td>
                    {d.support >= 0
                      ? `Batch ${predicted}`
                      : `Batch ${result.runner_up}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="kpi-card-note">
            Most similar reference locations:{" "}
            {result.nearest_reference_locations
              .map((n) => `${n.location_id} (batch ${n.batch})`)
              .join(", ")}
            .
          </p>
        </section>
      </div>

      <div className="unknown-notes">
        <p>
          <strong>Duplicate check:</strong>{" "}
          {result.duplicate_check.exact_copies.length
            ? `exact copy of ${result.duplicate_check.exact_copies.join(", ")}`
            : result.duplicate_check.same_field_as_reference
              ? `same field as ${result.duplicate_check.best_same_field_reference}`
              : "not a copy of, or the same field as, any reference image (new material)."}
        </p>
        <p>
          <strong>Session hint (not used by the model):</strong>{" "}
          {session.batches.length
            ? `imaged at ${session.image_height_px} px height, like ${session.reference_locations_same_height.join(", ")}. ${
                session.agrees_with_prediction
                  ? "That session belongs to the predicted batch."
                  : "That session does not match the predicted batch."
              }`
            : `no reference location was imaged at ${session.image_height_px} px height.`}
        </p>
        {result.cautions.map((c) => (
          <p className="unknown-caution" key={c}>
            {c}
          </p>
        ))}
      </div>
    </article>
  );
}

function UnknownBatch({ apiUrl }) {
  const classification = useJson(`${apiUrl}/unknown/classification`);
  const images = useJson(`${apiUrl}/batches/unknown/images`);
  const [locationId, setLocationId] = useState(null);

  let body;
  if (classification.status === "loading" || images.status === "loading") {
    body = <div className="notice" role="status">Loading the unknown batch…</div>;
  } else if (classification.status === "error") {
    body = (
      <div className="notice notice-error" role="alert">
        No classification available ({classification.error}). Put the images in data/raw/unknown and
        run <code>python -m analysis.classify</code>.
      </div>
    );
  } else {
    const data = classification.data;
    const v = data.reference_validation;
    const groups = Object.fromEntries((images.data ?? []).map((g) => [g.specimen_id, g.images]));
    const counts = BATCHES.map((b) => data.locations.filter((l) => l.predicted_batch === b).length);
    const active = data.locations.find((l) => l.location_id === locationId) ?? data.locations[0];
    body = (
      <>
        <div className="kpi-tiles unknown-summary">
          {BATCHES.map((b, i) => (
            <article className="kpi-tile" key={b}>
              <span className="kpi-tile-label">Classified as Batch {b}</span>
              <strong className="kpi-tile-value">{counts[i]}</strong>
              <span className="kpi-tile-meta">
                {data.locations.filter((l) => l.predicted_batch === b).map((l) => l.location_id).join(", ") || "none"}
              </span>
            </article>
          ))}
        </div>
        <div className="kpi-card">
          <h3>How reliable is this?</h3>
          <p className="kpi-card-note unknown-reliability">
            The classifier uses {data.method.features.length} material KPIs measured from each
            location&apos;s BSE image ({data.method.features.map((f) => f.name.toLowerCase()).join(", ")}).
            When each of the {Object.values(v.n_locations).reduce((a, b) => a + b, 0)} reference locations
            is held out and predicted, it is right {Math.round(v.loo_balanced_accuracy * 100)}% of the time
            (balanced across batches; chance is {Math.round(v.chance * 100)}%, permutation p ={" "}
            {v.permutation_p}). Recall by batch: {BATCHES.map((b) => `batch ${b} ${Math.round(v.per_batch_recall[b] * 100)}%`).join(", ")}.
            Treat each call as a lead, not a verdict.
          </p>
        </div>
        <Tabs
          tabs={data.locations.map((l) => ({
            id: l.location_id,
            label: l.location_id,
            badge: `Batch ${l.predicted_batch}`,
          }))}
          active={active.location_id}
          onChange={setLocationId}
          label="Unknown locations"
          idPrefix="unknown-location"
        />
        <div {...tabPanelProps("unknown-location", active.location_id)}>
          <LocationResult
            key={active.location_id}
            result={active}
            images={groups[active.location_id] ?? []}
            apiUrl={apiUrl}
          />
        </div>
      </>
    );
  }

  return (
    <section className="section-block" aria-labelledby="unknown-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">UNSEEN MATERIAL / UNKNOWN BATCH</p>
          <h2 id="unknown-title">Unknown batch: which reference batch is it?</h2>
        </div>
        <span className="section-count">
          {classification.status === "ready"
            ? `${classification.data.locations.length} LOCATIONS · CLASSIFIED AGAINST BATCHES 1–3`
            : "SOURCE: DATA/RAW/UNKNOWN"}
        </span>
      </div>
      {body}
    </section>
  );
}

export default UnknownBatch;
