import { batchLabel, isUnknownBatch } from "../../lib/batchLabel";

// Compact batch picker: reference batches plus the unknown set; pressing the selected batch clears it.
function BatchPicker({
  apiUrl,
  inventory = [],
  libraryState,
  batches,
  selectedBatch,
  imageState,
  specimens,
  imageCount,
  onSelect,
}) {
  return (
    <div className="batch-picker" role="group" aria-label="Batch">
      {batches.map((batch) => {
        const selected = selectedBatch === batch;
        const unknown = isUnknownBatch(batch);
        const entry = inventory.find((row) => row.batch_id === batch);
        const count = selected && imageState === "connected" ? imageCount : entry?.image_count;
        const groups = selected && imageState === "connected" ? specimens.length : entry?.group_count;
        const status =
          libraryState === "loading"
            ? "Scanning local folders…"
            : !entry
              ? "Inventory unavailable"
              : entry.status === "missing"
                ? "Folder not found"
                : entry.status === "empty"
                  ? "No TIFFs yet"
                  : `${count} TIFF views · ${groups} ${entry.grouping === "matched" ? "matched groups" : "filename groups"}`;
        return (
          <button
            key={batch}
            type="button"
            className={`batch-pick ${selected ? "batch-pick-selected" : ""} ${unknown ? "batch-pick-unknown" : ""}`}
            aria-pressed={selected}
            aria-label={`Browse ${batchLabel(batch)}`}
            onClick={() => onSelect(batch)}
          >
            {!unknown && (
              <span className="batch-cover">
                {entry?.preview ? (
                  <img
                    src={`${apiUrl}/batches/${batch}/images/${encodeURIComponent(entry.preview)}`}
                    alt={`${batchLabel(batch)} local reference preview`}
                    decoding="async"
                  />
                ) : (
                  <span className="batch-cover-empty">
                    {libraryState === "loading" ? "Loading local library" : "Add local reference images"}
                  </span>
                )}
                <span className="batch-cover-label">Provided reference · {batchLabel(batch)}</span>
              </span>
            )}
            <span className="batch-card-body">
              <span className="batch-card-title">
                <strong>{unknown ? "Unknown image set" : batchLabel(batch)}</strong>
                <span className="batch-availability">
                  {unknown
                    ? "Separate from references"
                    : entry?.status === "ready"
                      ? "Available locally"
                      : "Local folder"}
                </span>
              </span>
              <small>{status}</small>
              {!unknown && (
                <span className="detector-chips">
                  {Object.entries(entry?.detectors || {}).map(([detector, total]) => (
                    <span key={detector}>
                      {detector === "INLENS" ? "InLens" : detector} · {total}
                    </span>
                  ))}
                </span>
              )}
              <code className="batch-source">
                {entry?.source || (unknown ? "data/raw/unknown" : `ReferenceBatches/Batch_${batch}`)}
              </code>
              <span className="batch-browse">
                {selected
                  ? "Selected · click to close"
                  : unknown
                    ? "Inspect unknown images and classification"
                    : "Browse detector views"}
              </span>
            </span>
          </button>
        );
      })}
    </div>
  );
}

export default BatchPicker;
