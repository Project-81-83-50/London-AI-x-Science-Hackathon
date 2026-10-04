// Unknown batch: the current method's call for each location (KPI model + v3 material check and explanation).
import { useJson } from "../../hooks/useJson";
import { CompositionBar, ProbBars, Tier, nice } from "./common";

export default function V3UnknownCalls({ apiUrl }) {
  const { status, data, error } = useJson(`${apiUrl}/v3/unknown`);
  if (status === "loading") return <div className="v3-card v3-muted">Loading the batch calls…</div>;
  if (status === "error") return <div className="v3-card v3-error">Batch calls unavailable: {error}</div>;
  return (
    <section className="v3-card">
      <h3>Batch decision (current method)</h3>
      <p className="v3-warn v3-small">
        Note: the track-record statistics on this page — here and in the sections below — are outdated. They were
        computed for earlier versions of the methods and have not been recomputed for the current one.
      </p>
      <p className="v3-small v3-muted">
        Probability = 90% KPI model (Guanyi: a measured material KPI, ETD-dark solid — area dark in ETD but solid in BSE,
        i.e. sub-surface pores) + 10% our v3 material model (U-Net segmentation + DINOv2, no fingerprint). Confidence is
        High when the KPI model is at least 50% sure and the v3 material model agrees, otherwise Low. Batch 1 and
        Batch 2 differ only subtly — Batch 2 is more porous, with more open and hidden sub-surface pores; Batch 1 has
        slightly more and larger SiOx — and their ranges overlap, so calls between them are the hardest.
      </p>
      <div className="v3-grid3">
        {data.locations.map((l) => {
          const c = l.composition;
          const ci = l.sampling_uncertainty_95 || {};
          const iv = (k) => (ci[k] ? ` [${ci[k][0].toFixed(1)}–${ci[k][1].toFixed(1)}]` : "");
          return (
            <div className="v3-card" key={l.location_id} style={{ marginBottom: 0 }}>
              <div className="v3-small v3-muted">Location {l.location_id}</div>
              <div className={`v3-big ${l.answer_type === "unsure" ? "v3-unsure" : ""}`}>{nice(l.answer)}</div>
              <Tier value={l.confidence} />
              <ProbBars probabilities={l.probabilities} highlight={l.answer} />
              {l.material_model_pick && (
                <p className={`v3-small ${l.material_model_agrees ? "v3-muted" : "v3-warn"}`}>
                  Material model check (U-Net + DINOv2): {nice(l.material_model_pick)} —{" "}
                  {l.material_model_agrees ? "agrees." : "disagrees, so confidence is Low."}
                </p>
              )}
              <CompositionBar pore={c.pore} carbon={c["carbon (graphite + binder)"]} siox={c.SiOx} />
              <div className="v3-small v3-muted">
                pore {c.pore.toFixed(1)}%{iv("pore")} · carbon {c["carbon (graphite + binder)"].toFixed(1)}%{iv("carbon")} ·
                SiOx {c.SiOx.toFixed(1)}%{iv("SiOx")} <span title="95% sampling interval (GET4)">(95% sampling interval)</span>
              </div>
              <a className="v3-button v3-ghost" href={`#pipeline/${l.run}`} style={{ display: "inline-block", textDecoration: "none", marginTop: 8 }}>
                Open pipeline →
              </a>
            </div>
          );
        })}
      </div>
    </section>
  );
}
