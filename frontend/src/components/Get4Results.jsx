import { useState } from "react";
import "./Get4Results.css";

const DETECTOR_DESCRIPTIONS = {
  BSE: "Provisional intensity-based phase labels. Check the segmentation before interpreting as material phases.",
};

function getMeasurements(report) {
  if (report?.measurements?.phases) return report.measurements.phases;
  if (report?.measurements?.intensity_classes)
    return report.measurements.intensity_classes;
  if (report?.phases) return report.phases;
  if (report?.intensity_classes) return report.intensity_classes;
  return {};
}

function getImageFractions(image, report) {
  if (image.fraction_estimates) return image.fraction_estimates;

  const measurements =
    report?.detector === "BSE" ? image.phases : image.intensity_classes;
  if (!measurements) return {};

  return Object.fromEntries(
    Object.entries(measurements).map(([name, measurement]) => [
      name,
      {
        fraction: measurement.phi,
        uncertainty_95: [
          Math.max(0, measurement.phi - 1.959964 * measurement.se_image),
          Math.min(1, measurement.phi + 1.959964 * measurement.se_image),
        ],
      },
    ]),
  );
}

function formatPercent(value) {
  return Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : "—";
}

function formatInterval(interval) {
  return Array.isArray(interval) && interval.length === 2
    ? `${formatPercent(interval[0])}–${formatPercent(interval[1])}`
    : "Interval unavailable";
}

function FractionInterval({ fraction, interval, label }) {
  const lower = Number(interval?.[0]);
  const upper = Number(interval?.[1]);
  const point = Number(fraction);
  const hasInterval =
    Number.isFinite(lower) && Number.isFinite(upper) && upper >= lower;

  return (
    <svg
      className="get4-interval"
      viewBox="0 0 100 24"
      role="img"
      aria-label={
        hasInterval
          ? `${label}: ${formatPercent(point)}, 95% interval ${formatInterval(interval)}`
          : `${label}: uncertainty interval unavailable`
      }
    >
      <line x1="0" x2="100" y1="12" y2="12" className="get4-interval-track" />
      {hasInterval && (
        <>
          <line
            x1={lower * 100}
            x2={upper * 100}
            y1="12"
            y2="12"
            className="get4-interval-range"
          />
          <line
            x1={lower * 100}
            x2={lower * 100}
            y1="6"
            y2="18"
            className="get4-interval-cap"
          />
          <line
            x1={upper * 100}
            x2={upper * 100}
            y1="6"
            y2="18"
            className="get4-interval-cap"
          />
        </>
      )}
      {Number.isFinite(point) && (
        <circle
          cx={point * 100}
          cy="12"
          r="4"
          className="get4-interval-point"
        />
      )}
    </svg>
  );
}

function Get4Results({
  report = null,
  batchLabel = "",
  title = "Image uncertainty",
  loading = false,
  error = "",
}) {
  const [selectedClass, setSelectedClass] = useState("");
  const [selectedLocation, setSelectedLocation] = useState("all");

  const measurements = getMeasurements(report);
  const classNames = Object.keys(measurements);
  const images = Array.isArray(report?.images) ? report.images : [];
  const locations = [
    ...new Set(images.map((image) => image.location_id).filter(Boolean)),
  ].sort();
  const activeClass = classNames.includes(selectedClass)
    ? selectedClass
    : classNames[0] || "";
  const filteredImages = images.filter(
    (image) =>
      selectedLocation === "all" || image.location_id === selectedLocation,
  );
  const detector = report?.detector?.toUpperCase() || "UNKNOWN";
  const isEmpty = !report || classNames.length === 0;

  if (loading || error || isEmpty) {
    return (
      <section className="get4-panel" aria-labelledby="get4-results-title">
        <div className="get4-heading">
          <div>
            <p className="get4-eyebrow">GET4 / UNCERTAINTY REPORT</p>
            <h2 id="get4-results-title">{title}</h2>
          </div>
          <span className="get4-badge">
            {loading ? "LOADING" : error ? "UNAVAILABLE" : "NO REPORT"}
          </span>
        </div>
        <div
          className={`get4-empty${error ? " get4-empty-error" : ""}`}
          role={error ? "alert" : "status"}
        >
          <strong>
            {loading
              ? "Loading GET4 analysis…"
              : error
                ? "Could not load GET4 analysis."
                : "No analysis report is available for this selection."}
          </strong>
          <span>
            {loading
                ? "Fetching the generated analysis_report.json from the local API."
              : error ||
                "Run GET4.py --project from the repository root, then restart the API if needed."}
          </span>
        </div>
      </section>
    );
  }

  const pooled = measurements[activeClass] || {};
  const pooledInterval = pooled.ci95;
  const reportMetrics = Array.isArray(report.kpis)
    ? report.kpis
    : Array.isArray(report.image_metrics)
      ? report.image_metrics
      : [];
  const kpisById = Object.fromEntries(
    reportMetrics.map((metric) => [metric.id, metric]),
  );
  const uncertaintyBudget = pooled.budget || {};
  const budgetTotal = Object.values(uncertaintyBudget).reduce(
    (sum, value) => sum + (Number(value) || 0),
    0,
  );

  return (
    <section className="get4-panel" aria-labelledby="get4-results-title">
      <div className="get4-heading">
        <div>
          <p className="get4-eyebrow">
            GET4 / {detector} / {batchLabel || "BATCH REPORT"}
          </p>
          <h2 id="get4-results-title">{report.report_title || title}</h2>
        </div>
        <span className="get4-badge">{images.length} IMAGE FIELDS</span>
      </div>

      <p className="get4-interpretation">
        {report.segmentation_interpretation ||
          DETECTOR_DESCRIPTIONS[detector] ||
          "Intensity classes are not validated material-phase labels."}
      </p>

      {report.comparison?.reason && (
        <p className="get4-comparison-note">{report.comparison.reason}</p>
      )}

      {report.report_summary && report.analysis_settings?.mode !== "fast" && (
        <p className="get4-comparison-note">{report.report_summary}</p>
      )}

      {report.analysis_settings?.mode === "fast" && (
        <p className="get4-comparison-note get4-fast-mode-note">
          Fast mode report.{" "}
          {Number.isFinite(report.analysis_settings.target_pixel_nm)
            ? `Images were analysed at ${report.analysis_settings.target_pixel_nm.toFixed(1)} nm per pixel. `
            : ""}
          Fine detail may be lost at this scale; per-image plots were skipped.
          Run GET4 without <code>--fast</code>{" "}
          when you need the full-resolution analysis and plots.
        </p>
      )}

      {report.decision?.status === "not_assessed" && (
        <p className="get4-comparison-note">
          No accept/watch/reject verdict is assigned. {report.decision.reason}
        </p>
      )}

      {reportMetrics.length > 0 && (
        <div
          className="get4-kpi-grid"
          aria-label={
            report.kpis?.length
              ? "Provisional image-derived KPIs"
              : "Detector intensity metrics"
          }
        >
          {reportMetrics.map((metric) => (
            <article className="get4-kpi-card" key={metric.id}>
              <div className="get4-kpi-topline">
                <span>{metric.name}</span>
                <span className="get4-kpi-status">{metric.status}</span>
              </div>
              <strong>{formatPercent(metric.value)}</strong>
              <span className="get4-kpi-interval">
                95% CI {formatInterval([metric.ci_low, metric.ci_high])}
              </span>
              <small>
                {metric.locations_measured} locations · between-location SD{" "}
                {Number.isFinite(metric.between_location_sd)
                  ? formatPercent(metric.between_location_sd)
                  : "not estimable"}
              </small>
              <small>{metric.evidence_note}</small>
            </article>
          ))}
        </div>
      )}

      <div className="get4-class-picker" aria-label="Select an image class">
        {classNames.map((name) => {
          const estimate = measurements[name];
          const isSelected = activeClass === name;
          const kpi = kpisById[name];
          return (
            <button
              className={`get4-class-card${isSelected ? " is-selected" : ""}`}
              type="button"
              key={name}
              aria-pressed={isSelected}
              onClick={() => setSelectedClass(name)}
            >
              <span>{kpi?.name || name}</span>
              <strong>{formatPercent(estimate.phi)}</strong>
              <small>95% CI {formatInterval(estimate.ci95)}</small>
            </button>
          );
        })}
      </div>

      <div className="get4-summary-grid">
        <article className="get4-summary-card">
          <span>Selected class</span>
          <strong>{activeClass || "—"}</strong>
        </article>
        <article className="get4-summary-card">
          <span>Images in estimate</span>
          <strong>{pooled.n_images ?? images.length}</strong>
        </article>
        <article className="get4-summary-card">
          <span>95% batch interval</span>
          <strong>{formatInterval(pooledInterval)}</strong>
        </article>
        <article className="get4-summary-card">
          <span>Between-location variation</span>
          <strong>
            {Number.isFinite(pooled.tau) ? pooled.tau.toFixed(4) : "Not available"}
          </strong>
        </article>
      </div>

      {budgetTotal > 0 && (
        <div className="get4-budget">
          <div className="get4-subheading">
            <h3>What contributes to uncertainty?</h3>
            <span>Share of estimated variance</span>
          </div>
          <div
            className="get4-budget-bar"
            role="img"
            aria-label={Object.entries(uncertaintyBudget)
              .map(
                ([name, value]) =>
                  `${name}: ${Math.round((value / budgetTotal) * 100)}%`,
              )
              .join(", ")}
          >
            {Object.entries(uncertaintyBudget).map(([name, value]) => (
              <span
                className={`get4-budget-segment get4-budget-${name.replaceAll(" ", "-")}`}
                key={name}
                style={{ width: `${(value / budgetTotal) * 100}%` }}
              />
            ))}
          </div>
          <div className="get4-budget-legend">
            {Object.entries(uncertaintyBudget).map(([name, value]) => (
              <span key={name}>
                <i className={`get4-budget-dot get4-budget-${name.replaceAll(" ", "-")}`} />
                {name} <strong>{Math.round((value / budgetTotal) * 100)}%</strong>
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="get4-subheading get4-location-heading">
        <div>
          <h3>Image-by-image estimates</h3>
          <span>Point estimate and per-image 95% interval; scale is 0–100%.</span>
        </div>
        {locations.length > 0 && (
          <label className="get4-location-filter">
            Location
            <select
              value={selectedLocation}
              onChange={(event) => setSelectedLocation(event.target.value)}
            >
              <option value="all">All locations</option>
              {locations.map((location) => (
                <option value={location} key={location}>
                  {location}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {filteredImages.length === 0 ? (
        <p className="get4-no-images">No images match this location.</p>
      ) : (
        <div className="get4-image-table">
          <div className="get4-image-row get4-image-row-header">
            <span>Location / image</span>
            <span>Fraction and 95% interval</span>
            <span>Value</span>
            <span>Image checks</span>
          </div>
          {filteredImages.map((image) => {
            const estimate = getImageFractions(image, report)[activeClass] || {};
            const flags = image.imaging_flags || [];
            return (
              <article className="get4-image-row" key={image.image}>
                <div className="get4-image-name">
                  <strong>{image.location_id || "Location unavailable"}</strong>
                  <span title={image.image}>{image.image}</span>
                </div>
                <FractionInterval
                  fraction={estimate.fraction}
                  interval={estimate.uncertainty_95}
                  label={`${image.location_id || image.image} ${activeClass}`}
                />
                <strong className="get4-image-value">
                  {formatPercent(estimate.fraction)}
                </strong>
                <span
                  className={`get4-image-status${flags.length ? " has-flags" : ""}`}
                  title={flags.join("; ") || "No image quality flags"}
                >
                  {flags.length ? `${flags.length} flag${flags.length === 1 ? "" : "s"}` : "No flags"}
                </span>
                {flags.length > 0 && (
                  <ul className="get4-image-flags">
                    {flags.map((flag) => (
                      <li key={flag}>{flag}</li>
                    ))}
                  </ul>
                )}
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}

export default Get4Results;
