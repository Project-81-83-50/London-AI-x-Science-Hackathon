import argparse
import json
from pathlib import Path

from ..paths import REPO_ROOT
from .config import ResearchError, store_path
from .facts import decode
from .jobs import ReportJobs
from .store import Store


def run_report(folder: Path, force: bool = False) -> dict:
    folder = Path(folder).resolve()
    if not (folder / "output/facts.json").is_file():
        raise ValueError("The run has no output/facts.json")
    return ReportJobs().start(folder, force=force, background=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Research-grounded SEM explanations with Corrective RAG")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("folder", type=Path)
    run.add_argument("--force", action="store_true")
    inspect = commands.add_parser("inspect")
    inspect.add_argument("facts", type=Path)
    commands.add_parser("prepare")
    commands.add_parser("sources")
    approve = commands.add_parser("admit")
    approve.add_argument("source_id")
    approve.add_argument("--exclude", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "run":
            result = run_report(args.folder, args.force)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            if result.get("status") not in {"done", "running"}:
                raise SystemExit(1)
        elif args.command == "inspect":
            print(decode(args.facts.read_text(encoding="utf-8-sig")).model_dump_json(indent=2))
        else:
            store = Store(store_path())
            try:
                store.seed(REPO_ROOT / "knowledge/SiC_SEM_reference_verified.json")
                if args.command == "prepare":
                    store.search("SEM graphite SiOx porosity detector contrast", set(), 30 * 86400)
                    print(
                        "Local BM25/latent semantic index prepared. Seed summaries remain discovery leads, not verified full text."
                    )
                elif args.command == "sources":
                    print(
                        json.dumps(
                            [
                                {k: v for k, v in s.model_dump().items() if k != "text"}
                                for s in store.sources().values()
                            ],
                            indent=2,
                        )
                    )
                else:
                    store.admit(args.source_id, not args.exclude)
                    print("Source admission updated. Corpus-versioned report caches are invalidated.")
            finally:
                store.close()
    except (ResearchError, ValueError) as exc:
        parser.exit(1, str(exc) + "\n")


if __name__ == "__main__":
    main()
