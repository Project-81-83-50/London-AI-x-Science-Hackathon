"""Multi-agent explanation of one pipeline run (text only): analyst -> materials expert -> skeptic/writer.

Reads <run>/output/facts.json and writes <run>/output/report_status.json while working, then report.md and
report.json. Uses Claude Sonnet 5.5 at medium effort; the API key is read from sem_pipeline/.env
(ANTHROPIC_API_KEY). The literature knowledge base is read from the repository's knowledge/ folder.
Run by the backend (backend/app/routers/v3.py) as a subprocess:

    python -m website.agents <run folder>
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # sem_pipeline/
KNOWLEDGE = ROOT.parent / "knowledge" / "SiC_SEM_reference_verified.json"
MODEL = "claude-sonnet-5-5"
RULES = """Rules (binding):
- The input is a text-only facts file produced by the pipeline. Use only numbers that appear in it; never invent
  measurements, mechanisms, literature values or certainty.
- `decision` is the final answer. Its probability is 90 % the KPI model (`kpi_model`, the KPI classifier in analysis/classify.py: a
  measured material KPI such as ETD-dark solid, compared with the reference batches) + 10 % our v3 material model
  (`material_model`: U-Net segmentation + DINOv2, no fingerprint). There are two confidence levels: High when the
  KPI model is at least 50 % sure and the v3 material model picks the same batch; otherwise Low.
- `kpi_model` holds the KPI model's full evidence: `drivers` (the deciding KPI with its meaning and batch means),
  `all_kpis` (every KPI with its value, the batch means and how well it separates the batches), the nearest reference
  locations, how the image was measured, and the model's own reference validation.
- `kpi_model.session_hint` (image height = imaging session) is context only; it is NOT used by any model.
- Explain with material evidence only: the KPI value against the batch means, porosity, SiOx amount and
  distribution, where the DINOv2 evidence lies (map_text), and the composition's GET4 sampling intervals.
- Batch_1 and Batch_2 are NOT identical: they differ subtly. Whenever they are involved, use `batch_1_vs_batch_2` to
  explain HOW they differ (Batch_2: more porous, more open and hidden sub-surface pores, a more open pore network;
  Batch_1: slightly more and larger SiOx, lower SiOx-to-graphite brightness in BSE, rougher graphite texture in ETD)
  and where this location sits between them. Say that their ranges overlap, which makes single-location calls between
  them tricky, and flag differences marked may_reflect_imaging. Never call them indistinguishable.
- Composition: report pore / carbon / SiOx with their sampling intervals; the binder value is experimental.
- Track-record statistics for the combined method have not been recomputed. You may quote the KPI model's own
  reference validation (`kpi_model.reference_validation`), saying it is for the KPI model alone."""


def ask(client, system: str, user: str, max_tokens: int = 6000) -> str:
    """Send one streamed request and return the concatenated text blocks of the reply."""
    with client.messages.stream(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        thinking={"type": "adaptive"},
        output_config={"effort": "medium"},
        messages=[{"role": "user", "content": user}],
    ) as s:
        msg = s.get_final_message()
    return "".join(b.text for b in msg.content if b.type == "text").strip()


def knowledge_excerpt() -> str:
    """The knowledge-base sections relevant to microstructure, as JSON truncated to 60k characters."""
    if not KNOWLEDGE.exists():
        return "(knowledge base not found)"
    k = json.loads(KNOWLEDGE.read_text(encoding="utf-8"))
    return json.dumps(
        {x: k.get(x) for x in ("features", "properties", "imaging_modes", "artifacts")}, ensure_ascii=False
    )[:60000]


def number_check(report: str, facts_text: str) -> list[str]:
    """Numbers in the report that do not occur in facts.json (allowing % <-> fraction and rounding)."""
    pool = set()
    for v in re.findall(r"-?\d+(?:\.\d+)?", facts_text):
        x = abs(float(v))
        for y in (x, x * 100):
            for nd in (0, 1, 2, 3):
                pool.add(round(y, nd))
    unknown = []
    for v in re.findall(r"(?<![\w.])\d+(?:\.\d+)?", report.replace("−", "-")):
        nd = len(v.split(".")[1]) if "." in v else 0
        if round(float(v), nd) not in pool and float(v) not in (1, 2, 3) and v not in unknown:
            unknown.append(v)
    return unknown


def main(run: str) -> None:
    """Run the three agents on <run>/output/facts.json, reporting progress in report_status.json."""
    out = Path(run) / "output"
    status = out / "report_status.json"

    def stage(s, **extra):
        status.write_text(json.dumps({"status": "running", "stage": s, **extra}), encoding="utf-8")

    try:
        import anthropic
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
        client = anthropic.Anthropic(max_retries=4)
        facts_text = (out / "facts.json").read_text(encoding="utf-8")
        facts = json.loads(facts_text)
        stage("1/3 Evidence analyst is reading facts.json")
        analyst = ask(
            client,
            "You are the evidence analyst in a three-agent team explaining a batch-identification result "
            "for an SEM cross-section of a graphite + SiOx Li-ion anode.\n" + RULES,
            "facts.json:\n" + facts_text + "\n\nList the key findings strictly from this file, as bullet points: "
            "the decision, its probability (90 % KPI model + 10 % v3 material model) and confidence, the KPI model's "
            "evidence (the deciding KPI vs the batch means, other strongly separating KPIs from all_kpis, the "
            "nearest reference locations, its own reference validation), whether the v3 material model agrees, composition with sampling intervals, the material-model evidence and spatial "
            "description (map_text), the known-location and GET4 range checks, and every caveat. Quote numbers "
            "exactly. At most 300 words.",
        )
        stage("2/3 Materials expert is interpreting the microstructure")
        expert = ask(
            client,
            "You are the materials-science expert in the team. You interpret SEM microstructure of Si/C "
            "anodes using the team's literature knowledge base.\n" + RULES + "\n- Knowledge-base items are general "
            "literature guidance; cite them by id and never present them as measurements of this sample.",
            "Analyst's findings:\n"
            + analyst
            + "\n\nMeasured composition and maps (from facts.json):\n"
            + json.dumps(
                {"phases": facts["phases"], "map_text": facts["material_model"].get("map_text", {}).get("sentences")},
                ensure_ascii=False,
            )
            + "\n\nKnowledge base (excerpt):\n"
            + knowledge_excerpt()
            + "\n\nExplain in at most 250 words what this microstructure means for an anode (porosity, SiOx content "
            "and distribution, carbon/binder, sub-surface porosity seen as ETD-dark solid). Cite knowledge-base "
            "ids where relevant.",
        )
        stage("3/3 Skeptic is checking every claim and writing the report")
        final = ask(
            client,
            "You are the skeptic and final writer. You check every claim against facts.json, remove "
            "anything unsupported, and write the final report for a hackathon judge.\n" + RULES,
            "facts.json:\n"
            + facts_text
            + "\n\nAnalyst:\n"
            + analyst
            + "\n\nMaterials expert:\n"
            + expert
            + "\n\nWrite the final report in Markdown with these sections: ## Answer (one sentence: answer, "
            "confidence, probability), ## What the image shows, ## Why this batch (KPI evidence, and whether "
            "the material model agrees), ## Caveats, ## Verification notes (list any analyst or expert claim "
            "you removed and why; write 'none' if none). Every number must come from facts.json. At most 450 words.",
            max_tokens=8000,
        )
        (out / "report.md").write_text(final, encoding="utf-8")
        result = {
            "status": "done",
            "stage": "done",
            "markdown": final,
            "check": number_check(final, facts_text),
            "notes": {"analyst": analyst, "expert": expert},
            "model": MODEL,
        }
        (out / "report.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        status.write_text(json.dumps({"status": "done", "stage": "done"}), encoding="utf-8")
    except Exception as e:  # noqa: BLE001 - shown on the page
        status.write_text(json.dumps({"status": "error", "error": f"{type(e).__name__}: {e}"}), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1])
