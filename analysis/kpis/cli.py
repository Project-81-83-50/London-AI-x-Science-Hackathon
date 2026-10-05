"""Command line: `python -m analysis.kpis [--batches 1 2 3] [--rebuild-fields]`."""

import argparse
import json
import logging
from datetime import UTC, datetime

from .. import configure_cli_logging
from .catalogue import HEADLINE
from .report import analyse_batch, output_dir

logger = logging.getLogger(__name__)


def main() -> None:
    ap = argparse.ArgumentParser(description="Detailed KPI report per reference battery batch.")
    ap.add_argument("--batches", nargs="+", default=["1", "2", "3"])
    ap.add_argument(
        "--rebuild-fields", action="store_true", help="re-match fields even if the cached field manifest is up to date"
    )
    args = ap.parse_args()
    configure_cli_logging()
    out = output_dir()
    # Merge into the existing summary so rerunning one batch keeps the others' headline KPIs.
    summary_path = out / "summary.json"
    previous = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else {}
    summary = {
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "batches": [b for b in previous.get("batches", []) if b["batch_id"] not in args.batches],
    }
    for batch in args.batches:
        report = analyse_batch(batch, args.rebuild_fields)
        kpis = {k["id"]: k for g in report["kpi_groups"] for k in g["kpis"]}
        summary["batches"].append(
            {
                "batch_id": report["batch_id"],
                "locations_analysed": report["inventory"]["locations_analysed"],
                "kpis": [
                    {
                        key: kpis[h][key]
                        for key in ("id", "name", "unit", "display_scale", "mean", "sd", "ci95", "n", "consistency")
                        if key in kpis[h]
                    }
                    for h in HEADLINE
                ],
            }
        )
    summary["batches"].sort(key=lambda b: int(b["batch_id"]))
    summary_path.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    logger.info("wrote reports to %s", out)
