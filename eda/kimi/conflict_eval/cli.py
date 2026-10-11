"""Command-line entry point: validate, preview, run, label, analyze."""

from __future__ import annotations

import argparse
import os
import random
import sys
from pathlib import Path

from dotenv import dotenv_values

from conflict_eval import analysis
from conflict_eval.design import STAGES, build_trials, make_design
from conflict_eval.models import API_KEY_ENV, load_model_configs, make_client
from conflict_eval.prompts import (
    DISTANCES,
    DOC_ORDERS,
    INSTRUCTION_LEVELS,
    MAX_RUNG,
    RULE_PLACEMENTS,
    VARIANTS,
    Condition,
    build_prompt,
)
from conflict_eval.runner import (
    FatalModelError,
    load_responses,
    read_manifest,
    run_trials,
    write_manifest,
)
from conflict_eval.scenarios import QUESTION_TYPES, load_filler, load_scenarios
from conflict_eval.scoring import alternative_label, append_label, load_labels, score_rows
from conflict_eval.validation import validate

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SCENARIOS = BASE_DIR / "data" / "scenarios.json"
DEFAULT_FILLER = BASE_DIR / "data" / "filler.json"
DEFAULT_MODELS = BASE_DIR / "config" / "models.toml"
RESULTS_DIR = BASE_DIR / "results"


def main(argv: list[str] | None = None) -> int:
    # Keys in .env win over ones exported in the shell; blank entries fall back to the shell.
    for key, value in dotenv_values(BASE_DIR / ".env").items():
        if value:
            os.environ[key] = value
    args = _parser().parse_args(argv)
    try:
        return args.handler(args)
    except (ValueError, FatalModelError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


def cmd_validate(args) -> int:
    scenarios, filler = load_scenarios(args.scenarios), load_filler(args.filler)
    report = validate(scenarios, filler)
    print(f"{len(scenarios)} scenarios, {len(filler)} filler passages\n")
    print(report.render())
    print("\nAutomatic checks only. Work through the by-hand checklist with `preview` before any run.")
    return 0 if report.ok else 1


def cmd_preview(args) -> int:
    scenarios = {s.id: s for s in load_scenarios(args.scenarios)}
    if args.scenario not in scenarios:
        raise ValueError(f"unknown scenario {args.scenario!r}; choose from {', '.join(scenarios)}")
    scenario = scenarios[args.scenario]
    order = args.order if scenario.format == "multi_document" else "forward"
    condition = Condition(args.variant, args.question, args.distance, args.rule, args.instruction, args.rung, order)
    prompt = build_prompt(scenario, condition, load_filler(args.filler))
    expected, alternative = scenario.expected_answers(args.question, args.variant)

    print(f"# {scenario.id} ({scenario.format}, {scenario.conflict_subtype})  {condition}\n")
    print(f"--- system ---\n{prompt.system}\n")
    for message in prompt.messages:
        print(f"--- {message['role']} ---\n{message['content']}\n")
    print(f"expected: {' | '.join(expected)}    alternative: {' | '.join(alternative)}")
    return 0


def cmd_run(args) -> int:
    scenarios = load_scenarios(args.scenarios)
    if args.only:
        unknown = set(args.only) - {s.id for s in scenarios}
        if unknown:
            raise ValueError(f"unknown scenario ids: {', '.join(sorted(unknown))}")
        scenarios = [s for s in scenarios if s.id in args.only]
    filler = load_filler(args.filler)
    report = validate(scenarios, filler)
    if not report.ok:
        print(report.render(), file=sys.stderr)
        raise ValueError("scenario validation failed; fix the errors above first")
    too_hard = [s.id for s in scenarios if s.max_rung < args.rung]
    if too_hard:
        raise ValueError(f"rung {args.rung} needs ladder fields missing from: {', '.join(too_hard)}")

    design = make_design(
        args.stage,
        args.rung,
        questions=tuple(args.question or ()),
        distances=tuple(args.distance or ()),
        rule_placements=tuple(args.rule or ()),
        generations=args.generations,
    )
    configs = load_model_configs(args.models_config)
    names = args.models or list(configs)
    unknown = set(names) - set(configs)
    if unknown:
        raise ValueError(f"models not in {args.models_config.name}: {', '.join(sorted(unknown))}")
    configs = {name: configs[name] for name in names}

    trials = build_trials(design, scenarios, names, args.seed)
    # Runs from another model config get their own folder, e.g. results/small_models/stage0_rung0.
    results = RESULTS_DIR if args.models_config == DEFAULT_MODELS else RESULTS_DIR / args.models_config.stem
    out = args.out or results / f"{design.stage}_rung{design.rung}"
    done = {row["trial_id"] for row in load_responses(out)}
    pending = sum(t.id not in done for t in trials)
    print(f"{design}\n{len(trials)} trials ({pending} still to run) -> {out}")
    if args.dry_run:
        example = trials[0]
        prompt = build_prompt(example.scenario, example.condition, filler)
        print(f"\nExample trial {example.id}:\n--- system ---\n{prompt.system}")
        print(f"--- last message ---\n{prompt.messages[-1]['content']}")
        return 0

    missing = sorted({API_KEY_ENV[c.provider] for c in configs.values()} - set(k for k in os.environ if os.environ[k]))
    if missing:
        raise ValueError(f"set {', '.join(missing)} in {BASE_DIR / '.env'} (see .env.example)")
    write_manifest(out, design, configs, args.scenarios, [s.id for s in scenarios], filler, args.seed)
    clients = {name: make_client(config) for name, config in configs.items()}
    summary = run_trials(trials, clients, filler, out, args.workers)
    print(f"ran {summary.attempted}: {summary.succeeded} ok, {summary.failed} errors, {summary.skipped} already done")
    if summary.failed:
        print("Rerun the same command to retry the errors.")
    print(f"Next: python -m conflict_eval label {out}  then  python -m conflict_eval analyze {out}")
    return 0


def cmd_label(args) -> int:
    run_dir = args.run_dir
    labels = load_labels(run_dir)
    scored = score_rows(load_responses(run_dir), labels)
    queue = [r for r in scored if (args.all and r["label_source"] != "hand") or r["label_source"] == "pending"]
    random.Random(0).shuffle(queue)  # mixes conditions so labelling is not done in condition blocks
    if not queue:
        print("Nothing to label.")
        return 0
    print(f"{len(queue)} responses to label. Model and condition are hidden on purpose.\n")
    keys = {"a": "correct", "n": "no_answer", "o": "other_error"}
    for i, row in enumerate(queue, 1):
        print(f"=== {i}/{len(queue)} ===\nQ: {row['question']}")
        print(f"  A (expected):     {' | '.join(row['expected'])}")
        print(f"  B (other option): {' | '.join(row['alternative'])}")
        if row["label_source"] == "auto":
            print(f"  auto label: {row['label']}")
        print(f"--- response ---\n{(row['response'] or '(empty)').strip()}\n----------------")
        while True:
            choice = input(
                "Which answer did it give?  [a] A  [b] B  [n] didn't commit to one  [o] something else"
                "   ([p] show prompt  [s] skip  [q] quit) > "
            ).strip().lower()
            if choice == "p":
                print(f"\n{row['system']}\n")
                for message in row["messages"]:
                    print(f"[{message['role']}] {message['content']}\n")
                continue
            if choice in ("a", "b", "n", "o", "s", "q"):
                break
        if choice == "q":
            break
        if choice == "s":
            continue
        label = alternative_label(row["variant"]) if choice == "b" else keys[choice]
        append_label(run_dir, row["trial_id"], label)
        print()
    remaining = sum(r["label_source"] == "pending" for r in score_rows(load_responses(run_dir), load_labels(run_dir)))
    print(f"Saved. {remaining} still pending.")
    return 0


def cmd_analyze(args) -> int:
    run_dir = args.run_dir
    rows = load_responses(run_dir)
    if not rows:
        raise ValueError(f"no responses in {run_dir}")
    df = analysis.to_frame(score_rows(rows, load_labels(run_dir)))
    text, tables = analysis.build_report(df, read_manifest(run_dir))
    print(text)

    (run_dir / "report.txt").write_text(text + "\n")
    df.drop(columns=["system", "messages"]).to_csv(run_dir / "scored.csv", index=False)
    for name, table in tables.items():
        table.to_csv(run_dir / f"{name}.csv", index=False)
    (run_dir / "failures.md").write_text(analysis.failures_markdown(df))
    saved = ["report.txt", "scored.csv", *(f"{n}.csv" for n in tables), "failures.md"]
    print(f"Saved to {run_dir}: {', '.join(saved)}")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m conflict_eval", description=__doc__)
    parser.add_argument("--scenarios", type=Path, default=DEFAULT_SCENARIOS)
    parser.add_argument("--filler", type=Path, default=DEFAULT_FILLER)
    commands = parser.add_subparsers(required=True, metavar="command")

    validate_cmd = commands.add_parser("validate", help="automatic scenario checks")
    validate_cmd.set_defaults(handler=cmd_validate)

    preview = commands.add_parser("preview", help="print the exact prompt for one scenario and condition")
    preview.add_argument("scenario")
    preview.add_argument("--variant", choices=VARIANTS, default="conflict")
    preview.add_argument("--question", choices=QUESTION_TYPES, default="two_step")
    preview.add_argument("--distance", choices=DISTANCES, default="far")
    preview.add_argument("--rule", choices=RULE_PLACEMENTS, default="start")
    preview.add_argument("--instruction", choices=INSTRUCTION_LEVELS, default="none")
    preview.add_argument("--rung", type=int, choices=range(MAX_RUNG + 1), default=0)
    preview.add_argument("--order", choices=DOC_ORDERS, default="forward")
    preview.set_defaults(handler=cmd_preview)

    run = commands.add_parser("run", help="run a stage against the models")
    run.add_argument("stage", choices=STAGES)
    run.add_argument("--rung", type=int, choices=range(MAX_RUNG + 1), default=0)
    run.add_argument("--question", nargs="+", choices=QUESTION_TYPES, help="override the stage's question types")
    run.add_argument("--distance", nargs="+", choices=DISTANCES, help="override the stage's distances")
    run.add_argument("--rule", nargs="+", choices=RULE_PLACEMENTS, help="override the stage's rule placements")
    run.add_argument("--generations", type=int, help="override generations per cell")
    run.add_argument("--models", nargs="+", help="model aliases from models.toml (default: all)")
    run.add_argument("--models-config", type=Path, default=DEFAULT_MODELS)
    run.add_argument("--only", nargs="+", metavar="ID", help="restrict to these scenario ids")
    run.add_argument("--seed", type=int, default=0, help="trial-order shuffle seed")
    run.add_argument("--workers", type=int, default=4, help="concurrent requests")
    run.add_argument("--out", type=Path, help="run directory (default: results/[<config>/]<stage>_rung<N>)")
    run.add_argument("--dry-run", action="store_true", help="build trials and show one prompt; no API calls")
    run.set_defaults(handler=cmd_run)

    label = commands.add_parser("label", help="hand-label responses the string match could not")
    label.add_argument("run_dir", type=Path)
    label.add_argument("--all", action="store_true", help="also review auto-labeled responses")
    label.set_defaults(handler=cmd_label)

    analyze = commands.add_parser("analyze", help="tables, hypotheses, and stage decision rules")
    analyze.add_argument("run_dir", type=Path)
    analyze.set_defaults(handler=cmd_analyze)
    return parser
