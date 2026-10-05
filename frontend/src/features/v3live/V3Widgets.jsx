// Presentational pieces shared by the v3 live pages (unknown-batch calls, Demo, Pipeline): batch-probability
// bars, composition bar, confidence tier, plain table and a minimal Markdown renderer for the agent report.
import { V3_BATCHES, humanize, percent } from "../../lib/v3format";
import "./v3live.css";

export function ProbBars({ probabilities, highlight }) {
  return (
    <div className="v3-probs">
      {V3_BATCHES.map((b) => (
        <div className="v3-prob" key={b}>
          <span className="v3-prob-label">{humanize(b)}</span>
          <span className="v3-prob-track">
            <span
              className={`v3-prob-fill ${b === highlight ? "v3-prob-top" : ""}`}
              style={{ width: `${(probabilities?.[b] ?? 0) * 100}%` }}
            />
          </span>
          <span className="v3-prob-value">{percent(probabilities?.[b], 1)}</span>
        </div>
      ))}
    </div>
  );
}

export function CompositionBar({ pore, carbon, siox }) {
  return (
    <div className="v3-comp" title={`pore ${pore}% · carbon ${carbon}% · SiOx ${siox}%`}>
      <span className="v3-comp-pore" style={{ width: `${pore}%` }} />
      <span className="v3-comp-carbon" style={{ width: `${carbon}%` }} />
      <span className="v3-comp-siox" style={{ width: `${siox}%` }} />
    </div>
  );
}

export function Tier({ value }) {
  return <span className={`v3-tier v3-tier-${String(value).split(" ")[0]}`}>{value}</span>;
}

export function Table({ head, rows }) {
  return (
    <table className="v3live-table">
      <thead>
        <tr>
          {head.map((h) => (
            <th key={h}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>
            {r.map((c, j) => (
              <td key={j}>{c}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// Minimal Markdown for the agent report: headings, bullet lists, bold/italic/code, pipe tables, paragraphs.
function inline(text) {
  const parts = [];
  const re = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g;
  let last = 0;
  for (const m of text.matchAll(re)) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const t = m[0];
    if (t.startsWith("**")) parts.push(<b key={m.index}>{t.slice(2, -2)}</b>);
    else if (t.startsWith("`")) parts.push(<code key={m.index}>{t.slice(1, -1)}</code>);
    else parts.push(<i key={m.index}>{t.slice(1, -1)}</i>);
    last = m.index + t.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

export function Markdown({ text }) {
  const blocks = [];
  let list = null;
  let table = null;
  const flush = () => {
    if (list)
      blocks.push(
        <ul key={blocks.length}>
          {list.map((l, i) => (
            <li key={i}>{inline(l)}</li>
          ))}
        </ul>,
      );
    if (table) {
      const rows = table
        .filter((r) => !/^\|?\s*:?-{2,}/.test(r))
        .map((r) =>
          r
            .replace(/^\||\|$/g, "")
            .split("|")
            .map((c) => c.trim()),
        );
      if (rows.length)
        blocks.push(<Table key={blocks.length} head={rows[0]} rows={rows.slice(1).map((r) => r.map(inline))} />);
    }
    list = null;
    table = null;
  };
  for (const line of String(text ?? "").split("\n")) {
    if (/^\s*\|/.test(line)) {
      if (list) flush();
      (table ??= []).push(line.trim());
      continue;
    }
    if (/^\s*[-*] /.test(line)) {
      if (table) flush();
      (list ??= []).push(line.replace(/^\s*[-*] /, ""));
      continue;
    }
    flush();
    if (/^#{1,6} /.test(line)) blocks.push(<h4 key={blocks.length}>{inline(line.replace(/^#+ /, ""))}</h4>);
    else if (line.trim()) blocks.push(<p key={blocks.length}>{inline(line)}</p>);
  }
  flush();
  return <div className="v3-markdown">{blocks}</div>;
}
