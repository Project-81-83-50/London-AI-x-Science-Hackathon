import { useEffect, useState } from "react";
import "./App.css";

const API_URL = (
  import.meta.env.VITE_API_URL || "http://localhost:8000"
).replace(/\/$/, "");

function App() {
  const [batches, setBatches] = useState([]);
  const [selectedBatch, setSelectedBatch] = useState("");
  const [analysis, setAnalysis] = useState(null);
  const [error, setError] = useState("");
  const [loadingBatches, setLoadingBatches] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${API_URL}/batches`, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error(`API returned ${response.status}`);
        return response.json();
      })
      .then((result) => {
        setBatches(result);
        setSelectedBatch(result[0]?.batch_id || "");
        if (result.length === 0)
          setError("The API is running, but no batches are available yet.");
      })
      .catch((cause) => {
        if (cause.name !== "AbortError")
          setError(
            `Could not load batches. Check that the API is running at ${API_URL}.`,
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoadingBatches(false);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!selectedBatch) return undefined;
    const controller = new AbortController();
    fetch(`${API_URL}/batches/${encodeURIComponent(selectedBatch)}/analysis`, {
      signal: controller.signal,
    })
      .then((response) => {
        if (!response.ok) throw new Error(`API returned ${response.status}`);
        return response.json();
      })
      .then(setAnalysis)
      .catch((cause) => {
        if (cause.name !== "AbortError") {
          setAnalysis(null);
          setError(
            "Could not load this batch analysis. Check the API and try again.",
          );
        }
      });
    return () => controller.abort();
  }, [selectedBatch]);

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
          QUALITY CONTROL <span className="topbar-divider" /> ANALYSIS WORKSPACE
        </div>
        <span className="workspace-label">LONDON AI × SCIENCE</span>
      </header>

      <div className="content-wrap" id="overview">
        <section className="page-heading">
          <div>
            <p className="eyebrow">ELECTRON MICROSCOPY / BATCH REVIEW</p>
            <h1>Batch intelligence</h1>
            <p className="page-subtitle">
              Compare material properties against your established baseline.
            </p>
          </div>
          <label className="batch-picker">
            <span>SELECT BATCH</span>
            <select
              value={selectedBatch}
              onChange={(event) => {
                setError("");
                setSelectedBatch(event.target.value);
              }}
              disabled={loadingBatches || batches.length === 0}
            >
              {batches.length === 0 && (
                <option value="">No batches found</option>
              )}
              {batches.map((batch) => (
                <option key={batch.batch_id} value={batch.batch_id}>
                  {batch.batch_id}
                </option>
              ))}
            </select>
          </label>
        </section>

        {loadingBatches && (
          <div className="notice" role="status">
            Connecting to the analysis API…
          </div>
        )}
        {error && (
          <div className="notice notice-error" role="alert">
            {error}
          </div>
        )}
        {selectedBatch &&
          analysis?.batch_id !== selectedBatch &&
          !error &&
          !loadingBatches && (
            <div className="notice" role="status">
              Loading {selectedBatch} analysis…
            </div>
          )}

        {analysis && analysis.batch_id === selectedBatch && (
          <>
            <section className="section-block template-section">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">TODO: ADD A LABEL</p>
                  <h2>Batch summary</h2>
                </div>
              </div>
              {/* TODO: Choose which verdict information is useful, then design its presentation. */}
              <div className="template-slot">
                <span className="template-tag">YOUR COMPONENT</span>
                <p>Build your batch summary here.</p>
              </div>
            </section>

            <section className="section-block template-section">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">TODO: CHOOSE YOUR METRICS</p>
                  <h2>Measurements</h2>
                </div>
              </div>
              {/* TODO: Map analysis.kpis into the comparison or chart you want to build. */}
              <div className="template-slot">
                <span className="template-tag">YOUR COMPONENT</span>
                <p>Build your KPI view here.</p>
              </div>
            </section>

            <section className="section-block template-section">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">TODO: ADD INTERPRETATION</p>
                  <h2>Drivers and evidence</h2>
                </div>
              </div>
              {/* TODO: Decide how to present analysis.drivers and microscopy images. */}
              <div className="template-slot">
                <span className="template-tag">YOUR COMPONENT</span>
                <p>Build your interpretation view here.</p>
              </div>
            </section>
          </>
        )}
      </div>
      <footer className="footer">
        <span>EM QC / MATERIALS ANALYTICS</span>
        <span>LIVE API · {API_URL}</span>
      </footer>
    </main>
  );
}

export default App;
