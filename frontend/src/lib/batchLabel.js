// Display helpers for batch IDs: reference batches are "1", "2", "3"; the unknown set is "unknown".
export const UNKNOWN_BATCH = "unknown";

export function isUnknownBatch(batch) {
  return batch === UNKNOWN_BATCH;
}

export function batchLabel(batch) {
  return isUnknownBatch(batch) ? "Unknown batch" : `Batch ${batch}`;
}

export function batchFolder(batch) {
  return isUnknownBatch(batch) ? "data/raw/unknown" : `data/raw/batch_${batch}`;
}
