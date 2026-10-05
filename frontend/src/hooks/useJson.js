// Fetch JSON from the API: { status: "loading" | "ready" | "error", data, error }; aborts on unmount.
// A null url fetches nothing (status stays "idle"), for data that does not apply.
import { useEffect, useState } from "react";

export function useJson(url) {
  const [state, setState] = useState({ status: url ? "loading" : "idle", data: null, error: "" });
  useEffect(() => {
    if (!url) return undefined;
    const controller = new AbortController();
    fetch(url, { signal: controller.signal })
      .then(async (response) => {
        const body = await response.json().catch(() => null);
        if (!response.ok) throw new Error(body?.detail || `API returned ${response.status}`);
        return body;
      })
      .then((data) => setState({ status: "ready", data, error: "" }))
      .catch((cause) => {
        if (cause.name !== "AbortError") setState({ status: "error", data: null, error: cause.message });
      });
    return () => controller.abort();
  }, [url]);
  return state;
}
