import { useEffect, useState } from "react";
import "./App.css";
import Batch from "./components/Batch";
import Get4Results from "./components/Get4Results";
import KpiReport from "./components/KpiReport";
import LucasReport from "./components/LucasReport";
import TopBar from "./components/TopBar";

// Vite reads VITE_ variables at build/start time; change this in frontend/.env.
const API_URL = (
  import.meta.env.VITE_API_URL || "http://localhost:8000"
).replace(/\/$/, "");

const referenceBatches = ["1", "2", "3"];
const incomingBatches = ["4", "5"];
const supportedDetectors = ["BSE", "ETD", "INLENS", "SE", "TLD", "CBS"];

function App() {
  const [apiRecords, setApiRecords] = useState([]);
  const [apiState, setApiState] = useState("loading");
  const [apiError, setApiError] = useState("");
  const [selectedReferenceBatch, setSelectedReferenceBatch] = useState("");
  const [referenceSpecimens, setReferenceSpecimens] = useState([]);
  const [referenceImageState, setReferenceImageState] = useState("idle");
  const [referenceImageError, setReferenceImageError] = useState("");
  const [selectedDetector, setSelectedDetector] = useState("BSE");
  const [uncertaintyReport, setUncertaintyReport] = useState(null);
  const [uncertaintyState, setUncertaintyState] = useState("idle");
  const [uncertaintyError, setUncertaintyError] = useState("");

  const availableDetectors = [
    ...new Set(
      referenceSpecimens.flatMap((specimen) =>
        specimen.images.map((image) => image.filter.toUpperCase()),
      ),
    ),
  ].filter((detector) => supportedDetectors.includes(detector));
  const analysisDetector = availableDetectors.includes(selectedDetector)
    ? selectedDetector
    : availableDetectors.includes("BSE")
      ? "BSE"
      : availableDetectors[0] || selectedDetector;

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

  useEffect(() => {
    if (!selectedReferenceBatch) return undefined;
    const controller = new AbortController();
    fetch(`${API_URL}/batches/${selectedReferenceBatch}/images`, {
      signal: controller.signal,
    })
      .then((response) => {
        if (!response.ok) throw new Error(`API returned ${response.status}`);
        return response.json();
      })
      .then((result) => {
        if (!Array.isArray(result))
          throw new Error("The API returned an unexpected image inventory.");
        setReferenceSpecimens(result);
        setReferenceImageState("connected");
      })
      .catch((cause) => {
        if (cause.name !== "AbortError") {
          setReferenceImageError(cause.message);
          setReferenceImageState("error");
        }
      });
    return () => controller.abort();
  }, [selectedReferenceBatch]);

  useEffect(() => {
    if (!selectedReferenceBatch) return undefined;

    const controller = new AbortController();
    fetch(
      `${API_URL}/batches/${selectedReferenceBatch}/analysis-report?detector=${encodeURIComponent(analysisDetector)}`,
      { signal: controller.signal },
    )
      .then(async (response) => {
        if (!response.ok) {
          const body = await response.json().catch(() => null);
          throw new Error(
            body?.detail || `Analysis API returned ${response.status}`,
          );
        }
        return response.json();
      })
      .then((result) => {
        if (
          !result ||
          typeof result !== "object" ||
          !Array.isArray(result.images)
        ) {
          throw new Error("The API returned an unexpected GET4 report.");
        }
        setUncertaintyReport(result);
        setUncertaintyState("connected");
      })
      .catch((cause) => {
        if (cause.name !== "AbortError") {
          setUncertaintyError(cause.message);
          setUncertaintyState("error");
        }
      });
    return () => controller.abort();
  }, [selectedReferenceBatch, analysisDetector]);

  function selectReferenceBatch(batch) {
    if (selectedReferenceBatch === batch) {
      setSelectedReferenceBatch("");
      setReferenceSpecimens([]);
      setReferenceImageError("");
      setReferenceImageState("idle");
      setUncertaintyReport(null);
      setUncertaintyError("");
      setUncertaintyState("idle");
      return;
    }
    setReferenceSpecimens([]);
    setReferenceImageError("");
    setReferenceImageState("loading");
    setUncertaintyReport(null);
    setUncertaintyError("");
    setUncertaintyState("loading");
    setSelectedReferenceBatch(batch);
  }

  const referenceImageCount = referenceSpecimens.reduce(
    (count, specimen) => count + specimen.images.length,
    0,
  );

  function selectDetector(detector) {
    setSelectedDetector(detector);
    setUncertaintyReport(null);
    setUncertaintyError("");
    setUncertaintyState("loading");
  }

  return (
    <main className="app-shell">
      <TopBar />

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
          <Batch
            apiUrl={API_URL}
            batches={referenceBatches}
            selectedBatch={selectedReferenceBatch}
            imageState={referenceImageState}
            imageError={referenceImageError}
            specimens={referenceSpecimens}
            imageCount={referenceImageCount}
            onSelect={selectReferenceBatch}
          />
          {selectedReferenceBatch && (
            <>
              <KpiReport
                key={selectedReferenceBatch}
                apiUrl={API_URL}
                batch={selectedReferenceBatch}
              />
              <LucasReport
                key={`lucas-${selectedReferenceBatch}`}
                apiUrl={API_URL}
                batch={selectedReferenceBatch}
              />
              <div className="get4-controls">
                <label htmlFor="get4-detector">
                  Analysis filter
                  <select
                    id="get4-detector"
                    value={analysisDetector}
                    onChange={(event) => selectDetector(event.target.value)}
                  >
                    {(availableDetectors.length > 0
                      ? availableDetectors
                      : [selectedDetector]
                    ).map((detector) => (
                      <option value={detector} key={detector}>
                        {detector}
                      </option>
                    ))}
                  </select>
                </label>
                <span>
                  Reports are analysed per filter. Views from one location are
                  not counted as separate locations across filters.
                </span>
              </div>
              <Get4Results
                key={`${selectedReferenceBatch}-${analysisDetector}`}
                report={uncertaintyReport}
                batchLabel={`Batch ${selectedReferenceBatch}`}
                title="GET4 uncertainty results"
                loading={uncertaintyState === "loading"}
                error={
                  uncertaintyState === "error" ? uncertaintyError : ""
                }
              />
            </>
          )}
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
              <article className="batch-card incoming-card" key={batch}>
                <div className="batch-card-top">
                  <span className="batch-index">INCOMING / BATCH {batch}</span>
                  <span className="data-state data-state-pending">
                    NOT RECEIVED
                  </span>
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
                {selectedReferenceBatch
                  ? ` Batch ${selectedReferenceBatch} image inventory: ${
                      referenceImageState === "connected"
                        ? `${referenceImageCount} TIFFs across ${referenceSpecimens.length} groups.`
                        : referenceImageState === "error"
                          ? `unavailable (${referenceImageError}).`
                          : "loading."
                    }`
                  : " Select a reference batch to load its images."}
              </p>
              {apiRecords.length > 0 && (
                <ul
                  className="api-record-list"
                  aria-label="Available API records"
                >
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
          Reference images load only after selecting a batch. No image
          classifications are inferred; matching needs analysis evidence.
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
