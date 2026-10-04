// What the batch-match track record (held-out reference locations) says about a single answer.
export const pct = (x) => (Number.isFinite(x) ? `${Math.round(x * 100)}%` : "—");

// Held-out locations whose confidence was at least `confidence`: how often their top batch was right.
export function heldOutAtConfidence(records, confidence) {
  const near = records.filter((r) => r.confidence !== null && r.confidence >= confidence - 1e-9);
  return { n: near.length, right: near.filter((r) => r.leaning === r.truth).length };
}

// What the track record says about one batch-match answer.
export function answerReliability(match, evaluation) {
  if (!match) return null;
  if (match.how === "known location") return "Certain: the image shows a field already in the reference set.";
  if (match.how === "refused") return null;
  const loc = evaluation?.modes?.default?.locations;
  if (!loc) return null;
  if (match.how === "material") {
    const rule = loc.by_rule.material;
    return rule
      ? `Decided by the material range rule, which was right on ${rule.right} of ${rule.answered} held-out locations it decided.`
      : "Decided by the material range rule (it decided no held-out location in testing).";
  }
  const confidence = Math.max(...Object.values(match.probabilities ?? {}));
  if (!Number.isFinite(confidence)) return null;
  const { n, right } = heldOutAtConfidence(loc.records, confidence);
  const lead = `Confidence ${pct(confidence)}.`;
  if (n === 0) return `${lead} No held-out reference location reached this confidence, so there is no track record for it.`;
  return `${lead} Held-out reference locations at this confidence or higher: ${right} of ${n} right (${pct(right / n)}).`;
}
