import { useEffect, useState } from "react";
import "./App.css";

// Vite reads VITE_ variables at build/start time; change this in frontend/.env.
const API_URL = (
  import.meta.env.VITE_API_URL || "http://localhost:8000"
).replace(/\/$/, "");

const referenceBatches = ["1", "2", "3"];
const incomingBatches = ["4", "5"];

function App() {
  const [apiRecords, setApiRecords] = useState([]);
  const [apiState, setApiState] = useState("loading");
  const [apiError, setApiError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${API_URL}/batches`, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error(`API returned ${response.status}`);
        return response.json();
      })
      .then((result) => {
        if (!Array.isArray(result))
          throw new Error("The API returned an unexpected batch list.");
        setApiRecords(result);
        setApiState("connected");
      })
      .catch((cause) => {
        if (cause.name !== "AbortError") {
          setApiError(cause.message);
          setApiState("error");
        }
      });
    return () => controller.abort();
  }, []);

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="#overview" aria-label="EM QC overview">
          <span className="brand-mark" aria-hidden="true">
            EM
          </span>
          <span>
            MICRO<span className="brand-light">SCOPE</span>
          </span>
        </a>
        <div className="topbar-meta">
          <span className="service-indicator" />
          MICROSCOPY / IMAGE PROVENANCE
        </div>
        <span className="workspace-label">LONDON AI × SCIENCE</span>
      </header>

      <div className="content-wrap" id="overview">
        <section className="page-heading">
          <div>
            <p className="eyebrow">ELECTRON MICROSCOPY / BATCH ORGANISATION</p>
            <h1>Trace each image to its source</h1>
            <p className="page-subtitle">
              Learn the three known battery batches, then sort the images in
              mixed batches 4 and 5 with evidence.
            </p>
          </div>
        </section>

        <section className="workflow" aria-label="Analysis workflow">
          <article className="workflow-step">
            <span className="workflow-number">01</span>
            <div>
              <h2>Build the references</h2>
              <p>Compare views within each known batch.</p>
            </div>
          </article>
          <article className="workflow-step">
            <span className="workflow-number">02</span>
            <div>
              <h2>Sort the mixed images</h2>
              <p>Match each view in batches 4 and 5 to batches 1–3.</p>
            </div>
          </article>
          <article className="workflow-step">
            <span className="workflow-number">03</span>
            <div>
              <h2>Explain every match</h2>
              <p>Show the visual evidence and uncertainty behind each group.</p>
            </div>
          </article>
        </section>

        <section className="section-block" aria-labelledby="reference-title">
          <div className="section-heading">
            <div>
              <p className="eyebrow">KNOWN MATERIAL / REFERENCE LIBRARY</p>
              <h2 id="reference-title">Reference batches</h2>
            </div>
            <span className="section-count">3 EXPECTED SETS</span>
          </div>
          <div className="batch-grid batch-grid-three">
            {referenceBatches.map((batch) => (
              <article className="batch-card" key={batch}>
                <div className="batch-card-top">
                  <span className="batch-index">REFERENCE {batch}</span>
                  <span className="data-state">AWAITING IMAGES</span>
                </div>
                <h3>Batch {batch}</h3>
                <p>
                  Add the views for this known battery batch. Angles and
                  imaging filters should be compared as evidence, not treated
                  as separate materials.
                </p>
                <div className="batch-card-foot">
                  <span>Image set</span>
                  <strong>Not connected</strong>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="section-block" aria-labelledby="incoming-title">
          <div className="section-heading">
            <div>
              <p className="eyebrow">UNSEEN MATERIAL / MIXED IMAGE SETS</p>
              <h2 id="incoming-title">Incoming batches to organise</h2>
            </div>
            <span className="section-count">SOURCE: BATCHES 1–3</span>
          </div>
          <div className="batch-grid batch-grid-two">
            {incomingBatches.map((batch) => (
              <article
                className="batch-card incoming-card"
                key={batch}
              >
                <div className="batch-card-top">
                  <span className="batch-index">INCOMING / BATCH {batch}</span>
                  <span className="data-state data-state-pending">NOT RECEIVED</span>
                </div>
                <h3>Batch {batch}</h3>
                <p>
                  Images will be grouped by the reference batch they most
                  resemble. Each assignment should include a reason and a
                  confidence level.
                </p>
                <div className="match-placeholder">
                  <span>Image groups and match evidence will appear here.</span>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section
          className={`data-notice ${apiState === "error" ? "data-notice-error" : ""}`}
          aria-live="polite"
        >
          <div className="data-notice-heading">
            <span className="data-notice-indicator" />
            <h2>Data readiness</h2>
            <span className="api-address">{API_URL}</span>
          </div>
          {apiState === "loading" && (
            <p>Checking the local API for available batch records…</p>
          )}
          {apiState === "error" && (
            <p>
              Could not reach the batch API ({apiError}). Start the backend to
              check available records.
            </p>
          )}
          {apiState === "connected" && (
            <>
              <p>
                API connected · {apiRecords.length} analysis{" "}
                {apiRecords.length === 1 ? "record" : "records"} available.
                This API currently provides batch summaries, not microscopy
                image inventories or image-to-reference matches.
              </p>
              {apiRecords.length > 0 && (
                <ul className="api-record-list" aria-label="Available API records">
                  {apiRecords.map((record) => (
                    <li key={record.batch_id}>
                      <code>{record.batch_id}</code>
                      <span>Analysis metadata only</span>
                    </li>
                  ))}
                </ul>
              )}
              {apiRecords.length === 0 && (
                <p className="api-empty">
                  The API is running, but it has no batch records yet.
                </p>
              )}
            </>
          )}
        </section>

        <p className="integrity-note">
          No image classifications are shown until image files and reference
          data are available. Batch IDs alone are not enough to infer a match.
        </p>
      </div>

      <footer className="footer">
        <span>EM QC / IMAGE PROVENANCE WORKSPACE</span>
        <span>REFERENCE SETS 1–3 · MIXED SETS 4–5</span>
      </footer>
    </main>
  );
}

export default App;
