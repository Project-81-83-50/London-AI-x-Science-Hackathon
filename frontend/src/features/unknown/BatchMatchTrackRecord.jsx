// How often each classifier is right on held-out reference locations, and what that means for one answer.
import { useTooltip } from "../../hooks/useTooltip";
import { pct } from "../../lib/trackRecord";

const batchName = (b) => (b ? String(b).replaceAll("_", " ") : "—");

// One dot per held-out reference location, placed by the model's confidence; shape and colour show the outcome.
function ConfidenceStrip({ records, threshold }) {
  const { frame, handlers, layer, width } = useTooltip(640);
  const left = 8;
  const right = 8;
  const lo = 0.3;
  const x = (c) => left + ((c - lo) / (1 - lo)) * (width - left - right);
  // Dots that would overlap stack upwards; the chart grows to fit the tallest stack.
  const step = 11;
  const placed = [];
  const stacked = [...records]
    .filter((r) => r.confidence !== null)
    .sort((a, b) => a.confidence - b.confidence)
    .map((r) => {
      const cx = x(Math.max(lo, r.confidence));
      const level = placed.filter((p) => Math.abs(p - cx) < step).length;
      placed.push(cx);
      return { ...r, cx, level };
    });
  const top = 24 + step * Math.max(0, ...stacked.map((r) => r.level));
  const base = top + 46;
  const dots = stacked.map((r) => ({ ...r, cy: base - 10 - r.level * step }));
  const ticks = [0.4, 0.6, 0.8, 1.0];
  const outcome = (r) => (r.correct === null ? "unsure" : r.correct ? "right" : "wrong");
  return (
    <div className="kpi-chart-frame" ref={frame}>
      <svg
        viewBox={`0 0 ${width} ${base + 24}`}
        className="kpi-chart"
        role="img"
        aria-label={`Held-out reference locations by confidence: ${records.filter((r) => r.correct).length} right, ${records.filter((r) => r.correct === false).length} wrong, ${records.filter((r) => r.correct === null).length} unsure`}
      >
        <line x1={left} x2={width - right} y1={base} y2={base} className="track-axis" />
        {ticks.map((t) => (
          <text key={t} x={x(t)} y={base + 18} className="kpi-row-label" textAnchor="middle">
            {pct(t)}
          </text>
        ))}
        {Number.isFinite(threshold) && threshold <= 1 && (
          <g>
            <line x1={x(threshold)} x2={x(threshold)} y1="6" y2={base} className="track-threshold" />
            <text x={x(threshold) - 4} y="14" className="kpi-row-label" textAnchor="end">
              answers from here →
            </text>
          </g>
        )}
        {dots.map((r) => (
          <g
            key={r.item}
            className="kpi-hit"
            {...handlers([
              { value: r.item, label: `truth ${batchName(r.truth)}` },
              { value: batchName(r.answer), label: r.how === "material" ? "answer (material rule)" : "answer" },
              { value: pct(r.confidence), label: "model confidence" },
            ])}
          >
            <circle cx={r.cx} cy={r.cy} r="9" fill="transparent" />
            {outcome(r) === "wrong" ? (
              <path
                d={`M${r.cx - 4} ${r.cy - 4}L${r.cx + 4} ${r.cy + 4}M${r.cx + 4} ${r.cy - 4}L${r.cx - 4} ${r.cy + 4}`}
                className="track-wrong"
              />
            ) : (
              <circle cx={r.cx} cy={r.cy} r="4.5" className={`track-${outcome(r)}`} />
            )}
          </g>
        ))}
      </svg>
      {layer}
      <p className="track-legend">
        <span><i className="track-key track-key-right" /> right</span>
        <span><i className="track-key track-key-wrong">×</i> wrong</span>
        <span><i className="track-key track-key-unsure" /> answered “unsure”</span>
        <span>x-axis: the model&apos;s confidence in its top batch</span>
      </p>
    </div>
  );
}

// Side-by-side track record of the two classifiers that classify the unknown batch.
function TrackRecord({ kpiValidation, method, evaluation, evaluationStatus, threshold }) {
  const v = kpiValidation;
  const bm = evaluation?.modes?.default?.locations;
  const forced = evaluation?.modes?.forced?.locations;
  const nRef = Object.values(v.n_locations).reduce((a, b) => a + b, 0);
  return (
    <div className="kpi-card">
      <div className="kpi-card-heading">
        <h3>How reliable is this? Track record on held-out reference locations</h3>
        <span className="kpi-card-note">each of the {nRef} reference locations hidden in turn, then predicted</span>
      </div>
      <div className="kpi-tiles track-tiles">
        <article className="kpi-tile">
          <span className="kpi-tile-label">KPI model (main call)</span>
          <strong className="kpi-tile-value">{pct(v.loo_balanced_accuracy)}</strong>
          <span className="kpi-tile-meta">
            balanced accuracy, always answers · chance {pct(v.chance)} · permutation p = {v.permutation_p}
            {v.previous_model ? ` · was ${pct(v.previous_model.loo_balanced_accuracy)} with the fixed eight KPIs` : ""}
          </span>
        </article>
        <article className="kpi-tile">
          <span className="kpi-tile-label">Batch match: right when it answers</span>
          <strong className="kpi-tile-value">{bm ? pct(bm.accuracy_when_answering) : "—"}</strong>
          <span className="kpi-tile-meta">
            {bm
              ? `${bm.right} of ${bm.answered} answers right · 95% CI ${pct(bm.ci95?.[0])}–${pct(bm.ci95?.[1])}`
              : evaluationStatus === "loading"
                ? "loading…"
                : "not evaluated yet: python -m analysis.batch_match evaluate"}
          </span>
        </article>
        <article className="kpi-tile">
          <span className="kpi-tile-label">Batch match: how often it answers</span>
          <strong className="kpi-tile-value">{bm ? pct(bm.coverage) : "—"}</strong>
          <span className="kpi-tile-meta">
            {bm ? `${bm.answered} of ${bm.n} locations; the rest “unsure”` : "—"}
          </span>
        </article>
        <article className="kpi-tile">
          <span className="kpi-tile-label">Batch match, forced to always answer</span>
          <strong className="kpi-tile-value">{forced ? pct(forced.accuracy_when_answering) : "—"}</strong>
          <span className="kpi-tile-meta">
            {forced ? `${forced.right} of ${forced.n} locations · 95% CI ${pct(forced.ci95?.[0])}–${pct(forced.ci95?.[1])}` : "—"}
          </span>
        </article>
      </div>

      {bm && (
        <>
          <h4 className="track-subhead">Batch match: confidence against outcome, per held-out location</h4>
          <ConfidenceStrip records={bm.records} threshold={threshold} />
          <table className="kpi-table track-table">
            <thead>
              <tr>
                <th scope="col">True batch</th>
                <th scope="col">Locations</th>
                <th scope="col">Right</th>
                <th scope="col">Wrong</th>
                <th scope="col">Unsure</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(bm.per_batch).map(([b, s]) => (
                <tr key={b}>
                  <th scope="row">{batchName(b)}</th>
                  <td className="kpi-num">{s.n}</td>
                  <td className="kpi-num">{s.right}</td>
                  <td className="kpi-num">{s.wrong}</td>
                  <td className="kpi-num">{s.unsure}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      <p className="kpi-card-note unknown-reliability">
        The KPI model ranks all {method.n_candidate_features ?? method.features.length} material KPIs of each
        location&apos;s BSE image by how well they separate the reference batches and keeps the best{" "}
        {method.features.length === 1 ? "one" : method.features.length} (now:{" "}
        {method.features.map((f) => f.name.toLowerCase()).join(", ")}); how many to keep is chosen by an inner
        test, and the accuracy above re-runs that whole choice without each held-out location. Recall by batch:{" "}
        {["1", "2", "3"].map((b) => `batch ${b} ${pct(v.per_batch_recall[b])}`).join(", ")}. Batch match answers only
        above the confidence at which held-out answers were at least {pct(evaluation?.target_accuracy ?? 0.9)} right,
        and says “unsure” otherwise. It mostly recognises how each batch was imaged, so its record holds for images
        from the same imaging sessions. With {nRef} reference locations the intervals are wide: treat every call as
        a lead, not a verdict.
      </p>
    </div>
  );
}

export default TrackRecord;
