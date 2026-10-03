// Compact reference-batch picker: one button per batch; pressing the selected batch again clears it.
function BatchPicker({ batches, selectedBatch, imageState, specimens, imageCount, onSelect }) {
  return (
    <div className="batch-picker" role="group" aria-label="Reference batch">
      {batches.map((batch) => {
        const selected = selectedBatch === batch;
        const status = !selected
          ? "Reference set"
          : imageState === "loading"
            ? "Loading…"
            : imageState === "error"
              ? "Image error"
              : `${specimens.length} locations · ${imageCount} TIFFs`;
        return (
          <button
            key={batch}
            type="button"
            className={`batch-pick ${selected ? "batch-pick-selected" : ""}`}
            aria-pressed={selected}
            onClick={() => onSelect(batch)}
          >
            <strong>Batch {batch}</strong>
            <small>{status}</small>
          </button>
        );
      })}
    </div>
  );
}

export default BatchPicker;
