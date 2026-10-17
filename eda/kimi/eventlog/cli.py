"""Command-line entry point for the v4 harness: validate, generate, run, analyze."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, replace
from pathlib import Path

from eventlog import analysis
from eventlog.checks import check_hand_logs, check_log
from eventlog.dials import CONFLICT_DIALS, LOWEST, SEEDS, STAGE_A_STEPS, Dials, dials_for, parse_overrides
from eventlog.generator import TRAP_TYPES, generate
from eventlog.prompts import INSTRUCTIONS, RESPONSE_FORMATS, build_prompt
from eventlog.runner import (
    estimate_cost,
    load_log_files,
    plan,
    run_jobs,
    save_logs,
)
from harness.calls import FatalModelError
from harness.models import API_KEY_ENV, load_env, load_model_configs, make_client
from harness.runs import load_responses, read_manifest, write_manifest

BASE_DIR = Path(__file__).resolve().parent.parent
HAND_LOGS = BASE_DIR / "data" / "v4" / "hand_logs.json"
DEFAULT_MODELS = BASE_DIR / "config" / "v4_models.toml"
RESULTS_DIR = BASE_DIR / "results" / "v4"
ASSUMED_OUTPUT_TOKENS = {"working": 5000, "final_only": 2000}  # includes hidden reasoning; Stage A means: Claude/Gemini ~4.9k, GPT ~0.8k


def main(argv: list[str] | None = None) -> int:
    load_env(BASE_DIR / ".env")
    args = _parser().parse_args(argv)
    try:
        return args.handler(args)
    except (ValueError, FatalModelError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


def cmd_validate(args) -> int:
    count, hand_problems = check_hand_logs(HAND_LOGS)
    print(f"Hand-written logs: resolver matches {count - len(hand_problems)} of {count} hand answers")
    for problem in hand_problems:
        print(f"  - {problem}")

    settings = [dials_for(step) for step in range(len(STAGE_A_STEPS))]
    settings += [replace(Dials(), **{dial: LOWEST[dial]}) for dial in CONFLICT_DIALS] + [replace(Dials(), n_projects=200)]
    bad = 0
    for dials in settings:
        for seed in range(1, args.seeds + 1):
            problems = check_log(generate(dials, seed))
            if problems:
                bad += 1
                print(f"  - {dials} seed {seed}: {'; '.join(problems[:3])}")
    print(f"Generated logs: {len(settings) * args.seeds} checked across {len(settings)} dial settings, {bad} with problems")
    biggest = generate(Dials(), 1).render("conflict")
    print(f"Maximum-setting log: ~{len(biggest) // 4:,} tokens")
    print("Step 3 of the validation is reading two full maximum-setting logs: python -m eventlog generate --seed 1 (and --seed 2)")
    return 0 if not hand_problems and not bad else 1


def cmd_generate(args) -> int:
    overrides = parse_overrides(args.set or [])
    log = generate(dials_for(args.step, overrides), args.seed)
    out = args.out or RESULTS_DIR / "samples" / f"{_label('step', args.step, overrides, 'working')}_seed{args.seed}"
    out.mkdir(parents=True, exist_ok=True)
    for version in ("conflict", "consistent"):
        (out / f"{version}.txt").write_text(f"{log.render(version)}\n\nQuestion: {log.question}\n")
    (out / "answer.json").write_text(json.dumps(log.metadata(), indent=1) + "\n")

    traps = [kind for p in log.projects for kind, _ in p.traps]
    print(f"{log.dials}\nseed {args.seed}: ~{len(log.render('conflict')) // 4:,} tokens, {len(log.events)} records")
    print(f"question: {log.question}\nanswer: {len(log.answer)} of {len(log.projects)} projects")
    print("traps: " + ", ".join(f"{kind} {traps.count(kind)}" for kind in TRAP_TYPES))
    problems = check_log(log)
    print("checks: " + ("all passed" if not problems else "; ".join(problems)))
    print(f"wrote {out}/conflict.txt, consistent.txt, answer.json")
    return 0 if not problems else 1


def cmd_run(args) -> int:
    overrides = parse_overrides(args.set or [])
    base = dials_for(args.step, overrides)
    configs = load_model_configs(args.models_config)
    names = args.models or list(configs)
    unknown = set(names) - set(configs)
    if unknown:
        raise ValueError(f"models not in {args.models_config.name}: {', '.join(sorted(unknown))}")
    configs = {name: configs[name] for name in names}

    jobs, logs = plan(args.stage, base, names, args.seed)
    results = RESULTS_DIR if args.models_config.resolve() == DEFAULT_MODELS else RESULTS_DIR / args.models_config.stem
    out = args.out or results / _label(args.stage, args.step, overrides, args.response_format)
    done = {row["job_id"] for row in load_responses(out)}
    pending = [j for j in jobs if j.id not in done]
    settings = sorted({j.setting for j in jobs})
    print(f"Stage {args.stage}, {base}\nsettings: {', '.join(settings)}  |  seeds: {SEEDS[args.stage]}")
    print(f"{len(jobs)} calls ({len(pending)} still to run) -> {out}")

    output_tokens = args.output_tokens or ASSUMED_OUTPUT_TOKENS[args.response_format]
    estimate = estimate_cost(pending, logs, configs, args.response_format, output_tokens)
    total = sum(row.get("usd", 0) for row in estimate)
    print(f"\nEstimated cost of the remaining calls ({output_tokens:,} output tokens assumed per call):")
    for row in estimate:
        usd = f"${row['usd']:.2f}" if "usd" in row else "no price in config"
        print(f"  {row['model']:14} {row['calls']:4} calls  {row['input_tokens']:>11,} in  {row['output_tokens']:>9,} out  {usd}")
    print(f"  total ~${total:.2f}")
    if args.dry_run:
        example = jobs[0]
        prompt = build_prompt(logs[example.log_id].render(example.version), logs[example.log_id].question, example.instruction, args.response_format)
        print(f"\nExample call {example.id}:\n--- system ---\n{prompt.system}\n--- user (last lines) ---")
        print("\n".join(prompt.messages[0]["content"].splitlines()[-4:]))
        return 0

    missing = sorted({API_KEY_ENV[c.provider] for c in configs.values()} - {k for k, v in os.environ.items() if v})
    if missing:
        raise ValueError(f"set {', '.join(missing)} in {BASE_DIR / '.env'}")
    write_manifest(out, {
        "stage": args.stage,
        "step": args.step,
        "overrides": overrides,
        "dials": asdict(base),
        "response_format": args.response_format,
        "models_config": _relative(args.models_config),
        "models": {name: asdict(config) for name, config in configs.items()},
        "seeds": list(SEEDS[args.stage]),
        "shuffle_seed": args.seed,
    }, created={"instructions": INSTRUCTIONS})
    save_logs(out, logs)
    clients = {name: make_client(config) for name, config in configs.items()}
    summary = run_jobs(jobs, load_log_files(out), clients, out, args.response_format, args.workers)
    print(
        f"ran {summary.attempted}: {summary.succeeded} ok ({summary.format_failures} format failures), "
        f"{summary.failed} errors, {summary.skipped} already done"
    )
    if summary.failed:
        print("Rerun the same command to retry the errors.")
    print(f"Next: python -m eventlog analyze {_relative(out)}")
    return 0


def cmd_analyze(args) -> int:
    rows = load_responses(args.run_dir)
    if not rows:
        raise ValueError(f"no responses in {args.run_dir}")
    df = analysis.score_frame(rows, load_log_files(args.run_dir))
    text, tables = analysis.build_report(df, read_manifest(args.run_dir))
    print(text)
    (args.run_dir / "report.txt").write_text(text + "\n")
    for name, table in tables.items():
        table.to_csv(args.run_dir / f"{name}.csv", index=False)
    print(f"Saved to {args.run_dir}: report.txt, {', '.join(f'{n}.csv' for n in tables)}")
    return 0


def _label(stage: str, step: int, overrides: dict, response_format: str) -> str:
    label = f"{stage}_step{step}" if stage != "step" else f"step{step}"
    label += "".join(f"_{k}-{v}" for k, v in overrides.items())
    return label + ("_final-only" if response_format == "final_only" else "")


def _relative(path: Path) -> str:
    path = Path(path).resolve()
    return str(path.relative_to(BASE_DIR)) if path.is_relative_to(BASE_DIR) else str(path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m eventlog", description=__doc__)
    commands = parser.add_subparsers(required=True, metavar="command")

    validate = commands.add_parser("validate", help="hand-written logs vs the resolver, and checks on generated logs")
    validate.add_argument("--seeds", type=int, default=5, help="generated logs to check per dial setting")
    validate.set_defaults(handler=cmd_validate)

    def dial_options(command):
        command.add_argument("--step", type=int, choices=range(len(STAGE_A_STEPS)), default=0,
                             help="general-dial step from Stage A rule 2 (0 = every dial at maximum)")
        command.add_argument("--set", nargs="+", metavar="DIAL=VALUE", help="override dials, e.g. n_projects=200")

    generate_cmd = commands.add_parser("generate", help="write one log pair to read end to end")
    dial_options(generate_cmd)
    generate_cmd.add_argument("--seed", type=int, default=1)
    generate_cmd.add_argument("--out", type=Path)
    generate_cmd.set_defaults(handler=cmd_generate)

    run = commands.add_parser("run", help="run a stage (A probe, B sweep + ablation, C skill test)")
    run.add_argument("stage", choices=("A", "B", "C"))
    dial_options(run)
    run.add_argument("--response-format", choices=RESPONSE_FORMATS, default="working")
    run.add_argument("--models", nargs="+", help="model aliases from the config (default: all)")
    run.add_argument("--models-config", type=Path, default=DEFAULT_MODELS)
    run.add_argument("--workers", type=int, default=6, help="concurrent requests")
    run.add_argument("--seed", type=int, default=0, help="call-order shuffle seed")
    run.add_argument("--output-tokens", type=int, help="assumed output tokens per call for the cost estimate")
    run.add_argument("--out", type=Path, help="run directory (default: results/v4/[<config>/]<stage>_step<N>...)")
    run.add_argument("--dry-run", action="store_true", help="plan, check, and estimate cost; no API calls")
    run.set_defaults(handler=cmd_run)

    analyze = commands.add_parser("analyze", help="measures, hypothesis tables, and the stage decision rule")
    analyze.add_argument("run_dir", type=Path)
    analyze.set_defaults(handler=cmd_analyze)
    return parser
