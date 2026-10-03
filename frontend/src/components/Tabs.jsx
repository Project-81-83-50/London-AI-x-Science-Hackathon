import "./Tabs.css";

// Accessible tab buttons: one is selected, arrow keys / Home / End move between them.
// The caller renders the matching panel with tabPanelProps(idPrefix, activeId) from tabPanel.js.
function Tabs({ tabs, active, onChange, label, idPrefix, size = "md" }) {
  function onKeyDown(event) {
    const index = tabs.findIndex((t) => t.id === active);
    const last = tabs.length - 1;
    const next = { ArrowRight: index + 1, ArrowLeft: index - 1, Home: 0, End: last }[event.key];
    if (next === undefined) return;
    event.preventDefault();
    const target = tabs[(next + tabs.length) % tabs.length];
    onChange(target.id);
    document.getElementById(`${idPrefix}-tab-${target.id}`)?.focus();
  }

  return (
    <div className={`tabs tabs-${size}`} role="tablist" aria-label={label} onKeyDown={onKeyDown}>
      {tabs.map((tab) => {
        const selected = tab.id === active;
        return (
          <button
            key={tab.id}
            id={`${idPrefix}-tab-${tab.id}`}
            type="button"
            role="tab"
            aria-selected={selected}
            aria-controls={`${idPrefix}-panel`}
            tabIndex={selected ? 0 : -1}
            className={`tab ${selected ? "tab-selected" : ""}`}
            onClick={() => onChange(tab.id)}
          >
            <span>{tab.label}</span>
            {tab.badge !== undefined && <span className="tab-badge">{tab.badge}</span>}
          </button>
        );
      })}
    </div>
  );
}

export default Tabs;
