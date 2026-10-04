import "../features/v3live/v3live.css";
const PAGES = [
  { id: "batches", href: "#overview", label: "1 · Batches" },
  { id: "demo", href: "#demo", label: "2 · Demo" },
  { id: "pipeline", href: "#pipeline", label: "3 · Pipeline" },
];

export default function TopBar({ page = "batches" }) {
  return (
    <header className="topbar">
      <a className="brand" href="#overview" aria-label="EM QC overview">
        <span className="brand-mark" aria-hidden="true">
          EM
        </span>
        <span>
          MICRO<span className="brand-light">SCOPE</span>
        </span>
      </a>
      <nav className="v3-nav" aria-label="Pages">
        {PAGES.map((p) => (
          <a key={p.id} href={p.href} className={page === p.id ? "v3-nav-on" : ""}>{p.label}</a>
        ))}
      </nav>
      <div className="topbar-meta">
        <span className="service-indicator" />
        MICROSCOPY / IMAGE PROVENANCE
      </div>
      <span className="workspace-label">LONDON AI × SCIENCE</span>
    </header>
  );
}
