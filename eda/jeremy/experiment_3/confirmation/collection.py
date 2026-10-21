"""Resumable, append-only Codex collection and conservative event/answer scoring."""
import collections
from contextlib import contextmanager
import json
import os
from pathlib import Path
import random
import shutil
import signal
import statistics
import subprocess
import tempfile
import time

import ledger
import planning
import input_matching

TOKEN_FIELDS = ("input_tokens", "output_tokens", "cached_input_tokens", "cache_write_input_tokens", "reasoning_output_tokens")
RETRYABLE = {"execution_error", "timeout", "interrupted", "interrupted_before_receipt", "rate_limited"}
# These flags are scoped to each child, never written to the user's configuration.
OVERRIDES = {
    "forced_login_method": "chatgpt", "model_provider": "openai", "project_doc_max_bytes": 0,
    "suppress_unstable_features_warning": True,
    "web_search": "disabled", "agents.enabled": False,
    **{"features." + key: False for key in ("shell_tool", "remote_plugin", "plugins", "apps", "memories",
       "multi_agent", "multi_agent_v2", "hooks", "skill_search", "view_image", "image_generation")},
    "features.skip_host_skill_discovery": True,
}


def child_environment():
    env = os.environ.copy()
    for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_AUTH_TOKEN", "CODEX_THREAD_ID", "CODEX_PARENT_THREAD_ID"):
        env.pop(key, None)
    return env


def find_codex(explicit=None):
    selected = explicit or os.environ.get("CODEX_BIN")
    bundled = "/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex"
    found = shutil.which(selected) if selected else shutil.which("codex") or (bundled if Path(bundled).is_file() else None)
    if not found:
        raise ValueError("Codex executable not found; pass --codex-bin PATH or set CODEX_BIN")
    return str(Path(found).resolve())


def preflight(explicit=None):
    binary = find_codex(explicit)
    details = {}
    for name, args in (("login", ["login", "status"]), ("version", ["--version"]), ("help", ["exec", "--help"])):
        result = subprocess.run([binary, *args], env=child_environment(), capture_output=True, text=True, timeout=30)
        text = result.stdout + result.stderr
        if result.returncode:
            raise ValueError(f"Codex {name} check failed: {text.strip()}")
        details[name] = text
    if "Logged in using ChatGPT" not in details["login"]:
        raise ValueError(f"ChatGPT sign-in required. Run {binary!r} login.")
    for flag in ("--json", "--ephemeral", "--ignore-user-config", "--strict-config", "--output-last-message"):
        if flag not in details["help"]:
            raise ValueError(f"Installed CLI is missing {flag}; update it before collection")
    version_lines = [s for s in details["version"].splitlines() if s.startswith("codex-cli")]
    return {"codex_bin": binary, "cli_version": version_lines[0] if version_lines else details["version"].strip(),
            "authentication": "ChatGPT", "overrides": OVERRIDES}


@contextmanager
def run_lock(run):
    path = Path(run) / ".collecting"
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise ValueError(f"Run is locked: {path}. Check the recorded PID before removing a stale lock.") from None
    try:
        with os.fdopen(descriptor, "w") as handle:
            json.dump({"pid": os.getpid(), "started_at": planning.now()}, handle)
        yield
    finally:
        path.unlink(missing_ok=True)


def inspect_events(path):
    events, invalid = [], []
    if Path(path).exists():
        for number, line in enumerate(Path(path).read_text(errors="replace").splitlines(), 1):
            try:
                item = json.loads(line)
                if not isinstance(item, dict):
                    raise ValueError()
                events.append(item)
            except ValueError:
                invalid.append(number)
    counts = collections.Counter(e.get("type") for e in events)
    usage_events = [{"line_event_index": i, "event_type": e.get("type"), "usage": e["usage"]}
                    for i, e in enumerate(events) if isinstance(e.get("usage"), dict)]
    # Only a single completed turn has a known non-overlapping scope here.
    single_usage = len(usage_events) == 1 and usage_events[0]["event_type"] == "turn.completed" and counts["turn.completed"] == 1
    raw = usage_events[0]["usage"] if single_usage else {}
    tokens = {key: raw[key] if type(raw.get(key)) is int and raw[key] >= 0 else None for key in TOKEN_FIELDS}
    message_items = [e["item"] for e in events if e.get("type") == "item.completed" and isinstance(e.get("item"), dict) and e["item"].get("type") == "agent_message"]
    unexpected_items = sorted({e["item"].get("type", "unknown") for e in events
                              if isinstance(e.get("item"), dict) and e["item"].get("type") not in ("agent_message", "reasoning")})
    known_events = {"thread.started", "turn.started", "turn.completed", "turn.failed", "error", "item.started", "item.updated", "item.completed"}
    unexpected_events = sorted({str(e.get("type")) for e in events if e.get("type") not in known_events})
    return {"event_counts": dict(counts), "invalid_json_lines": invalid, "unexpected_items": unexpected_items,
            "unexpected_events": unexpected_events, "usage_raw": usage_events, **tokens,
            "usage_missing_reason": None if all(tokens[k] is not None for k in ("input_tokens", "output_tokens")) else
                ("multiple_or_ambiguous_usage_events" if len(usage_events) > 1 else "missing_reported_usage"),
            "final_messages": [item.get("text", "") for item in message_items],
            "reported_models": sorted({e["model"] for e in events if isinstance(e.get("model"), str)}),
            "errors": [e for e in events if e.get("type") in ("error", "turn.failed")]}


def classify(receipt, trial, world):
    events = receipt["events"]
    text = receipt["response"]
    scored = ledger.score(text, world["expected"], world["contexts"][trial["context"]])
    issues = []
    if events["invalid_json_lines"]:
        issues.append("invalid_event_stream")
    if events["unexpected_items"] or events["unexpected_events"]:
        issues.append("tool_or_unexpected_event")
    counts = events["event_counts"]
    if counts.get("turn.started", 0) != 1 or counts.get("turn.completed", 0) != 1 or counts.get("thread.started", 0) != 1:
        issues.append("not_one_completed_fresh_turn")
    if counts.get("turn.failed", 0) or counts.get("error", 0):
        issues.append("error_event")
    if len(events["final_messages"]) != 1 or events["final_messages"][0].strip() != text.strip():
        issues.append("final_answer_event_mismatch")
    if events["reported_models"] and events["reported_models"] != [trial["model"]]:
        issues.append("reported_model_mismatch")
    if trial["effort"] == "none" and events["reasoning_output_tokens"] != 0:
        issues.append("reasoning_off_unverified")
    execution = receipt["execution_status"]
    diagnostics = (receipt.get("stderr_tail", "") + json.dumps(events["errors"])).lower()
    if execution == "execution_error":
        if any(word in diagnostics for word in ("rate limit", "usage limit", "quota", "too many requests")):
            execution = "rate_limited"
        elif any(word in diagnostics for word in ("not supported", "unsupported", "unknown model", "invalid value", "not found", "not available", "not allowed")):
            execution = "configuration_error"
    if any(word in diagnostics for word in ("max_output_tokens", "output token limit", "maximum output", "max_tokens")):
        execution = "output_limit"
    eligible = execution == "completed" and not issues
    return {**scored, "answer_outcome": scored["outcome"],
            "outcome": execution if execution != "completed" else ("excluded_interface" if issues else scored["outcome"]),
            "eligible": eligible, "audit_issues": issues,
            "correct": scored["correct"] if eligible else None, "budget_correct": scored["budget_correct"] if eligible else None,
            "completed": execution == "completed" and counts.get("turn.completed", 0) == 1,
            "reported_model": events["reported_models"][0] if len(events["reported_models"]) == 1 else None}


def stop_process(process):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()


def execute_attempt(run, trial, number, runtime, timeout):
    folder = run / "attempts" / trial["trial_id"] / f"{number:03d}"
    folder.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(run / trial["prompt_path"], folder / "prompt.txt")
    shutil.copyfile(run / trial["system_path"], folder / "system.md")
    receipt = {"trial_id": trial["trial_id"], "attempt": number, "started_at": planning.now(),
               "cli_version": runtime["cli_version"], "execution_status": "interrupted_before_receipt"}
    planning.dump(folder / "started.json", receipt)
    process = None
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="eda-ledger-") as work:
        overrides = {**OVERRIDES, "model_reasoning_effort": trial["effort"], "model_instructions_file": str(folder / "system.md")}
        command = [runtime["codex_bin"], "exec", "--json", "--ephemeral", "--ignore-user-config", "--strict-config",
                   "--skip-git-repo-check", "--sandbox", "read-only", "--cd", work, "--model", trial["model"]]
        for key, value in overrides.items():
            command.extend(["-c", f"{key}={json.dumps(value)}"])
        command.extend(["--output-last-message", str(folder / "response.txt"), "-"])
        planning.dump(folder / "command.json", command)
        with (folder / "prompt.txt").open("rb") as prompt, (folder / "events.jsonl").open("wb") as output, (folder / "stderr.log").open("wb") as error:
            try:
                process = subprocess.Popen(command, stdin=prompt, stdout=output, stderr=error, env=child_environment(), start_new_session=True)
                code = process.wait(timeout=timeout)
                receipt.update(returncode=code, execution_status="completed" if code == 0 else "execution_error")
            except subprocess.TimeoutExpired:
                stop_process(process)
                receipt.update(returncode=process.returncode, execution_status="timeout")
            except KeyboardInterrupt:
                if process:
                    stop_process(process)
                receipt.update(returncode=process.returncode if process else None, execution_status="interrupted")
            except OSError as exc:
                receipt.update(returncode=None, execution_status="execution_error", launch_error=str(exc))
    receipt.update(finished_at=planning.now(), elapsed_seconds=round(time.monotonic() - start, 3))
    receipt["response"] = (folder / "response.txt").read_text(errors="replace") if (folder / "response.txt").exists() else ""
    receipt["events"] = inspect_events(folder / "events.jsonl")
    receipt["stderr_tail"] = (folder / "stderr.log").read_text(errors="replace")[-6000:]
    planning.dump(folder / "receipt.json", receipt)
    return receipt


def read_attempts(run, trials, worlds, recover=False):
    lookup = {t["trial_id"]: t for t in trials}
    attempts = []
    for started in sorted((run / "attempts").glob("*/*/started.json")):
        folder = started.parent
        path = folder / "receipt.json"
        if not path.exists():
            # A killed collector never silently turns into a completed trial.
            receipt = json.loads(started.read_text())
            receipt.update(execution_status="interrupted_before_receipt", returncode=None, finished_at=None,
                           response=(folder / "response.txt").read_text() if (folder / "response.txt").exists() else "",
                           events=inspect_events(folder / "events.jsonl"), stderr_tail="")
            if recover:
                planning.dump(path, receipt)
        else:
            receipt = json.loads(path.read_text())
        if receipt["trial_id"] not in lookup:
            raise ValueError("Attempt belongs to an unknown trial")
        trial = lookup[receipt["trial_id"]]
        attempts.append({**trial, **receipt, **classify(receipt, trial, worlds[trial["world_id"]]),
                         "attempt_path": str(folder.relative_to(run))})
    return attempts


def collect(run, max_new, explicit=None, models=None, efforts=None, retry_errors=False):
    run = Path(run).resolve()
    if max_new < 1:
        raise ValueError("--max-new-trials must be positive")
    manifest, trials, worlds = planning.load_plan(run, check_sources=True)
    runtime = preflight(explicit)
    if manifest.get("required_runtime") and runtime != manifest["required_runtime"]:
        raise ValueError("CLI runtime differs from tokenizer calibration; review and prepare a new run")
    requested_models = set(models or [])
    requested_efforts = set(efforts or [])
    selected = [t for t in trials if (not requested_models or t["model"] in requested_models) and (not requested_efforts or t["effort"] in requested_efforts)]
    if not selected:
        raise ValueError("No planned trials match the requested model/effort filters")
    with run_lock(run):
        runtime_path = run / "runtime.json"
        if runtime_path.exists():
            if json.loads(runtime_path.read_text()) != runtime:
                raise ValueError("CLI version/path/settings changed; create a new run instead of mixing runtimes")
        else:
            planning.dump(runtime_path, runtime)
        existing = read_attempts(run, trials, worlds, recover=True)
        history = collections.defaultdict(list)
        for attempt in existing:
            history[attempt["trial_id"]].append(attempt)
        progress = analyze(run, locked=True)
        if progress.get("input_matching", {}).get("failed_pairs", 0):
            raise ValueError("Reported input matching failed in a saved pair; preserve this run and review before new collection")
        count = 0
        for trial in selected:
            previous = sorted(history[trial["trial_id"]], key=lambda a: a["attempt"])
            if previous:
                last = previous[-1]
                if not retry_errors or last["outcome"] not in RETRYABLE or len(previous) >= manifest["config"]["max_attempts"]:
                    continue
            number = max((a["attempt"] for a in previous), default=0) + 1
            print(f"[{count + 1}/{max_new}] {trial['world_id']} {trial['context']}/{trial['instruction']} {trial['model']} {trial['effort']}", flush=True)
            receipt = execute_attempt(run, trial, number, runtime, manifest["config"]["timeout_seconds"])
            result = classify(receipt, trial, worlds[trial["world_id"]])
            print(f"  {result['outcome']} | input={receipt['events']['input_tokens']} output={receipt['events']['output_tokens']}", flush=True)
            count += 1
            # Regenerate summaries after every saved receipt; raw attempts remain append-only.
            progress = analyze(run, locked=True)
            if progress.get("input_matching", {}).get("failed_pairs", 0):
                print("Stopped: missing reported input usage or a pair exceeds the input-length tolerance. Responses are saved; inspect input_length_audit.csv.", flush=True)
                break
            if not result["eligible"]:
                print("Stopped after an execution/interface problem. Inspect this attempt before continuing.", flush=True)
                break
            if count >= max_new:
                break
        if count == 0:
            analyze(run, locked=True)
        return count


def paired_summary(trials, latest, factor="context"):
    contrasts = {
        "context": (("C", "RG"), ("C", "G"), ("C", "R"), ("R", "RG")),
        "effort": (("low", "none"), ("medium", "none"), ("high", "none"), ("medium", "low"), ("high", "low"), ("high", "medium"), ("xhigh", "high"), ("max", "xhigh")),
        "instruction": (("skill", "none"), ("skill", "neutral"), ("neutral", "none")),
    }
    fixed = tuple(k for k in ("model", "effort", "instruction", "records", "context") if k != factor)
    grouped = collections.defaultdict(dict)
    for trial in trials:
        attempt = latest.get(trial["trial_id"])
        if attempt and attempt["eligible"]:
            key = tuple(trial[k] for k in (*fixed, "world_id"))
            grouped[key][trial[factor]] = int(attempt["correct"])
    pairs = collections.defaultdict(list)
    for key, outcomes in grouped.items():
        for left, right in contrasts[factor]:
            if left in outcomes and right in outcomes:
                pairs[(*key[:-1], left, right)].append(outcomes[left] - outcomes[right])
    rows = []
    for key, differences in pairs.items():
        n = len(differences)
        rng = random.Random(180)
        draws = sorted(statistics.mean(rng.choices(differences, k=n)) * 100 for _ in range(2000)) if n >= 2 else []
        rows.append(dict(zip((*fixed, "left_" + factor, "right_" + factor), key),
                         matched_worlds=n, accuracy_gap_pp=statistics.mean(differences) * 100,
                         bootstrap_low_pp=draws[int(.025 * len(draws))] if draws else None,
                         bootstrap_high_pp=draws[min(len(draws)-1, int(.975 * len(draws)))] if draws else None))
    return rows


def analyze(run, locked=False):
    run = Path(run).resolve()
    if not locked:
        with run_lock(run):
            return analyze(run, locked=True)
    manifest, trials, worlds = planning.load_plan(run)
    attempts = read_attempts(run, trials, worlds)
    latest = {}
    for attempt in attempts:
        key = attempt["trial_id"]
        if key not in latest or attempt["attempt"] > latest[key]["attempt"]:
            latest[key] = attempt
    # A convenient consolidated view, rebuildable from immutable per-attempt receipts.
    planning.write_rows(run / "responses.jsonl", attempts)
    base_fields = ["trial_id", "attempt", "world_id", "stage", "records", "context", "instruction", "model", "effort", "outcome", "eligible"]
    tokens = [{**{k: a[k] for k in base_fields}, **{k: a["events"][k] for k in TOKEN_FIELDS},
               "experimental_prompt_tokens": a["experimental_prompt_tokens"], "prompt_tokens_exact": a["prompt_tokens_exact"],
               "usage_missing_reason": a["events"]["usage_missing_reason"], "usage_raw": a["events"]["usage_raw"],
               "included_in_accuracy": latest[a["trial_id"]]["attempt"] == a["attempt"] and a["eligible"],
               "elapsed_seconds": a.get("elapsed_seconds"), "attempt_path": a["attempt_path"]} for a in attempts]
    planning.write_csv(run / "token_usage.csv", tokens, base_fields + list(TOKEN_FIELDS) + ["experimental_prompt_tokens", "prompt_tokens_exact", "usage_missing_reason", "usage_raw", "included_in_accuracy", "elapsed_seconds", "attempt_path"])
    scored = []
    for trial in trials:
        attempt = latest.get(trial["trial_id"])
        scored.append({**trial, **({k: attempt[k] for k in ("attempt", "outcome", "correct", "budget_correct", "format_valid", "eligible", "audit_issues",
                                                          "expected_budget_k", "returned_budget_k", "error_k", "absolute_error_k")} if attempt else
                                  {"attempt": None, "outcome": "not_collected", "correct": None, "budget_correct": None, "format_valid": None,
                                   "eligible": False, "audit_issues": [], "expected_budget_k": worlds[trial["world_id"]]["expected"]["budget_k"],
                                   "returned_budget_k": None, "error_k": None, "absolute_error_k": None})})
    planning.write_csv(run / "scored.csv", scored)
    group_fields = ("model", "effort", "stage", "records", "context", "instruction")
    groups = collections.defaultdict(list)
    for trial in trials:
        groups[tuple(trial[k] for k in group_fields)].append(trial)
    summaries = []
    for key, planned in groups.items():
        ids = {t["trial_id"] for t in planned}
        all_attempts = [a for a in attempts if a["trial_id"] in ids]
        last = [latest[i] for i in ids if i in latest]
        eligible = [a for a in last if a["eligible"]]
        summary = {**dict(zip(group_fields, key)), "planned": len(planned), "attempted_trials": len(last),
                   "attempts_including_retries": len(all_attempts), "completed_trials": sum(a["completed"] for a in last),
                   "eligible_trials": len(eligible), "valid_format_trials": sum(a["format_valid"] for a in eligible),
                   "correct_trials": sum(a["correct"] for a in eligible),
                   "accuracy_percent": 100 * sum(a["correct"] for a in eligible) / len(eligible) if eligible else None}
        summary.update(wrong_budget_trials=sum(a["outcome"] == "wrong_budget" for a in eligible),
                       abstained_trials=sum(a["outcome"] == "abstained" for a in eligible),
                       malformed_or_missing_trials=sum(a["outcome"] in {"malformed_output", "missing_output"} for a in eligible))
        numeric = [a["absolute_error_k"] for a in eligible if a["absolute_error_k"] is not None]
        summary["numeric_answers"] = len(numeric)
        summary["mean_absolute_error_k_among_numeric_answers"] = statistics.mean(numeric) if numeric else None
        for prefix, values in (("all_attempts", all_attempts), ("included", eligible)):
            for field in TOKEN_FIELDS:
                known = [a["events"][field] for a in values if a["events"][field] is not None]
                summary[f"{prefix}_{field}_known_total"] = sum(known) if known else None
                summary[f"{prefix}_{field}_reported_attempts"] = len(known)
                summary[f"{prefix}_{field}_mean"] = statistics.mean(known) if known else None
                summary[f"{prefix}_{field}_median"] = statistics.median(known) if known else None
        summaries.append(summary)
    planning.write_csv(run / "summary.csv", summaries)
    for factor, filename in (("context", "paired_effects.csv"), ("effort", "reasoning_effects.csv"), ("instruction", "instruction_effects.csv")):
        fixed = [k for k in ("model", "effort", "instruction", "records", "context") if k != factor]
        planning.write_csv(run / filename, paired_summary(trials, latest, factor),
                           fixed + ["left_" + factor, "right_" + factor, "matched_worlds", "accuracy_gap_pp", "bootstrap_low_pp", "bootstrap_high_pp"])
    progress = {"planned_trials": len(trials), "attempts": len(attempts), "attempted_trials": len(latest),
                "eligible_trials": sum(a["eligible"] for a in latest.values()), "not_collected": len(trials) - len(latest),
                "outcomes": dict(collections.Counter(a["outcome"] for a in latest.values()))}
    guard = manifest["config"].get("reported_input_matching", {})
    if guard.get("enabled") and manifest["stage"] == "confirmation":
        rows, status = input_matching.audit(trials, latest, guard["tolerance"])
        planning.write_csv(run / "input_length_audit.csv", rows)
        progress["input_matching"] = status
    planning.dump(run / "progress.json", progress)
    return progress
