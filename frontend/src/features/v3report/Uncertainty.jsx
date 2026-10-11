// General report, "How sure are these numbers?": GET4's uncertainty for one reference batch (analysis.v3_report
// `uncertainty`): whether ONE location can be told apart from the other batches, what limits the precision of the
// batch mean, how many locations would be enough, and every location's own GET4 error bar with GET4's image checks
// (from its BSE analysis report, when generated). Same U-Net values as the composition tiles above.
import { useState } from "react";
import { useJson } from "../../hooks/useJson";
import "./Uncertainty.css";

const BATCHES = ["Batch_1", "Batch_2", "Batch_3"];
const PHASE_ORDER = ["pore", "carbon", "SiOx"];
const PHASE_WORDS = { pore: "pore", carbon: "carbon", SiOx: "SiOx" }; // phase names inside a sentence

const batchName = (batch) => batch.replace("_", " ");
const pct = (value) => (Number.isFinite(value) ? `${value.toFixed(1)}%` : "—");
const range = ([lo, hi]) => `${pct(lo)}–${pct(hi)}`;

// Share of range `a` that range `b` covers (0-1).
function coverage(a, b) {
  const width = a[1] - a[0];
  if (width <= 0) return 0;
  return Math.max(0, Math.min(a[1], b[1]) - Math.max(a[0], b[0])) / width;
}

function separability(share) {
  if (share >= 0.8) return "cannot separate";
  if (share >= 0.3) return "only partly separates";
  return "mostly separates";
}

// GET4's image-quality flags (analysis.get4.imaging.quality_flags) in words.
const QUALITY_NAMES = {
  sharpness: "Sharpness",
  noise: "Noise",
  contrast: "Contrast",
  anisotropy: "Directional blur",
  median: "Brightness",
  separability: "Grey-level separation of the phases",
  stripes_curtaining: "Curtaining stripes",
  stripes_scan_lines: "Scan-line stripes",
  stripes_curtaining_after: "Curtaining stripes after filtering",
  stripes_scan_lines_after: "Scan-line stripes after filtering",
  clipped_black: "Clipped black pixels",
  clipped_white: "Clipped white pixels",
  shading: "Uneven shading",
};

function describeFlag(flag) {
  const relative = flag.match(/^(\w+) [\d.]+ vs reference [\d.]+ \(([^)]+)\)$/);
  if (relative) return `${QUALITY_NAMES[relative[1]] || relative[1]} ${relative[2]} vs the rest of the batch`;
  const limit = flag.match(/^(\w+) ([\d.]+) (below|above) limit ([\d.]+)$/);
  if (limit) return `${QUALITY_NAMES[limit[1]] || limit[1]} ${limit[2]} is ${limit[3]} the limit ${limit[4]}`;
  return flag;
}

// Axis covering every range drawn for one phase, rounded out to whole percent.
function axisFor(ranges) {
  const lo = Math.floor(Math.max(0, Math.min(...ranges.map((r) => r[0])) - 1));
  const hi = Math.ceil(Math.min(100, Math.max(...ranges.map((r) => r[1])) + 1));
  return { lo, hi, at: (v) => ((v - lo) / Math.max(hi - lo, 1e-9)) * 100 };
}

function Axis({ axis }) {
  const mid = (axis.lo + axis.hi) / 2;
  return (
    <div className="get4-axis" aria-hidden="true">
      <span>{axis.lo}%</span>
      <span>{Number.isInteger(mid) ? mid : mid.toFixed(1)}%</span>
      <span>{axis.hi}%</span>
    </div>
  );
}

// One batch per row: the light band is where one new location is expected, the dark bar the 95 % interval of the
// batch mean, the dot the mean.
function BatchRanges({ phases, own, axis, phaseName }) {
  return (
    <div className="get4-ranges" role="img" aria-label={`${phaseName}: batch means and new-location ranges`}>
      {BATCHES.map((b) => {
        const p = phases[b];
        const [nlo, nhi] = p.new_location95_pct;
        const [clo, chi] = p.ci95_pct;
        return (
          <div className={`get4-range-row${b === own ? " is-own" : ""}`} key={b}>
            <span className="get4-range-label">{batchName(b)}</span>
            <div className="get4-range-track">
              <span
                className="get4-range-band"
                style={{ left: `${axis.at(nlo)}%`, width: `${axis.at(nhi) - axis.at(nlo)}%` }}
                title={`one new location: ${range(p.new_location95_pct)}`}
              />
              <span
                className="get4-range-ci"
                style={{ left: `${axis.at(clo)}%`, width: `${Math.max(axis.at(chi) - axis.at(clo), 0.6)}%` }}
                title={`batch mean 95% interval: ${range(p.ci95_pct)}`}
              />
              <span className="get4-range-mean" style={{ left: `${axis.at(p.mean_pct)}%` }} />
            </div>
            <span className="get4-range-value">{range(p.new_location95_pct)}</span>
          </div>
        );
      })}
      <div className="get4-range-row get4-range-axis-row">
        <span />
        <Axis axis={axis} />
        <span />
      </div>
    </div>
  );
}

function Locations({ locations, active, p, axis, flags }) {
  return (
    <div className="get4-image-table">
      <div className="get4-image-row get4-image-row-header">
        <span>Location</span>
        <span>{p.name}</span>
        <span>Value</span>
        <span>Image checks</span>
      </div>
      {locations.map((l) => {
        const v = l[active];
        const lo = v.pct - 1.96 * v.se_pp;
        const hi = v.pct + 1.96 * v.se_pp;
        const f = flags[l.sample_id];
        return (
          <article className="get4-image-row" key={l.sample_id}>
            <div className="get4-image-name">
              <strong>{l.sample_id}</strong>
            </div>
            <div
              className="get4-range-track get4-location-track"
              role="img"
              aria-label={`${l.sample_id}: ${pct(v.pct)}, 95% interval ${range([lo, hi])}`}
            >
              <span
                className="get4-range-band"
                style={{
                  left: `${axis.at(p.new_location95_pct[0])}%`,
                  width: `${axis.at(p.new_location95_pct[1]) - axis.at(p.new_location95_pct[0])}%`,
                }}
              />
              <span
                className="get4-location-interval"
                style={{ left: `${axis.at(lo)}%`, width: `${axis.at(hi) - axis.at(lo)}%` }}
              />
              <span className="get4-range-mean" style={{ left: `${axis.at(v.pct)}%` }} />
            </div>
            <strong className="get4-image-value">
              {pct(v.pct)} <small>± {(1.96 * v.se_pp).toFixed(1)}</small>
            </strong>
            <span
              className={`get4-image-status${f?.length ? " has-flags" : ""}`}
              title={f ? f.join("; ") || "No image quality flags" : "GET4 image checks not generated"}
            >
              {!f ? "—" : f.length ? `${f.length} flag${f.length === 1 ? "" : "s"}` : "No flags"}
            </span>
            {f?.length > 0 && (
              <ul className="get4-image-flags">
                {f.map((flag) => (
                  <li key={flag} title={flag}>
                    {describeFlag(flag)}
                  </li>
                ))}
              </ul>
            )}
          </article>
        );
      })}
      <div className="get4-image-row get4-axis-row">
        <span />
        <Axis axis={axis} />
        <span />
        <span />
      </div>
    </div>
  );
}

function Uncertainty({ apiUrl, batch, uncertainty }) {
  const checks = useJson(`${apiUrl}/batches/${batch}/analysis-report?detector=BSE`); // optional image checks
  const [selected, setSelected] = useState("pore");
  const own = `Batch_${batch}`;
  const mine = uncertainty.batches[own];
  const phaseIds = PHASE_ORDER.filter((id) => mine.phases[id]);
  const active = phaseIds.includes(selected) ? selected : phaseIds[0];
  const p = mine.phases[active];
  const all = Object.fromEntries(BATCHES.map((b) => [b, uncertainty.batches[b].phases[active]]));
  const intervals = mine.locations.map((l) => [
    l[active].pct - 1.96 * l[active].se_pp,
    l[active].pct + 1.96 * l[active].se_pp,
  ]);
  const axis = axisFor([...BATCHES.map((b) => all[b].new_location95_pct), ...intervals]);
  const others = BATCHES.filter((b) => b !== own).map((b) => ({
    batch: b,
    share: coverage(p.new_location95_pct, all[b].new_location95_pct),
  }));
  const between = p.budget.between_locations;
  const flags = Object.fromEntries(
    (checks.data?.images || []).map((image) => [image.location_id, image.imaging_flags || []]),
  );
  const flagged = Object.values(flags).filter((f) => f.length).length;
  const target = uncertainty.target_half_width_pp;

  return (
    <div className="kpi-card">
      <div className="kpi-card-heading">
        <h3>How sure are these numbers?</h3>
        <div className="get4-phase-toggle" role="group" aria-label="Phase">
          {phaseIds.map((id) => (
            <button
              type="button"
              key={id}
              className={id === active ? "is-selected" : ""}
              aria-pressed={id === active}
              onClick={() => setSelected(id)}
            >
              {mine.phases[id].name.replace(" (graphite + binder)", "")}
            </button>
          ))}
        </div>
      </div>
      <p className="kpi-card-note get4-intro">
        Each composition is measured on {mine.n_locations} image fields, so it is an estimate. GET4 sizes the error in
        two layers: <b>within an image</b> (neighbouring pixels are correlated, so an image holds fewer independent
        samples than pixels) and <b>between locations</b> (the electrode itself varies from place to place).
      </p>

      <div className="get4-block">
        <div className="get4-subheading">
          <h4>Can one location be told apart?</h4>
          <span>light band: where one new location is expected · dark bar: batch mean (95%)</span>
        </div>
        <BatchRanges phases={all} own={own} axis={axis} phaseName={p.name} />
        <p className="get4-reading">
          {batchName(own)}&apos;s mean {PHASE_WORDS[active]} is known to <b>± {p.half_width_pp.toFixed(1)} pp</b>, but
          single locations scatter much more: one new {batchName(own)} location is expected at{" "}
          <b>{range(p.new_location95_pct)}</b>.{" "}
          {others.map((o, i) => (
            <span key={o.batch}>
              {i === 0 ? "" : " "}
              {batchName(o.batch)}&apos;s range covers {Math.round(o.share * 100)}% of it, so {PHASE_WORDS[active]}{" "}
              alone <b>{separability(o.share)}</b> a single location from {batchName(o.batch)}.
            </span>
          ))}
        </p>
      </div>

      <div className="get4-block get4-two-col">
        <div>
          <div className="get4-subheading">
            <h4>What limits the precision?</h4>
          </div>
          <div
            className="get4-budget-bar"
            role="img"
            aria-label={`within images ${Math.round((1 - between) * 100)}%, between locations ${Math.round(between * 100)}%`}
          >
            <span className="get4-budget-segment get4-budget-area" style={{ width: `${(1 - between) * 100}%` }} />
            <span className="get4-budget-segment get4-budget-between" style={{ width: `${between * 100}%` }} />
          </div>
          <div className="get4-budget-legend">
            <span>
              <i className="get4-budget-dot get4-budget-area" />
              within images <strong>{Math.round((1 - between) * 100)}%</strong>
            </span>
            <span>
              <i className="get4-budget-dot get4-budget-between" />
              between locations <strong>{Math.round(between * 100)}%</strong>
            </span>
          </div>
          <p className="get4-reading">
            {between >= 0.5
              ? "Most of the uncertainty is real variation between locations, so imaging more locations helps far more than imaging larger areas: "
              : "Much of the uncertainty comes from within the images (limited area and uneven structure), so larger fields of view help too: "}
            twice the locations narrows the interval by <b>{Math.round(p.narrowing_double_locations_pct)}%</b>, twice
            the area of every image by <b>{Math.round(p.narrowing_double_image_area_pct)}%</b>.
          </p>
        </div>
        <div>
          <div className="get4-subheading">
            <h4>How many locations are enough?</h4>
          </div>
          <ul className="get4-projection">
            {p.projection.map((row) => (
              <li key={row.locations} className={row.locations === mine.n_locations ? "is-now" : ""}>
                <span>
                  {row.locations} locations{row.locations === mine.n_locations ? " (now)" : ""}
                </span>
                <strong>± {row.half_width_pp.toFixed(1)} pp</strong>
              </li>
            ))}
          </ul>
          <p className="get4-reading">
            {p.half_width_pp <= target
              ? `The batch mean is already known to within ±${target} pp.`
              : p.locations_for_target
                ? `About ${p.locations_for_target} locations would pin the batch mean to ±${target} pp, if new locations vary like these.`
                : `More than 1000 locations would be needed for ±${target} pp.`}
          </p>
        </div>
      </div>

      <details className="get4-details">
        <summary>
          Every location: its own error bar and image checks
          {checks.status === "ready" && (
            <span className={`get4-image-status${flagged ? " has-flags" : ""}`}>
              {flagged ? `${flagged} flagged` : "no image flags"}
            </span>
          )}
        </summary>
        <p className="kpi-card-note">
          dot: measured value · line: 95% interval for that image alone · band: where a new location is expected
        </p>
        <Locations locations={mine.locations} active={active} p={p} axis={axis} flags={flags} />
      </details>

      <p className="get4-method">
        Method: GET4 gives each image a standard error from its U-Net label map (two-point covariance for the number of
        independent samples, tile overdispersion for uneven structure). The spread between locations is split into that
        image error and real location-to-location variation (random effects, never below the image error), with t
        intervals over the locations. Image checks compare each BSE image&apos;s sharpness, noise, contrast and
        curtaining stripes with the rest of the batch. Not included: systematic segmentation error (see Segmentation
        accuracy below).
      </p>
    </div>
  );
}

export default Uncertainty;
