#!/usr/bin/env python3
"""Generate, check, collect, and analyze Experiment 3 through ChatGPT-signed-in Codex."""
import argparse
import json
from pathlib import Path
import sys

import collection
import planning


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    models = commands.add_parser("models", help="List locally advertised models/efforts; no model calls")
    models.add_argument("--catalog", type=Path)
    check = commands.add_parser("check", help="Check CLI and ChatGPT login without a model call")
    check.add_argument("--codex-bin")
    prepare = commands.add_parser("prepare", help="Freeze a dataset and randomized schedule; no model calls")
    prepare.add_argument("--stage", choices=["smoke", "development", "confirmation"], required=True)
    prepare.add_argument("--run", type=Path, required=True)
    prepare.add_argument("--config", type=Path, default=planning.ROOT / "config.json")
    prepare.add_argument("--catalog", type=Path)
    prepare.add_argument("--development-reviewed", action="store_true")
    prepare.add_argument("--allow-estimated-tokens", action="store_true")
    collect = commands.add_parser("collect", help="Run a bounded batch; resume the same directory later")
    collect.add_argument("--run", type=Path, required=True)
    collect.add_argument("--max-new-trials", type=int, required=True)
    collect.add_argument("--models", nargs="+")
    collect.add_argument("--efforts", nargs="+")
    collect.add_argument("--retry-errors", action="store_true")
    collect.add_argument("--codex-bin")
    analyze = commands.add_parser("analyze", help="Rebuild scores and token tables from saved attempts")
    analyze.add_argument("--run", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "models":
            catalog = planning.load_catalog(args.catalog)
            print(f"Cached catalog: {catalog['fetched_at']} | CLI: {catalog['client_version']}")
            for model in catalog["models"]:
                if model["visibility"] != "hide":
                    print(f"{model['model']}: {', '.join(model['efforts'])}")
            print('Reasoning off means "none". Low effort is not off. Catalog entries do not guarantee live access.')
        elif args.command == "check":
            print(json.dumps(collection.preflight(args.codex_bin), indent=2))
            print("Checks passed. No model request sent.")
        elif args.command == "prepare":
            config = json.loads(args.config.read_text())
            result = planning.prepare(args.run, config, args.stage, planning.load_catalog(args.catalog),
                                      args.allow_estimated_tokens, args.development_reviewed)
            print(f"Prepared {result['planned_trials']} trials in {args.run.resolve()}")
            for skipped in result["unsupported_combinations"]:
                print(f"Skipped {skipped['model']} / {skipped['effort']}: {skipped['reason']}")
            print("No model requests sent. Review manifest.json and validation.json before collecting.")
        elif args.command == "collect":
            count = collection.collect(args.run, args.max_new_trials, args.codex_bin, args.models, args.efforts, args.retry_errors)
            print(f"Saved {count} new attempts. Results: {args.run.resolve()}")
        else:
            print(json.dumps(collection.analyze(args.run), indent=2))
    except (ValueError, OSError, KeyError, ImportError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
