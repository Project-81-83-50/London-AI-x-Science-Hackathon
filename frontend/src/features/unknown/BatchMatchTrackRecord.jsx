// How often each classifier is right on held-out reference locations, and what that means for one answer.
import { pct } from "../../lib/trackRecord";

function TrackRecord({ kpiValidation, method }) {
  const v = kpiValidation;
  const nRef = Object.values(v.n_locations).reduce((a, b) => a + b, 0);
  return (
    <div className="kpi-card">
      <div className="kpi-card-heading">
        <h3>How reliable is this? Track record on held-out reference locations</h3>
        <span className="kpi-card-note">each of the {nRef} reference locations hidden in turn, then predicted</span>
      </div>
      <div className="kpi-tiles track-tiles">
        <article className="kpi-tile">
          <span className="kpi-tile-label">KPI model</span>
          <strong className="kpi-tile-value">{pct(v.loo_balanced_accuracy)}</strong>
          <span className="kpi-tile-meta">
            balanced accuracy, always answers · chance {pct(v.chance)} · permutation p = {v.permutation_p}
            {v.previous_model ? ` · was ${pct(v.previous_model.loo_balanced_accuracy)} with the fixed eight KPIs` : ""}
          </span>
        </article>
      </div>
      <p className="kpi-card-note unknown-reliability">
        The KPI model ranks all {method.n_candidate_features ?? method.features.length} material KPIs of each
        location&apos;s BSE image by how well they separate the reference batches and keeps the best{" "}
        {method.features.length === 1 ? "one" : method.features.length} (now:{" "}
        {method.features.map((f) => f.name.toLowerCase()).join(", ")}); how many to keep is chosen by an inner
        test, and the accuracy above re-runs that whole choice without each held-out location. Recall by batch:{" "}
        {["1", "2", "3"].map((b) => `batch ${b} ${pct(v.per_batch_recall[b])}`).join(", ")}. With {nRef} reference
        locations the intervals are wide: treat every call as a lead, not a verdict.
      </p>
    </div>
  );
}

export default TrackRecord;
