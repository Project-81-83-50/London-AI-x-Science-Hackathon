import { useState } from "react";
import { batchFolder, batchLabel } from "../../lib/batchLabel";

// Images tab: the batch's TIFF views grouped by location, with JPEG previews and original-TIFF downloads.
function ImageGallery({ apiUrl, selectedBatch, imageState, imageError, specimens, imageCount, sourceFolder }) {
  const [query, setQuery] = useState("");
  const [detector, setDetector] = useState("all");
  if (!selectedBatch) return null;
  const matched = specimens.length > 0 && specimens.every((s) => s.grouping === "matched");
  const folder = sourceFolder || batchFolder(selectedBatch);
  const detectors = [
    ...new Set(specimens.flatMap((s) => s.images.map((image) => (image.detector || image.filter).toUpperCase()))),
  ].sort();
  const search = query.trim().toLowerCase();
  const visible = specimens
    .map((specimen) => ({
      ...specimen,
      images: specimen.images.filter(
        (image) =>
          (detector === "all" || (image.detector || image.filter).toUpperCase() === detector) &&
          (specimen.specimen_id.toLowerCase().includes(search) ||
            image.filename.toLowerCase().includes(search) ||
            image.display_name?.toLowerCase().includes(search)),
      ),
    }))
    .filter((specimen) => specimen.images.length > 0);
  const visibleCount = visible.reduce((total, specimen) => total + specimen.images.length, 0);

  return (
    <section className="section-block" id="reference-images" aria-labelledby="reference-images-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">LOCAL DATA / {batchLabel(selectedBatch).toUpperCase()}</p>
          <h2 id="reference-images-title">{batchLabel(selectedBatch)} microscopy images</h2>
        </div>
        <span className="section-count">
          {imageState === "connected"
            ? `${specimens.length} ${matched ? "MATCHED GROUPS" : "FILENAME GROUPS"} · ${imageCount} TIFFS`
            : imageState === "loading"
              ? "LOADING IMAGE INVENTORY"
              : imageState === "error"
                ? "IMAGE INVENTORY UNAVAILABLE"
                : ""}
        </span>
      </div>
      {imageState === "loading" && (
        <div className="notice" role="status">
          Loading {batchLabel(selectedBatch)} image inventory…
        </div>
      )}
      {imageState === "error" && (
        <div className="notice notice-error" role="alert">
          Could not load {batchLabel(selectedBatch)} images ({imageError}). Check the API and confirm the files are in{" "}
          {folder}.
        </div>
      )}
      {imageState === "connected" && specimens.length === 0 && (
        <div className="notice">No supported TIFF images were found in {folder}.</div>
      )}
      {imageState === "connected" && specimens.length > 0 && (
        <div className="notice">
          {matched
            ? "Images are grouped by the location they show and labelled location_filter. Each label is checked against the image itself; a label that disagrees with the image is replaced and marked."
            : "These groups follow your filenames; cross-detector location matching has not been verified. Batch labels come from your folders. Run python -m analysis.fields if you need image-matched groups."}
        </div>
      )}
      {imageState === "connected" && specimens.length > 0 && (
        <>
          <p className="reference-folder">
            Reading from <code>{folder}</code>
          </p>
          <div className="reference-filters">
            <label>
              Search images
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Location code or filename"
              />
            </label>
            <label>
              Detector view
              <select aria-label="Detector view" value={detector} onChange={(event) => setDetector(event.target.value)}>
                <option value="all">All detectors</option>
                {detectors.map((name) => (
                  <option key={name} value={name}>
                    {name === "INLENS" ? "InLens" : name}
                  </option>
                ))}
              </select>
            </label>
            <span className="section-count" role="status">
              Showing {visibleCount} of {imageCount} views · {visible.length} groups
            </span>
          </div>
          {!visibleCount && (
            <p className="notice">
              No images match these filters.{" "}
              <button
                type="button"
                className="toggle-button"
                onClick={() => {
                  setQuery("");
                  setDetector("all");
                }}
              >
                Reset filters
              </button>
            </p>
          )}
        </>
      )}
      {imageState === "connected" && specimens.length > 0 && (
        <div className="specimen-grid">
          {visible.map((specimen) => (
            <article className="specimen-panel" key={specimen.specimen_id}>
              <div className="specimen-heading">
                <h3>
                  {matched ? "Location" : "Image group"} {specimen.specimen_id}
                </h3>
                <span
                  title={
                    specimen.location_alternatives?.length
                      ? `Codes that fit equally well: ${specimen.location_alternatives.join(", ")}`
                      : undefined
                  }
                >
                  {specimen.images.length} {specimen.images.length === 1 ? "view" : "views"}
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
                        aria-label={`Open enlarged preview of ${image.filename} from ${batchLabel(selectedBatch)}`}
                      >
                        <img
                          src={imageUrl}
                          alt={`${batchLabel(selectedBatch)} ${image.detector ?? image.filter} view, file ${image.filename}`}
                          loading="lazy"
                          decoding="async"
                        />
                      </a>
                      <figcaption>
                        <span>
                          {image.detector ? (
                            <>
                              <strong>{image.display_name ?? `${specimen.specimen_id}_${image.detector}`}</strong>
                              {image.label_matches_image === false && (
                                <small className="label-corrected">
                                  {" "}
                                  · relabelled from {image.filename.replace(/^img_|\.tiff?$/gi, "")}
                                </small>
                              )}
                            </>
                          ) : (
                            image.filter
                          )}
                        </span>
                        <a href={`${imageUrl}?download=true`} download={image.filename}>
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

export default ImageGallery;
