// Steps of a v3 run in order; `key` is the progress line the run prints when the step finishes
// (the agent report has none: it is started separately once the run is done).
export const PIPELINE_STEPS = [
  { id: "inputs", name: "Inputs + preprocessing", key: "read_preprocess_s" },
  { id: "seg", name: "U-Net segmentation", key: "segmentation_s" },
  { id: "feat", name: "Material features", key: "features_s" },
  { id: "dino", name: "DINOv2 texture", key: "dino_s" },
  { id: "mat", name: "Material model + evidence", key: "classify_explain_s" },
  { id: "known", name: "Known-spot check", key: "known_location_s" },
  { id: "get4", name: "GET4 sampling + range", key: "get4_range_rule_s" },
  { id: "kpi", name: "KPI model (ETD-dark solid)", key: "kpi_s" },
  { id: "dec", name: "Decision", key: "decision_s" },
  { id: "rep", name: "Agent report", key: null },
];
