// ARIA props for the panel controlled by a <Tabs> row with the same idPrefix.
export function tabPanelProps(idPrefix, activeId) {
  return {
    id: `${idPrefix}-panel`,
    role: "tabpanel",
    "aria-labelledby": `${idPrefix}-tab-${activeId}`,
  };
}
