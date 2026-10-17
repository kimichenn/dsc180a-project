"""Command-line entry point for the v5 harness: validate, preview, check-models, run, analyze."""

from __future__ import annotations

import argparse
import os
import statistics
import sys
import time
from dataclasses import asdict
from pathlib import Path

from chain import analysis
from chain.checks import check_chain, check_hand_chains, summary
from chain.dials import BREAK_LEVELS, PROFILES
from chain.generator import generate
from chain.prompts import INSTRUCTIONS, build_prompt, system_prompt
from chain.resolver import LURES, flipped
from chain.runner import (
    BUDGET_USD,
    billed,
    estimate,
    load_chain_files,
    plan,
    run_jobs,
    save_chains,
    seeds_for,
    spent_usd,
)
from chain.scoring import parse_answer
from harness.calls import FatalModelError
from harness.models import API_KEY_ENV, load_env, load_model_configs, make_client
from harness.runs import CHARS_PER_TOKEN, load_responses, read_manifest, token_counts, write_manifest

BASE_DIR = Path(__file__).resolve().parent.parent
HAND_CHAINS = BASE_DIR / "data" / "v5" / "hand_chains.json"
DEFAULT_MODELS = BASE_DIR / "config" / "v5_models.toml"
RESULTS_DIR = BASE_DIR / "results" / "v5"
# Assumed output per call for the expected cost, hidden reasoning included (v4 Stage A: Claude/Gemini ~4.9k).
ASSUMED_OUTPUT_TOKENS = {"working": 5000, "final_only": 2000}
VALIDATE_LEVELS = (20, 200, 800)
# P3 changes only the response format, so its chains are P2's.
VALIDATE_PROFILES = ("P0", "P1", "P2")
# The worked example from the v5 plan (answer 810), for check-models.
CHECK_LOG = """POLICY
Only the Finance Office can change a project's budget. Messages from anyone else do not change it.
The Finance Office can withdraw one of its earlier updates. A withdrawn update counts as if it never happened; every other update still applies, in order. A withdrawal can itself be withdrawn.

RECORDS
#001  2025-09-02  Finance Office: Kavel budget set to $800K.
#002  2025-09-03  Engineering email: Kavel budget is going up to $950K.
#003  2025-09-05  Finance Office: Kavel budget increased by $40K.
#004  2025-09-08  Finance Office: Kavel budget decreased by $15K.
#005  2025-09-09  Finance Office: Withdraw update #003.
#006  2025-09-11  Finance Office: Kavel budget increased by $25K."""


def main(argv: list[str] | None = None) -> int:
    load_env(BASE_DIR / ".env")
    args = _parser().parse_args(argv)
    try:
        return args.handler(args)
    except (ValueError, FatalModelError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


def cmd_validate(args) -> int:
    count, hand_problems, pending = check_hand_chains(HAND_CHAINS)
    filled = count - len(pending)
    print(f"Hand chains: resolver matches {filled - len(hand_problems)} of {filled} hand answers; {len(pending)} of {count} still blank")
    for problem in hand_problems:
        print(f"  - {problem}")
    if pending:
        print(f"  PENDING (work these out by hand, then fill in 'expected' in {HAND_CHAINS.relative_to(BASE_DIR)}): {', '.join(pending)}")

    bad = 0
    print(f"\nGenerated chains ({args.seeds} seeds for P0, {max(1, args.seeds // 10)} for the others):")
    print(f"  {'profile':7} {'N':>4} {'chains':>6} {'bad':>4} {'attempts':>8} {'consequential':>13} {'after last set':>14} {'control length':>14} {'max chars':>9} {'secs':>5}")
    for name in VALIDATE_PROFILES:
        seeds = args.seeds if name == "P0" else max(1, args.seeds // 10)
        for n in VALIDATE_LEVELS:
            started = time.monotonic()
            stats, problems = [], 0
            try:
                for seed in range(1, seeds + 1):
                    chain = generate(n, PROFILES[name], seed)
                    found = check_chain(chain)
                    if found:
                        problems += 1
                        print(f"  - {name} N={n} seed {seed}: {'; '.join(found[:3])}")
                    stats.append((chain.attempts, summary(chain)))
            except ValueError as error:
                print(f"  {name:7} {n:>4} skipped: {error}")
                continue
            except RuntimeError as error:
                bad += 1
                print(f"  - {name} N={n}: {error}")
                continue
            bad += problems
            attempts = statistics.mean(a for a, _ in stats)
            cons = statistics.median(s["consequential"] for _, s in stats)
            tail = statistics.median(s["after_last_set"] for _, s in stats)
            gap = statistics.mean(s["length_gap"] for _, s in stats)
            chars = max(s["chars"] for _, s in stats)
            print(f"  {name:7} {n:>4} {len(stats):>6} {problems:>4} {attempts:>8.2f} {cons:>13.0f} {tail:>14.0f} {gap:>+13.1%} {chars:>9,} {time.monotonic() - started:>5.1f}")
    print("  (medians per chain for the question's project; control length is control vs conflict characters)")
    print("\nRead one chain by hand: python -m chain preview --seed 1 --n 30")
    return 0 if not hand_problems and not pending and not bad else 1


def cmd_preview(args) -> int:
    profile = PROFILES[args.profile]
    chain = generate(args.n, profile, args.seed)
    for version in ("conflict", "control"):
        print(f"===== {version.upper()} =====\n{chain.render(version)}\n\nQuestion: {chain.question}\n")

    print("===== ANSWER KEY =====")
    print(f"{args.profile} {profile}")
    print(f"seed {args.seed}, N={args.n}, project {chain.project}, {chain.attempts} generator attempt(s)")
    print(f"answer: {chain.answer}")
    for version in ("conflict", "control"):
        lures = chain.lures(version)
        print(f"lures ({version}): " + " | ".join(f"{name} {lures[name]}" for name in LURES))
    print(f"\ntrace for {chain.project} (* = flipping this record alone changes the answer):")
    for line in _trace(chain):
        print(f"  {line}")
    s = summary(chain)
    print(
        f"\n{s['records']} records about {chain.project}: {s['consequential']} consequential, "
        f"{s['after_last_set']} after the last active set, {s['nested']} withdrawals of withdrawals; "
        f"control is {s['length_gap']:+.1%} the length of conflict ({s['chars']:,} characters)"
    )
    problems = check_chain(chain)
    print("checks: " + ("all passed" if not problems else "; ".join(problems)))
    return 0 if not problems else 1


def cmd_check_models(args) -> int:
    """One small call per model: right answer, no tools, the requested model, and little added context."""
    configs = load_model_configs(args.models_config)
    names = args.models or list(configs)
    prompt = build_prompt(CHECK_LOG, "What is Kavel's budget now?", "none")
    chars = len(prompt.system) + len(prompt.messages[0]["content"])
    bad = 0
    for name in names:
        config = configs[name]
        try:
            client = make_client(config)
            started = time.monotonic()
            completion = client.generate(prompt)
        except Exception as error:
            bad += 1
            print(f"{name:13} FAILED  {type(error).__name__}: {error}")
            continue
        value = parse_answer(completion.text)
        tokens_in, tokens_out = token_counts(completion.usage)
        tools = completion.usage.get("tool_calls", 0)
        problems = [p for p, failed in (("wrong answer", value != 810), ("used a tool", tools), ("other model", completion.model_version not in (None, config.model))) if failed]
        bad += bool(problems)
        print(
            f"{name:13} {'ok    ' if not problems else 'CHECK '} answer {value}  tools {tools}  served {completion.model_version or config.model}  "
            f"input {tokens_in:,} tokens (prompt alone ~{chars / CHARS_PER_TOKEN[config.provider]:,.0f})  output {tokens_out:,}  "
            f"{time.monotonic() - started:.0f}s  {getattr(client, 'version', '') or config.provider}" + (f"  <- {', '.join(problems)}" if problems else "")
        )
    return 0 if not bad else 1


def cmd_run(args) -> int:
    profile = PROFILES[args.profile]
    levels = args.levels or (list(BREAK_LEVELS) if args.phase == "break" else None)
    if not levels:
        raise ValueError("sweep needs --levels (analyze on the break run prints them)")
    configs = load_model_configs(args.models_config)
    names = args.models or list(configs)
    unknown = set(names) - set(configs)
    if unknown:
        raise ValueError(f"models not in {args.models_config.name}: {', '.join(sorted(unknown))}")
    configs = {name: configs[name] for name in names}

    p = plan(args.phase, profile, levels, configs, shuffle_seed=args.seed)
    results = RESULTS_DIR if args.models_config.resolve() == DEFAULT_MODELS else RESULTS_DIR / args.models_config.stem
    out = args.out or results / f"{args.phase}_{args.profile}"
    done = {row["job_id"] for row in load_responses(out)}
    pending = [j for j in p.jobs if j.id not in done]
    seeds = seeds_for(args.phase)
    print(f"{args.phase} phase, {args.profile} {profile}")
    print(f"N levels: {', '.join(map(str, levels))}  |  seeds: {seeds[0]}-{seeds[-1]}  |  versions: conflict, control")
    print(f"{len(p.jobs)} calls ({len(pending)} still to run) -> {_relative(out)}")
    for reason in p.skipped:
        print(f"  skipped {reason}")

    output_tokens = args.output_tokens or ASSUMED_OUTPUT_TOKENS[profile.response_format]
    rows = estimate(pending, p.prompt_chars, configs, output_tokens)
    print(f"\nRemaining calls ({output_tokens:,} output tokens per call assumed for the expected cost):")
    for row in rows:
        config = configs[row["model"]]
        cost = f"${row['expected_usd']:.2f} expected, ${row['worst_usd']:.2f} at most" if row["billed"] else f"$0 ({config.provider} subscription)"
        print(f"  {row['model']:13} {config.model:24} {row['calls']:4} calls  {row['input_tokens']:>10,} prompt tokens  {cost}")
    expected = sum(row["expected_usd"] for row in rows)
    worst = sum(row["worst_usd"] for row in rows)
    spent = spent_usd(RESULTS_DIR)
    left = args.max_usd - spent
    print(f"\nAPI budget: ${spent:.2f} of ${args.max_usd:.2f} spent across results/v5, ${left:.2f} left.")
    print(f"These calls: ~${expected:.2f} expected, ${worst:.2f} if every billed call hit its output limit and needed a rerun.")
    if worst > left:
        print("The runner reserves each API call's worst case before starting it, so it stops starting API calls before the budget runs out.")
    fits = expected <= left
    if not fits:
        print(f"Expected cost is over the ${left:.2f} left: drop models with --models, or raise --max-usd.")
    if args.dry_run:
        example = p.jobs[0]
        chain = p.chains[example.chain_id]
        prompt = build_prompt(chain.render(example.version), chain.question, example.instruction, profile.response_format)
        print(f"\nExample call {example.id}:\n--- system ---\n{prompt.system}\n--- user (first and last lines) ---")
        lines = prompt.messages[0]["content"].splitlines()
        print("\n".join(lines[:8] + ["..."] + lines[-3:]))
        return 0
    if not fits:
        return 1

    missing = sorted({API_KEY_ENV[c.provider] for c in configs.values() if billed(c)} - {k for k, v in os.environ.items() if v})
    if missing:
        raise ValueError(f"set {', '.join(missing)} in {BASE_DIR / '.env'}")
    clients = {name: make_client(config) for name, config in configs.items()}  # checks each CLI and its login
    write_manifest(out, {
        "phase": args.phase,
        "profile_name": args.profile,
        "profile": asdict(profile),
        "levels": levels,
        "seeds": list(seeds),
        "models_config": _relative(args.models_config),
        "models": {name: asdict(config) for name, config in configs.items()},
        "system_prompt": system_prompt("none", profile.response_format),
        "shuffle_seed": args.seed,
    }, created={"instructions": INSTRUCTIONS})
    save_chains(out, p.chains)
    summary_ = run_jobs(p.jobs, load_chain_files(out), clients, p.prompt_chars, out, left, args.workers)
    print(
        f"ran {summary_.attempted - summary_.over_budget}: {summary_.succeeded} ok ({summary_.format_failures} format failures, "
        f"{summary_.tool_calls} used a tool), {summary_.failed} errors, {summary_.already_done} already done; "
        f"API spend this session ${summary_.spent_usd:.2f}"
    )
    if summary_.over_budget:
        print(f"{summary_.over_budget} API calls not started: they would have gone over the ${args.max_usd:.2f} budget.")
    for model, error in summary_.stopped.items():
        print(f"stopped {model}: {error}")
    if summary_.failed or summary_.stopped:
        print("Rerun the same command to retry the errors.")
    print(f"Next: python -m chain analyze {_relative(out)}")
    return 0


def cmd_analyze(args) -> int:
    rows = load_responses(args.run_dir)
    if not rows:
        raise ValueError(f"no responses in {args.run_dir}")
    chain_files = load_chain_files(args.run_dir)
    manifest = read_manifest(args.run_dir)
    df = analysis.score_frame(rows, chain_files)
    text, results = analysis.build_report(df, manifest, chain_files)
    print(text)
    run_dir = args.run_dir
    (run_dir / "report.txt").write_text(text + "\n")
    df.to_csv(run_dir / "scored.csv", index=False)
    results["errors"].to_csv(run_dir / "errors.csv", index=False)
    (run_dir / "failures.md").write_text(analysis.failures_markdown(df, chain_files, {r["job_id"]: r for r in rows}))
    analysis.plot(results["acc"], results["points"], manifest, run_dir / "accuracy_vs_n.png")
    print(f"Saved to {_relative(run_dir)}: report.txt, accuracy_vs_n.png, errors.csv, scored.csv, failures.md")
    return 0


def _relative(path: Path) -> str:
    path = Path(path).resolve()
    return str(path.relative_to(BASE_DIR)) if path.is_relative_to(BASE_DIR) else str(path)


def _trace(chain) -> list[str]:
    records = chain.records("conflict")
    withdrawn_by = {r.target: r.id for r in records if r.op == "withdraw"}
    width = chain.id_width
    value, lines = None, []
    for r in records:
        if r.entity != chain.project:
            continue
        flag = "*" if chain.consequential[r.id] else " "
        if r.op in ("set", "adjust"):
            label = f"set {r.amount}" if r.op == "set" else f"adjust {r.amount:+d}"
            if chain.active[r.id]:
                value = r.amount if r.op == "set" else value + r.amount
                status = f"-> {value}"
            else:
                status = f"withdrawn by #{withdrawn_by[r.id]:0{width}d}; if applied: {flipped(records, chain.project, r.id)}"
        elif r.op == "withdraw":
            label = f"withdraw #{r.target:0{width}d}"
            if chain.active[r.id]:
                status = f"applies; if ignored: {flipped(records, chain.project, r.id)}"
            else:
                status = f"withdrawn by #{withdrawn_by[r.id]:0{width}d}; if applied: {flipped(records, chain.project, r.id)}"
        elif r.op == "note":
            label = f"note {r.amount:+d}" if r.relative else f"note {r.amount}"
            status = f"ignored ({r.author}); if official: {flipped(records, chain.project, r.id)}"
        else:
            label, status = "neutral", ""
        lines.append(f"#{r.id:0{width}d} {flag} {label:<16} {status}".rstrip())
    return lines


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m chain", description=__doc__)
    commands = parser.add_subparsers(required=True, metavar="command")

    validate = commands.add_parser("validate", help="hand chains vs the resolver, then the generator checks on many seeds")
    validate.add_argument("--seeds", type=int, default=1000, help="seeds per N for P0 (a tenth of this for P1 and P2)")
    validate.set_defaults(handler=cmd_validate)

    preview = commands.add_parser("preview", help="print both versions of one chain, its answer, and its lures")
    preview.add_argument("--seed", type=int, default=1)
    preview.add_argument("--n", type=int, default=30)
    preview.add_argument("--profile", choices=PROFILES, default="P0")
    preview.set_defaults(handler=cmd_preview)

    check = commands.add_parser("check-models", help="one small call per model to confirm each login and the isolation")
    check.add_argument("--models", nargs="+", help="model aliases from the config (default: all)")
    check.add_argument("--models-config", type=Path, default=DEFAULT_MODELS)
    check.set_defaults(handler=cmd_check_models)

    run = commands.add_parser("run", help="run a phase: break (find each model's break point) or sweep (the result)")
    run.add_argument("phase", choices=("break", "sweep"))
    run.add_argument("--profile", choices=PROFILES, default="P0")
    run.add_argument("--levels", type=int, nargs="+", help=f"N levels (break default: {' '.join(map(str, BREAK_LEVELS))}; sweep: required)")
    run.add_argument("--models", nargs="+", help="model aliases from the config (default: all)")
    run.add_argument("--models-config", type=Path, default=DEFAULT_MODELS)
    run.add_argument("--workers", type=int, default=4, help="concurrent calls")
    run.add_argument("--seed", type=int, default=0, help="call-order shuffle seed")
    run.add_argument("--output-tokens", type=int, help="assumed output tokens per call for the expected cost")
    run.add_argument("--max-usd", type=float, default=BUDGET_USD, help="API spend cap across every run under results/v5")
    run.add_argument("--out", type=Path, help="run directory (default: results/v5/[<config>/]<phase>_<profile>)")
    run.add_argument("--dry-run", action="store_true", help="plan and estimate cost; no calls")
    run.set_defaults(handler=cmd_run)

    analyze = commands.add_parser("analyze", help="tables, the accuracy-vs-N figure, break points, and the decision rule")
    analyze.add_argument("run_dir", type=Path)
    analyze.set_defaults(handler=cmd_analyze)
    return parser
