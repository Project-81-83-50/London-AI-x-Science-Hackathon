function BatchList({
  apiUrl,
  selectedBatch,
  imageState,
  imageError,
  specimens,
  imageCount,
}) {
  if (!selectedBatch) return null;
  const matched = specimens.length > 0 && specimens.every((s) => s.grouping === "matched");

  return (
    <section
      className="section-block"
      id="reference-images"
      aria-labelledby="reference-images-title"
    >
      <div className="section-heading">
        <div>
          <p className="eyebrow">LOCAL DATA / RAW BATCH {selectedBatch}</p>
          <h2 id="reference-images-title">
            Batch {selectedBatch} microscopy images
          </h2>
        </div>
        <span className="section-count">
          {imageState === "connected"
            ? `${specimens.length} LOCATIONS · ${imageCount} TIFFS`
            : imageState === "loading"
              ? "LOADING IMAGE INVENTORY"
              : imageState === "error"
                ? "IMAGE INVENTORY UNAVAILABLE"
                : ""}
        </span>
      </div>
      {imageState === "loading" && (
        <div className="notice" role="status">
          Loading Batch {selectedBatch} image inventory…
        </div>
      )}
      {imageState === "error" && (
        <div className="notice notice-error" role="alert">
          Could not load Batch {selectedBatch} images ({imageError}). Check the
          API and confirm the files are in data/raw/batch_{selectedBatch}.
        </div>
      )}
      {imageState === "connected" && specimens.length === 0 && (
        <div className="notice">
          No supported TIFF images were found in data/raw/batch_{selectedBatch}.
        </div>
      )}
      {imageState === "connected" && specimens.length > 0 && (
        <div className={`notice ${matched ? "" : "notice-error"}`}>
          {matched
            ? "Images are grouped by the location they show and labelled location_filter. Each label is checked against the image itself; a label that disagrees with the image is replaced and marked."
            : "Views are grouped by filename code, which does not reliably identify the imaged field. Run field_matching.py to group views by matched field."}
        </div>
      )}
      {imageState === "connected" && specimens.length > 0 && (
        <div className="specimen-grid">
          {specimens.map((specimen) => (
            <article className="specimen-panel" key={specimen.specimen_id}>
              <div className="specimen-heading">
                <h3>Location {specimen.specimen_id}</h3>
                <span
                  title={
                    specimen.location_alternatives?.length
                      ? `Codes that fit equally well: ${specimen.location_alternatives.join(", ")}`
                      : undefined
                  }
                >
                  {specimen.images.length}{" "}
                  {specimen.images.length === 1 ? "view" : "views"}
                  {specimen.location_recovered === false ? " · name assigned" : ""}
                </span>
              </div>
              <div className="microscopy-grid">
                {specimen.images.map((image) => {
                  const imageUrl = `${apiUrl}/batches/${selectedBatch}/images/${encodeURIComponent(image.filename)}`;
                  return (
                    <figure className="microscopy-image" key={image.filename}>
                      <a
                        className="microscopy-preview-link"
                        href={imageUrl}
                        target="_blank"
                        rel="noreferrer"
                        aria-label={`Open enlarged preview of ${image.filename} from batch ${selectedBatch}`}
                      >
                        <img
                          src={imageUrl}
                          alt={`Batch ${selectedBatch} ${image.detector ?? image.filter} view, file ${image.filename}`}
                          loading="lazy"
                          decoding="async"
                        />
                      </a>
                      <figcaption>
                        <span>
                          {image.detector ? (
                            <>
                              <strong>
                                {image.display_name ??
                                  `${specimen.specimen_id}_${image.detector}`}
                              </strong>
                              {image.label_matches_image === false && (
                                <small className="label-corrected">
                                  {" "}
                                  · relabelled from{" "}
                                  {image.filename.replace(/^img_|\.tiff?$/gi, "")}
                                </small>
                              )}
                            </>
                          ) : (
                            image.filter
                          )}
                        </span>
                        <a
                          href={`${imageUrl}?download=true`}
                          download={image.filename}
                        >
                          Download TIFF
                        </a>
                      </figcaption>
                    </figure>
                  );
                })}
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

export default BatchList;
