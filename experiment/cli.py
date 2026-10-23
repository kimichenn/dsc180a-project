"""Command line for the budget-ledger experiment. Run `python -m experiment --help` from the repository root."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path

from experiment import runs, text
from experiment.checks import check_hand_logs, check_world
from experiment.clients import ClientError, make_client
from experiment.collect import collect, pending
from experiment.config import GeneratorSettings, load_config
from experiment.generator import generate
from experiment.prompts import Prompt, system_prompt, user_prompt
from experiment.records import VERSIONS
from experiment.scoring import MISTAKES, hit_length_limit, score
from experiment.world import World

ROOT = runs.REPO_ROOT
HAND_LOGS = ROOT / "data" / "hand_logs.json"
DEFAULT_CONFIG = ROOT / "config" / "trial.toml"


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return args.handler(args)
    except (ValueError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


def cmd_validate(args) -> int:
    cases, problems = check_hand_logs(HAND_LOGS)
    unchecked = [c["name"] for c in cases if not c.get("checked_by")]
    print(f"Hand logs ({_relative(HAND_LOGS)}): both solvers match {len(cases) - len(problems)} of {len(cases)} hand-worked answers")
    for problem in problems:
        print(f"  - {problem}")
    if unchecked:
        print(f"  {len(unchecked)} not yet checked by a person: work each out from its lines, then put your name in checked_by")

    settings = load_config(args.config).generator if args.config else GeneratorSettings()
    print(f"\nGenerated worlds ({_relative(args.config) if args.config else 'default generator settings'}), {args.seeds} seeds per size:")
    print(f"  {'records':>7} {'worlds':>6} {'bad':>4} {'attempts':>8} {'chains':>6} {'nested':>6} {'depth':>5} {'G vs C':>7} {'R vs C':>7} {'RG vs C':>7} {'secs':>5}")
    bad = 0
    for n in args.records:
        sized = replace(settings, records=n)
        started = time.monotonic()
        worlds, size_bad = [], 0
        for seed in range(1, args.seeds + 1):
            try:
                world = generate(seed, sized)
            except RuntimeError as error:
                size_bad += 1
                print(f"  - N={n} seed {seed}: {error}")
                continue
            found = check_world(world, sized) + _check_scoring(world)
            if found:
                size_bad += 1
                print(f"  - N={n} seed {seed}: {'; '.join(found[:3])}")
            worlds.append(world)
        bad += size_bad
        if not worlds:
            continue
        diagnostics = [w.diagnostics() for w in worlds]
        gap = {v: max(abs(d["length_vs_C"][v]) for d in diagnostics) for v in ("G", "R", "RG")}
        print(
            f"  {n:>7} {len(worlds):>6} {size_bad:>4} "
            f"{statistics.mean(w.attempts for w in worlds):>8.2f} {statistics.median(d['chains'] for d in diagnostics):>6.0f} "
            f"{statistics.median(d['nested_chains'] for d in diagnostics):>6.0f} {max(d['max_chain_depth'] for d in diagnostics):>5} "
            f"{gap['G']:>7.1%} {gap['R']:>7.1%} {gap['RG']:>7.1%} {time.monotonic() - started:>5.1f}"
        )
    print("  (attempts: mean generator resamples; chains, nested: medians; depth: the longest chain; X vs C: the largest length gap)")
    print("\nRead one world by hand: python -m experiment preview --seed 1 --records 40")
    return 0 if not problems and not bad else 1


def _check_scoring(world: World) -> list[str]:
    """Answers built to land in each bucket must land there, and in a version without the records
    behind a mistake, its value must land somewhere else."""
    key = world.key
    answer = key["answer"]
    first = {bucket: key["buckets"]["RG"][bucket][0]["value"] for bucket in MISTAKES}
    cases = [(answer, "C", "correct", False), (answer, "RG", "correct", True), (None, "RG", "gave_up", False),
             (None, "RG", "cut_off", True), (first["missed_withdrawal"], "RG", "missed_withdrawal", True)]
    cases += [(value, "RG", bucket, False) for bucket, value in first.items()]
    cases += [(first["counted_gossip"], "R", "other", False), (first["missed_withdrawal"], "C", "other", False),
              (first["dropped_reinstated"], "C", "off_by_one_regular", False)]  # in C it is an ordinary change
    problems = []
    for value, version, want, hit_limit in cases:
        response = "I cannot work this out." if value is None else f"Working...\nANSWER: ${value}K"
        got = score(response, key, version, hit_limit)["bucket"]
        if got != want:
            problems.append(f"scoring: {value} on {version} is {got}, expected {want}")
    return problems


def cmd_preview(args) -> int:
    settings = replace(load_config(args.config).generator if args.config else GeneratorSettings(), records=args.records)
    world = generate(args.seed, settings)
    print(user_prompt(world.version(args.version), world.project))
    key = world.key
    width = text.id_width(world.n)
    print(f"\n===== ANSWER KEY =====\n{world.world_id}, project {world.project}, {world.attempts} generator attempt(s); answer {world.answer}")
    for version in VERSIONS:
        print(f"lures {version:2}: " + " | ".join(f"{name} {value}" for name, value in key["lures"][version].items()))
        print("   single mistakes: " + ", ".join(f"{b} {len(key['buckets'][version][b])}" for b in MISTAKES))
    mistakes = {i: (b, m["value"]) for b in MISTAKES for m in key["buckets"]["RG"][b] for i in m["record_ids"]}
    print("\nwithdrawal chains, and the answer if any withdrawal in one is mishandled (RG):")
    for c in world.chains:
        stack = " <- ".join(f"#{w:0{width}d}" for w in c.withdrawals)
        bucket, value = mistakes[c.adjust_id]
        print(f"  #{c.adjust_id:0{width}d} {c.amount:+d} <- {stack}  depth {c.depth}, {'counts' if c.active else 'withdrawn'}: {bucket} {value}")
    print("\ntrace (last column: the versions that show the record; the others show filler):")
    budget = None
    for r in world.records:
        if r.kind == "opening":
            budget = r.amount
            note = f"set {r.amount} -> {budget}"
        elif r.kind == "adjust":
            budget += r.amount if world.active[r.id] else 0
            note = f"{r.amount:+d} -> {budget}" if world.active[r.id] else f"{r.amount:+d} withdrawn"
        elif r.kind == "withdraw":
            note = f"withdraw #{r.target:0{width}d}" + ("" if world.active[r.id] else " (itself withdrawn)")
        elif r.kind == "gossip":
            note = f"claims {r.amount:+d} change" if r.relative else f"claims budget {r.amount}"
        else:
            note = ""
        shown = ",".join(v for v in VERSIONS if not world.switched_off(r, v))
        print(f"  #{r.id:0{width}d}  {r.kind:8} {note:34} {shown}")
    diagnostics = world.diagnostics()
    print("\nlength vs C: " + ", ".join(f"{v} {diagnostics['length_vs_C'][v]:+.1%}" for v in ("G", "R", "RG")))
    problems = check_world(world, settings)
    print("checks: " + ("all passed" if not problems else "; ".join(problems)))
    return 0 if not problems else 1


def cmd_check(args) -> int:
    """One small live call per model on the worked example: login, isolation, and the right answer."""
    config = load_config(args.config)
    case = json.loads(HAND_LOGS.read_text())[0]
    records = text.parse_lines(case["lines"])
    key = World("check", 0, case["project"], records).key
    prompt = Prompt(system_prompt("none"), user_prompt(records, case["project"]))
    names = args.models or list(config.models)
    bad = 0
    for name in names:
        spec = config.models[name]
        started = time.monotonic()
        try:
            client = make_client(spec)
            completion = client.complete(prompt, config.timeout_seconds)
        except ClientError as error:
            bad += 1
            print(f"{name:10} FAILED  {error}")
            continue
        scored = score(completion.text, key, "RG", hit_length_limit(completion.usage, completion.stop_reason, spec.max_output_tokens))
        problems = ([] if scored["correct"] else [f"wrong answer (expected {key['answer']})"]) + completion.audit
        bad += bool(problems)
        usage = completion.usage
        print(
            f"{name:10} {'ok   ' if not problems else 'CHECK'}  answer {scored['value']}  served {completion.served_model or spec.model} "
            f"at {spec.effort}  input {usage.get('input_tokens') or 0:,} output {usage.get('output_tokens') or 0:,}  "
            f"{time.monotonic() - started:.0f}s  {client.version}" + (f"  <- {'; '.join(problems)}" if problems else "")
        )
    return 0 if not bad else 1


def cmd_prepare(args) -> int:
    config = load_config(args.config)
    run = runs.prepare(config, args.config, args.run, runs.operator_name(args.operator))
    c = config
    print(
        f"Prepared {_relative(run.path)}: {c.logs} logs x {len(c.versions)} versions x {len(c.instructions)} instructions "
        f"x {c.repeats} repeats x {len(c.models)} models = {len(run.trials)} calls. No model calls were made."
    )
    print(f"  {'world':16} {'project':9} {'answer':>6} {'chains':>6} {'nested':>6}  length vs C (G, R, RG)")
    for world_id, w in run.manifest["worlds"].items():
        gaps = ", ".join(f"{w['length_vs_C'][v]:+.1%}" for v in ("G", "R", "RG"))
        print(f"  {world_id:16} {w['project']:9} {w['answer']:>6} {w['chains']:>6} {w['nested_chains']:>6}  {gaps}")
    print(f"\nNext: commit {_relative(run.path)} so everyone collects the same frozen plan, then\n  python -m experiment collect {_relative(run.path)}")
    return 0


def cmd_status(args) -> int:
    run = runs.load(args.run)
    attempts = runs.read_attempts(run)
    chosen = runs.counted(attempts)
    print(f"{_relative(run.path)}: {len(chosen)} of {len(run.trials)} calls done")
    print(f"  {'model':10} {'done':>5} {'left':>5} {'errors':>6} {'not eligible':>12}  done by          CLI versions")
    for name in run.config.models:
        planned = [t for t in run.trials if t.model == name]
        mine = [a for a in attempts if a["model"] == name]
        done = Counter(chosen[t.trial_id]["operator"] for t in planned if t.trial_id in chosen)
        errors = sum(a["status"] == "error" for a in mine)
        ineligible = sum(a["status"] == "completed" and not a["eligible"] for a in mine)
        versions = sorted({a["client_version"] for a in mine})
        by = ", ".join(f"{op} {count}" for op, count in done.most_common()) or "-"
        print(f"  {name:10} {sum(done.values()):>5} {len(planned) - sum(done.values()):>5} {errors:>6} {ineligible:>12}  {by:16} {', '.join(versions) or '-'}")
    return 0


def cmd_collect(args) -> int:
    run = runs.load(args.run)
    operator = runs.operator_name(args.operator)
    unknown = set(args.models or []) - set(run.config.models)
    if unknown:
        raise ValueError(f"not in this run: {', '.join(sorted(unknown))} (it has {', '.join(run.config.models)})")
    todo = pending(run, args.models, args.shard)
    if args.max_calls is not None:
        todo = todo[: args.max_calls]
    if not todo:
        print("Nothing left to collect for this selection.")
        return 0
    clients = {}
    for name in sorted({t.model for t in todo}):
        try:
            clients[name] = make_client(run.config.models[name])
        except ClientError as error:
            print(f"skipping {name}: {error}", file=sys.stderr)
    todo = [t for t in todo if t.model in clients]
    if not todo:
        return 1
    counts = Counter(t.model for t in todo)
    print(f"{len(todo)} calls as {operator}: " + ", ".join(f"{m} {n} ({clients[m].version})" for m, n in sorted(counts.items())))
    with runs.collect_lock(run, operator):
        summary = collect(run, clients, todo, operator, args.workers)
    print(f"\n{summary.calls} calls: " + ", ".join(f"{k} {v}" for k, v in summary.outcomes.most_common()))
    for model, reason in summary.stopped.items():
        print(f"stopped {model}: {reason}")
    left = len(pending(run, args.models, args.shard))
    print(f"{left} calls left for this selection. Commit {_relative(run.path / 'attempts')} and push so others continue from here.")
    return 130 if summary.interrupted else 0


def cmd_analyze(args) -> int:
    from experiment.analysis import analyze  # pandas is needed only here

    run = runs.load(args.run)
    print(analyze(run))
    print(f"\nTables: {_relative(run.path / 'analysis')}/")
    return 0


def _shard(value: str) -> tuple[int, int]:
    try:
        k, n = (int(part) for part in value.split("/"))
    except ValueError:
        raise argparse.ArgumentTypeError("use K/N, e.g. 1/2") from None
    if not 1 <= k <= n:
        raise argparse.ArgumentTypeError("need 1 <= K <= N")
    return k, n


def _relative(path: Path) -> str:
    path = Path(path).resolve()
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m experiment", description=__doc__)
    commands = parser.add_subparsers(required=True, metavar="command")

    validate = commands.add_parser("validate", help="hand logs vs the solvers, then every generator check on many seeds (no model calls)")
    validate.add_argument("--config", type=Path, help="use this run config's generator settings (default: built-in defaults)")
    validate.add_argument("--records", type=int, nargs="+", default=[40, 200, 1600], help="log sizes to generate")
    validate.add_argument("--seeds", type=int, default=20, help="seeds per size")
    validate.set_defaults(handler=cmd_validate)

    preview = commands.add_parser("preview", help="print one world's prompt, answer key, chains, and a record-by-record trace")
    preview.add_argument("--seed", type=int, default=1)
    preview.add_argument("--records", type=int, default=40)
    preview.add_argument("--version", choices=VERSIONS, default="RG")
    preview.add_argument("--config", type=Path, help="use this run config's generator settings")
    preview.set_defaults(handler=cmd_preview)

    check = commands.add_parser("check", help="one small live call per model: login, isolation, and the right answer")
    check.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help=f"run config with the models (default: {_relative(DEFAULT_CONFIG)})")
    check.add_argument("--models", nargs="+", help="model names from the config (default: all)")
    check.set_defaults(handler=cmd_check)

    prepare = commands.add_parser("prepare", help="generate a run's logs and freeze its call schedule (no model calls)")
    prepare.add_argument("config", type=Path, help="run config, e.g. config/trial.toml")
    prepare.add_argument("run", type=Path, help="new run directory, e.g. runs/trial_v1")
    prepare.add_argument("--operator", help="your name in the manifest (default: $EXPERIMENT_OPERATOR or git user.name)")
    prepare.set_defaults(handler=cmd_prepare)

    status = commands.add_parser("status", help="calls done and left per model, who ran them, and with which CLI versions")
    status.add_argument("run", type=Path)
    status.set_defaults(handler=cmd_status)

    collect_ = commands.add_parser("collect", help="make a run's remaining calls; rerun it to resume")
    collect_.add_argument("run", type=Path)
    collect_.add_argument("--models", nargs="+", help="only these models (default: all in the run)")
    collect_.add_argument("--shard", type=_shard, help="only shard K of N (e.g. 1/2), to split one model's calls between people")
    collect_.add_argument("--max-calls", type=int, help="stop after this many calls")
    collect_.add_argument("--workers", type=int, default=1, help="calls at once (default 1)")
    collect_.add_argument("--operator", help="your name on each attempt (default: $EXPERIMENT_OPERATOR or git user.name)")
    collect_.set_defaults(handler=cmd_collect)

    analyze = commands.add_parser("analyze", help="score every collected call and write the tables to <run>/analysis/")
    analyze.add_argument("run", type=Path)
    analyze.set_defaults(handler=cmd_analyze)
    return parser
