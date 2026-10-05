// Formatting shared by the General and Detailed reports (SEM pipeline v3 data).
export const V3_BATCHES = ["Batch_1", "Batch_2", "Batch_3"];

// A 0-1 fraction as a percentage string; missing values count as 0.
export const percent = (fraction, digits = 0) => `${((fraction ?? 0) * 100).toFixed(digits)}%`;
// "Batch_1" -> "Batch 1".
export const humanize = (name) => String(name ?? "").replaceAll("_", " ");

const DIGITS = { "%": 1, µm: 2, ratio: 3, "per 1000 µm²": 1 };

export function formatValue(value, unit) {
  if (!Number.isFinite(value)) return "—";
  if (unit === "%") return `${value.toFixed(1)}%`;
  const shown = value.toFixed(DIGITS[unit] ?? 2);
  return unit && unit !== "ratio" && !unit.includes("…") ? `${shown} ${unit}` : shown;
}

// Table cells: the number alone (percent keeps its sign); the unit is shown once in the header.
export function formatNumber(value, unit) {
  if (!Number.isFinite(value)) return "—";
  return unit === "%" ? `${value.toFixed(1)}%` : value.toFixed(DIGITS[unit] ?? 2);
}

export const unitLabel = (unit) => (unit && unit !== "%" && unit !== "ratio" ? unit : "");

export function formatP(p) {
  if (!Number.isFinite(p)) return "—";
  return p < 0.001 ? "< 0.001" : p.toFixed(3);
}

// Whose report this is: a reference batch (compared with the other two) or the unknown batch (compared with all three).
export function reportSubject(data) {
  const key = data.own_key ?? `Batch_${data.batch_id}`;
  const unknown = key === "unknown";
  return {
    key,
    unknown,
    name: unknown ? "Unknown batch" : `Batch ${data.batch_id}`,
    others: V3_BATCHES.filter((b) => b !== key),
  };
}

// How a metric's batch difference should be read: holds within imaging sessions, may be session, or none.
export function differenceKind(stat, alpha = 0.05) {
  if (!stat || !(stat.kruskal_p < alpha)) return "none";
  return stat.session_stratified_p < alpha ? "robust" : "session";
}

export const DIFFERENCE_LABEL = {
  robust: "differs · holds within sessions",
  session: "differs · may be session",
  none: "no clear difference",
};
