// App shell: hash routing between the batch workspace, the Demo page and the Pipeline page, plus the batch
// workspace itself (batch picker, per-batch view tabs and the API data-readiness line).
import { useEffect, useState } from "react";
import "./styles/App.css";
import BatchPicker from "./features/reference/BatchPicker";
import ImageGallery from "./features/reference/ImageGallery";
import PointNetwork from "./components/PointNetwork";
import Get4Results from "./features/uncertainty/Get4Results";
import GeneralReport from "./features/v3report/GeneralReport";
import DetailedReport from "./features/v3report/DetailedReport";
import Tabs from "./components/Tabs";
import { tabPanelProps } from "./lib/tabPanel";
import TopBar from "./components/TopBar";
import UnknownBatch from "./features/unknown/UnknownBatch";
import { UNKNOWN_BATCH, batchLabel, isUnknownBatch } from "./lib/batchLabel";
import DemoPage from "./features/v3live/DemoPage";
import PipelinePage from "./features/v3live/PipelinePage";
import V3UnknownCalls from "./features/v3live/V3UnknownCalls";

// Pages: the batch workspace (default), the v3 Demo and the v3 Pipeline view (#demo, #pipeline/<run>).
function routeFromHash() {
  const hash = window.location.hash.replace(/^#/, "");
  if (hash.startsWith("demo")) return { page: "demo", run: "" };
  if (hash.startsWith("pipeline")) return { page: "pipeline", run: hash.split("/")[1] || "" };
  return { page: "batches", run: "" };
}

// Vite reads VITE_ variables at build/start time; change this in frontend/.env.
const API_URL = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");

const allBatches = ["1", "2", "3", UNKNOWN_BATCH];
const supportedDetectors = ["BSE", "ETD", "INLENS", "SE", "TLD", "CBS"];
const referenceViews = [
  { id: "images", label: "Images" },
  { id: "general", label: "General report" },
  { id: "detailed", label: "Detailed report" },
  { id: "uncertainty", label: "Uncertainty (GET4)" },
];
// Reference batches show their images and reports; the unknown batch shows its images and the batch call for each
// location (Classification). New locations go through the Demo page.
const unknownViews = [
  { id: "images", label: "Images" },
  { id: "classification", label: "Classification" },
];

function App() {
  const [route, setRoute] = useState(routeFromHash);
  useEffect(() => {
    const onHash = () => {
      setRoute(routeFromHash());
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
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
  const [batchView, setBatchView] = useState("images");

  const availableDetectors = [
    ...new Set(referenceSpecimens.flatMap((specimen) => specimen.images.map((image) => image.filter.toUpperCase()))),
  ].filter((detector) => supportedDetectors.includes(detector));
  const analysisDetector = availableDetectors.includes(selectedDetector)
    ? selectedDetector
    : availableDetectors.includes("BSE")
      ? "BSE"
      : availableDetectors[0] || selectedDetector;

  // Health check for the data-readiness line at the bottom of the page.
  useEffect(() => {
    const controller = new AbortController();
    fetch(`${API_URL}/health`, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error(`API returned ${response.status}`);
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
        if (!Array.isArray(result)) throw new Error("The API returned an unexpected image inventory.");
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
          throw new Error(body?.detail || `Analysis API returned ${response.status}`);
        }
        return response.json();
      })
      .then((result) => {
        if (!result || typeof result !== "object" || !Array.isArray(result.images)) {
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

  const views = isUnknownBatch(selectedReferenceBatch) ? unknownViews : referenceViews;
  const activeView = views.some((v) => v.id === batchView) ? batchView : "images";

  const referenceImageCount = referenceSpecimens.reduce((count, specimen) => count + specimen.images.length, 0);

  function selectDetector(detector) {
    setSelectedDetector(detector);
    setUncertaintyReport(null);
    setUncertaintyError("");
    setUncertaintyState("loading");
  }

  return (
    <main className="app-shell">
      <PointNetwork />
      <TopBar page={route.page} />

      {route.page === "demo" && <DemoPage apiUrl={API_URL} />}
      {route.page === "pipeline" && <PipelinePage apiUrl={API_URL} run={route.run} />}
      {route.page === "batches" && (
        <div className="content-wrap" id="overview">
          <section className="page-heading">
            <div>
              <p className="eyebrow">ELECTRON MICROSCOPY / BATCH ORGANISATION</p>
              <h1>Trace each image to its source</h1>
              <p className="page-subtitle">
                Learn the three known battery batches, then assign each location in the unknown batch to its closest
                reference, with evidence.
              </p>
            </div>
          </section>

          <ol className="workflow" aria-label="Analysis workflow">
            <li className="workflow-step">
              <span className="workflow-number">01</span>
              <span>
                <strong>Build the references</strong> · compare views within each known batch
              </span>
            </li>
            <li className="workflow-step">
              <span className="workflow-number">02</span>
              <span>
                <strong>Classify the unknown batch</strong> · assign each location to batch 1, 2 or 3
              </span>
            </li>
            <li className="workflow-step">
              <span className="workflow-number">03</span>
              <span>
                <strong>Explain every match</strong> · evidence and uncertainty for each call
              </span>
            </li>
          </ol>

          <section className="section-block" aria-labelledby="reference-title">
            <div className="section-heading">
              <div>
                <p className="eyebrow">REFERENCE LIBRARY · UNKNOWN SET</p>
                <h2 id="reference-title">Batches</h2>
              </div>
              <span className="section-count">3 REFERENCE SETS + UNKNOWN</span>
            </div>
            <BatchPicker
              batches={allBatches}
              selectedBatch={selectedReferenceBatch}
              imageState={referenceImageState}
              specimens={referenceSpecimens}
              imageCount={referenceImageCount}
              onSelect={selectReferenceBatch}
            />
            {!selectedReferenceBatch && (
              <p className="picker-hint">
                Select a reference batch to see its images and analysis reports, or Unknown to classify and inspect the
                unknown images. To test a new location, use the Demo page.
              </p>
            )}
            {selectedReferenceBatch && (
              <div className="batch-views">
                <Tabs
                  tabs={views.map((view) =>
                    view.id === "images" && referenceImageState === "connected"
                      ? { ...view, badge: referenceImageCount }
                      : view,
                  )}
                  active={activeView}
                  onChange={setBatchView}
                  label={`${batchLabel(selectedReferenceBatch)} views`}
                  idPrefix="batch-view"
                />
                <div {...tabPanelProps("batch-view", activeView)}>
                  {activeView === "images" && (
                    <ImageGallery
                      apiUrl={API_URL}
                      selectedBatch={selectedReferenceBatch}
                      imageState={referenceImageState}
                      imageError={referenceImageError}
                      specimens={referenceSpecimens}
                      imageCount={referenceImageCount}
                    />
                  )}
                  {activeView === "general" && (
                    <GeneralReport
                      key={`general-${selectedReferenceBatch}`}
                      apiUrl={API_URL}
                      batch={selectedReferenceBatch}
                    />
                  )}
                  {activeView === "detailed" && (
                    <DetailedReport
                      key={`detailed-${selectedReferenceBatch}`}
                      apiUrl={API_URL}
                      batch={selectedReferenceBatch}
                    />
                  )}
                  {activeView === "classification" && (
                    <>
                      <V3UnknownCalls apiUrl={API_URL} />
                      <UnknownBatch apiUrl={API_URL} />
                    </>
                  )}
                  {activeView === "uncertainty" && (
                    <>
                      <div className="get4-controls">
                        <label htmlFor="get4-detector">
                          Analysis filter
                          <select
                            id="get4-detector"
                            value={analysisDetector}
                            onChange={(event) => selectDetector(event.target.value)}
                          >
                            {(availableDetectors.length > 0 ? availableDetectors : [selectedDetector]).map(
                              (detector) => (
                                <option value={detector} key={detector}>
                                  {detector}
                                </option>
                              ),
                            )}
                          </select>
                        </label>
                        <span>
                          Reports are analysed per filter. Views from one location are not counted as separate locations
                          across filters.
                        </span>
                      </div>
                      {analysisDetector === "BSE" && (
                        <p className="notice">
                          These phases are brightness classes: "pore" counts only the BSE-dark (deep) pores, and
                          grey-floored open pores fall into "graphite". For the four-phase machine-learning segmentation
                          (pore, graphite, SiOx, binder) see the General report.
                        </p>
                      )}
                      <Get4Results
                        key={`${selectedReferenceBatch}-${analysisDetector}`}
                        report={uncertaintyReport}
                        batchLabel={batchLabel(selectedReferenceBatch)}
                        title="GET4 uncertainty results"
                        loading={uncertaintyState === "loading"}
                        error={uncertaintyState === "error" ? uncertaintyError : ""}
                      />
                    </>
                  )}
                </div>
              </div>
            )}
          </section>

          <details className={`data-notice ${apiState === "error" ? "data-notice-error" : ""}`} aria-live="polite">
            <summary className="data-notice-heading">
              <span className="data-notice-indicator" />
              <strong>Data readiness</strong>
              <span>
                {apiState === "loading"
                  ? "checking the local API…"
                  : apiState === "error"
                    ? `API unreachable (${apiError})`
                    : "API connected"}
              </span>
              <span className="api-address">{API_URL}</span>
            </summary>
            {apiState === "error" && <p>Start the backend to load the batch images and reports.</p>}
            {apiState === "connected" && (
              <p>
                {selectedReferenceBatch
                  ? `Batch ${selectedReferenceBatch} image inventory: ${
                      referenceImageState === "connected"
                        ? `${referenceImageCount} TIFFs across ${referenceSpecimens.length} groups.`
                        : referenceImageState === "error"
                          ? `unavailable (${referenceImageError}).`
                          : "loading."
                    }`
                  : "Select a reference batch to load its images."}
              </p>
            )}
          </details>

          <p className="integrity-note">
            Reference images load only after selecting a batch. No image classifications are inferred; matching needs
            analysis evidence.
          </p>
        </div>
      )}

      <footer className="footer">
        <span>EM QC / IMAGE PROVENANCE WORKSPACE</span>
        <span>REFERENCE SETS 1–3 · UNKNOWN SET</span>
      </footer>
    </main>
  );
}

export default App;
