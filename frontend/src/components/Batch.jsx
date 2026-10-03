import LoadBatchBtn from "./LoadBatchBtn";
import BatchList from "./BatchList";

function Batch({
  apiUrl,
  batches,
  selectedBatch,
  imageState,
  imageError,
  specimens,
  imageCount,
  onSelect,
}) {
  return (
    <>
      <div className="batch-grid batch-grid-three">
        {batches.map((batch) => (
          <article
            className={`batch-card reference-card ${selectedBatch === batch ? "reference-card-selected" : ""}`}
            key={batch}
          >
            <div className="batch-card-top">
              <span className="batch-index">REFERENCE {batch}</span>
              <span className="data-state">
                {selectedBatch === batch
                  ? imageState === "loading"
                    ? "LOADING"
                    : imageState === "error"
                      ? "IMAGE ERROR"
                      : "SELECTED"
                  : "NOT LOADED"}
              </span>
            </div>
            <h3>Batch {batch}</h3>
            <p>
              Local microscopy views grouped by the field of view they show.
              Select this batch to load its images.
            </p>
            <div className="batch-card-foot">
              <span>Image set</span>
              <strong>
                {selectedBatch === batch && imageState === "connected"
                  ? `${specimens.length} ${specimens.every((s) => s.grouping === "matched") ? "fields" : "groups"} · ${imageCount} TIFFs`
                  : "Select to load"}
              </strong>
            </div>
            <LoadBatchBtn
              batch={batch}
              selected={selectedBatch === batch}
              onToggle={onSelect}
            />
          </article>
        ))}
      </div>
      <BatchList
        apiUrl={apiUrl}
        selectedBatch={selectedBatch}
        imageState={imageState}
        imageError={imageError}
        specimens={specimens}
        imageCount={imageCount}
      />
    </>
  );
}

export default Batch;
