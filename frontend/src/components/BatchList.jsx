function BatchList({
  apiUrl,
  selectedBatch,
  imageState,
  imageError,
  specimens,
  imageCount,
}) {
  if (!selectedBatch) return null;

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
            ? `${specimens.length} SPECIMENS · ${imageCount} TIFFS`
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
        <div className="specimen-grid">
          {specimens.map((specimen) => (
            <article className="specimen-panel" key={specimen.specimen_id}>
              <div className="specimen-heading">
                <h3>Specimen {specimen.specimen_id}</h3>
                <span>
                  {specimen.images.length}{" "}
                  {specimen.images.length === 1 ? "view" : "views"}
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
                        aria-label={`Open enlarged ${image.filter} preview for batch ${selectedBatch} specimen ${specimen.specimen_id}`}
                      >
                        <img
                          src={imageUrl}
                          alt={`Batch ${selectedBatch} specimen ${specimen.specimen_id}, ${image.filter} filter`}
                          loading="lazy"
                          decoding="async"
                        />
                      </a>
                      <figcaption>
                        <span>{image.filter}</span>
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
