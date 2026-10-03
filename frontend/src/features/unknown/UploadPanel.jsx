import { useEffect, useRef, useState } from "react";
import "./UploadPanel.css";

// Upload new TIFFs into data/raw/unknown or delete existing ones, then re-run the unknown-batch analysis
// and refresh the views. Every file shows the batch its location was classified as.
// Files are checked here first (name and size) and again by the API (name, TIFF header, size, overwrite).
const NAME_PATTERN = /^img_[A-Za-z0-9]+_(BSE|ETD|Inlens|SE)\.tif$/;
const MAX_BYTES = 300 * 1024 * 1024;
const POLL_MS = 2000;

function checkFile(file) {
  if (!NAME_PATTERN.test(file.name))
    return "Name must look like img_<location>_<BSE|ETD|Inlens|SE>.tif";
  if (file.size > MAX_BYTES) return "Larger than 300 MB";
  if (file.size === 0) return "Empty file";
  return "";
}

function megabytes(bytes) {
  return `${(bytes / 2 ** 20).toFixed(1)} MB`;
}

function putFile(url, file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    xhr.upload.onprogress = (event) => event.lengthComputable && onProgress(event.loaded / event.total);
    xhr.onload = () => {
      let body = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        body = null;
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body);
      else reject(new Error(body?.detail || `Upload failed (${xhr.status})`));
    };
    xhr.onerror = () => reject(new Error("Network error while uploading"));
    xhr.send(file);
  });
}

// Current files grouped by location, with each location's classification (missing until analysed).
function useInventory(apiUrl, version) {
  const [inventory, setInventory] = useState({ groups: [], byFile: {}, byLocation: {} });
  useEffect(() => {
    let cancelled = false;
    Promise.all([
      fetch(`${apiUrl}/batches/unknown/images`).then((r) => (r.ok ? r.json() : [])),
      fetch(`${apiUrl}/unknown/classification`).then((r) => (r.ok ? r.json() : null)),
    ])
      .then(([groups, classification]) => {
        if (cancelled) return;
        const byLocation = Object.fromEntries((classification?.locations ?? []).map((l) => [l.location_id, l]));
        const byFile = {};
        for (const l of classification?.locations ?? []) for (const view of l.views) byFile[view] = l;
        setInventory({ groups: Array.isArray(groups) ? groups : [], byFile, byLocation });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [apiUrl, version]);
  return inventory;
}

function Verdict({ result }) {
  if (!result) return <span className="upload-verdict upload-verdict-none">not classified yet</span>;
  return (
    <span className={`upload-verdict upload-verdict-${result.confidence}`}>
      → Batch {result.predicted_batch} · {result.confidence}
      {result.prediction_source !== "material KPIs" ? " · reference match" : ""}
    </span>
  );
}

function UploadPanel({ apiUrl, onUploaded, onAnalysed }) {
  const [items, setItems] = useState([]);
  const [overwrite, setOverwrite] = useState(false);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [job, setJob] = useState(null);
  const [selected, setSelected] = useState(() => new Set());
  const [deleteError, setDeleteError] = useState("");
  const [inventoryVersion, setInventoryVersion] = useState(0);
  const inventory = useInventory(apiUrl, inventoryVersion);
  const refreshInventory = () => setInventoryVersion((v) => v + 1);
  const inputRef = useRef(null);
  const wasRunning = useRef(false);

  // Follow the analysis job: poll while it runs, refresh the batch views once it succeeds.
  useEffect(() => {
    let cancelled = false;
    let timer = 0;
    async function poll() {
      try {
        const response = await fetch(`${apiUrl}/unknown/analysis`);
        const state = await response.json();
        if (cancelled) return;
        setJob(state);
        if (state.state === "running") {
          wasRunning.current = true;
          timer = setTimeout(poll, POLL_MS);
        } else if (wasRunning.current) {
          wasRunning.current = false;
          setInventoryVersion((v) => v + 1);
          if (state.state === "done") onAnalysed();
        }
      } catch {
        if (!cancelled) timer = setTimeout(poll, POLL_MS * 2);
      }
    }
    poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
    // Re-subscribe when a new job is started (job.started changes).
  }, [apiUrl, job?.started, onAnalysed]);

  function addFiles(fileList) {
    const added = [...fileList].map((file) => {
      const problem = checkFile(file);
      return { file, name: file.name, status: problem ? "invalid" : "ready", message: problem, progress: 0 };
    });
    setItems((current) => {
      const names = new Set(added.map((a) => a.name));
      return [...current.filter((c) => !names.has(c.name)), ...added];
    });
  }

  function update(name, patch) {
    setItems((current) => current.map((item) => (item.name === name ? { ...item, ...patch } : item)));
  }

  async function startAnalysis() {
    const response = await fetch(`${apiUrl}/unknown/analysis`, { method: "POST" });
    const body = await response.json().catch(() => null);
    if (!response.ok) {
      setJob((current) => ({ ...(current ?? {}), state: "failed", log_tail: [body?.detail ?? "Could not start the analysis"] }));
      return;
    }
    wasRunning.current = true;
    setJob(body);
  }

  async function uploadAll() {
    setBusy(true);
    let uploaded = 0;
    for (const item of items.filter((i) => i.status === "ready" || i.status === "error")) {
      if (checkFile(item.file)) continue;
      update(item.name, { status: "uploading", progress: 0, message: "" });
      try {
        const url = `${apiUrl}/batches/unknown/images/${encodeURIComponent(item.name)}${overwrite ? "?overwrite=true" : ""}`;
        const result = await putFile(url, item.file, (p) => update(item.name, { progress: p }));
        update(item.name, { status: "done", progress: 1, message: result?.replaced ? "Replaced" : "Uploaded" });
        uploaded += 1;
      } catch (error) {
        update(item.name, { status: "error", message: error.message });
      }
    }
    setBusy(false);
    if (uploaded > 0) {
      onUploaded();
      refreshInventory();
      await startAnalysis();
    }
  }

  function toggle(name) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }

  async function deleteSelected() {
    const names = [...selected];
    if (!names.length) return;
    const message = `Delete ${names.length} image${names.length === 1 ? "" : "s"} from the unknown batch?\n\n${names.join("\n")}\n\nThis removes the files from data/raw/unknown and cannot be undone.`;
    if (!window.confirm(message)) return;
    setBusy(true);
    setDeleteError("");
    let remaining = null;
    const failed = [];
    for (const name of names) {
      try {
        const response = await fetch(`${apiUrl}/batches/unknown/images/${encodeURIComponent(name)}`, { method: "DELETE" });
        const body = await response.json().catch(() => null);
        if (!response.ok) throw new Error(body?.detail ?? `Delete failed (${response.status})`);
        remaining = body.remaining;
      } catch (error) {
        failed.push(`${name}: ${error.message}`);
      }
    }
    setSelected(new Set());
    setBusy(false);
    if (failed.length) setDeleteError(failed.join(" · "));
    if (remaining === null) return;
    onUploaded();
    refreshInventory();
    if (remaining > 0) await startAnalysis();
    else onAnalysed(); // nothing left to analyse; the API cleared the unknown batch's results
  }

  const ready = items.filter((i) => i.status === "ready" || i.status === "error").length;
  const running = job?.state === "running";
  const lastLine = job?.log_tail?.at(-1);

  return (
    <section className="kpi-card upload-panel" aria-labelledby="upload-title">
      <div className="kpi-card-heading">
        <h3 id="upload-title">Add images to the unknown batch</h3>
        <span className="kpi-card-note">
          {job ? `${job.images} images in data/raw/unknown` : "Checking the unknown batch…"}
        </span>
      </div>
      <p className="kpi-card-note">
        Name each file <code>img_&lt;location&gt;_&lt;BSE|ETD|Inlens|SE&gt;.tif</code>; views of one location
        share the location code. After uploading, the unknown batch is re-measured and re-classified
        (about 30 s per location), and every tab refreshes when it finishes.
      </p>

      <div
        className={`upload-drop ${dragging ? "upload-drop-active" : ""}`}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          addFiles(event.dataTransfer.files);
        }}
      >
        <p>Drop .tif files here, or</p>
        <button type="button" className="toggle-button" onClick={() => inputRef.current?.click()} disabled={busy}>
          Choose files
        </button>
        <input
          ref={inputRef}
          type="file"
          accept=".tif,image/tiff"
          multiple
          hidden
          onChange={(event) => {
            addFiles(event.target.files);
            event.target.value = "";
          }}
        />
      </div>

      {items.length > 0 && (
        <ul className="upload-list" aria-label="Files to upload">
          {items.map((item) => (
            <li key={item.name} className={`upload-item upload-${item.status}`}>
              <span className="upload-name">{item.name}</span>
              <span className="upload-size">{megabytes(item.file.size)}</span>
              <span className="upload-status">
                {item.status === "uploading"
                  ? `Uploading ${Math.round(item.progress * 100)}%`
                  : item.status === "ready"
                    ? "Ready"
                    : item.message}
              </span>
              {item.status === "done" && !running && <Verdict result={inventory.byFile[item.name]} />}
              {item.status === "uploading" && (
                <span className="upload-bar" style={{ width: `${Math.round(item.progress * 100)}%` }} />
              )}
            </li>
          ))}
        </ul>
      )}

      <div className="upload-actions">
        <label className="upload-overwrite">
          <input type="checkbox" checked={overwrite} onChange={(event) => setOverwrite(event.target.checked)} />
          Replace existing files with the same name
        </label>
        <button
          type="button"
          className="upload-primary"
          disabled={busy || running || ready === 0}
          onClick={uploadAll}
        >
          {busy ? "Uploading…" : `Upload ${ready || ""} file${ready === 1 ? "" : "s"} and analyse`}
        </button>
        {items.length > 0 && !busy && (
          <button type="button" className="toggle-button" onClick={() => setItems([])}>
            Clear list
          </button>
        )}
        <button type="button" className="toggle-button" disabled={busy || running} onClick={startAnalysis}>
          Re-run analysis
        </button>
      </div>

      {job && job.state !== "idle" && (
        <div className={`upload-job upload-job-${job.state}`} role="status" aria-live="polite">
          <strong>
            {running
              ? "Analysing the unknown batch…"
              : job.state === "done"
                ? `Analysis finished ${job.finished ? new Date(job.finished).toLocaleTimeString() : ""}`
                : "Analysis failed"}
          </strong>
          {running && lastLine && <span>{lastLine}</span>}
          {job.state === "failed" && (
            <pre className="upload-log">{(job.log_tail ?? []).join("\n")}</pre>
          )}
        </div>
      )}

      <div className="upload-manager">
        <div className="kpi-card-heading">
          <h3>Images in the unknown batch</h3>
          <button
            type="button"
            className="upload-delete"
            disabled={busy || running || selected.size === 0}
            onClick={deleteSelected}
          >
            Delete selected{selected.size ? ` (${selected.size})` : ""}
          </button>
        </div>
        {deleteError && <p className="upload-error-line">{deleteError}</p>}
        {inventory.groups.length === 0 ? (
          <p className="kpi-card-note">No images yet. Upload some above.</p>
        ) : (
          <ul className="upload-locations">
            {inventory.groups.map((group) => (
              <li key={group.specimen_id}>
                <div className="upload-location-head">
                  <strong>{group.specimen_id}</strong>
                  <Verdict result={inventory.byLocation[group.specimen_id]} />
                </div>
                <ul className="upload-files">
                  {group.images.map((image) => (
                    <li key={image.filename}>
                      <label>
                        <input
                          type="checkbox"
                          checked={selected.has(image.filename)}
                          disabled={busy || running}
                          onChange={() => toggle(image.filename)}
                        />
                        <span className="upload-name">{image.display_name ?? image.filename}</span>
                      </label>
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

export default UploadPanel;
