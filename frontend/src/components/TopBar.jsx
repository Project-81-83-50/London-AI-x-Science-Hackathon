export default function TopBar({}) {
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
      <div className="topbar-meta">
        <span className="service-indicator" />
        MICROSCOPY / IMAGE PROVENANCE
      </div>
      <span className="workspace-label">LONDON AI × SCIENCE</span>
    </header>
  );
}
