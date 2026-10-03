import { batchLabel, isUnknownBatch } from "../../lib/batchLabel";

// Compact batch picker: reference batches plus the unknown set; pressing the selected batch clears it.
function BatchPicker({ batches, selectedBatch, imageState, specimens, imageCount, onSelect }) {
  return (
    <div className="batch-picker" role="group" aria-label="Batch">
      {batches.map((batch) => {
        const selected = selectedBatch === batch;
        const status = !selected
          ? isUnknownBatch(batch)
            ? "Classify against 1–3"
            : "Reference set"
          : imageState === "loading"
            ? "Loading…"
            : imageState === "error"
              ? "Image error"
              : `${specimens.length} locations · ${imageCount} TIFFs`;
        return (
          <button
            key={batch}
            type="button"
            className={`batch-pick ${selected ? "batch-pick-selected" : ""} ${isUnknownBatch(batch) ? "batch-pick-unknown" : ""}`}
            aria-pressed={selected}
            onClick={() => onSelect(batch)}
          >
            <strong>{isUnknownBatch(batch) ? "Unknown" : batchLabel(batch)}</strong>
            <small>{status}</small>
          </button>
        );
      })}
    </div>
  );
}

export default BatchPicker;
