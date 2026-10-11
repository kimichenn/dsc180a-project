"""Notebook helpers for Jeremy's pilot, frozen evaluation, scoring, and EDA.

Importing this module never downloads models or generates responses. Collection is
explicit. Raw attempts are append-only and a run refuses changed inputs on resume.
"""
from __future__ import annotations

import gc
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import random
import re
import time
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

CONDITIONS = {
    "A": {"misleading_info": False, "skill_used": False},
    "B": {"misleading_info": True, "skill_used": False},
    "C": {"misleading_info": False, "skill_used": True},
    "D": {"misleading_info": True, "skill_used": True},
}
LABELS = {"correct", "adopted_misleading", "abstained", "other_error"}
COMMON = "Use only the supplied facts and source rules about this fictional scenario."
OUTPUT_RULE = (
    "Give a brief explanation. End with exactly one line: Final answer: <entity name>. "
    "If the facts do not determine an answer, end with Final answer: Cannot determine."
)


def digest(value):
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    rows = []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at {path.name}:{number}; inspect the interrupted write.") from exc
    return rows


def append_jsonl(path, record):
    with Path(path).open("a") as out:
        out.write(json.dumps(record) + "\n")
        out.flush()
        os.fsync(out.fileno())


def calculate(value, operation, parameter):
    if operation == "identity":
        return value
    if operation == "subtract":
        return value - parameter
    if operation == "add":
        return value + parameter
    if operation == "multiply":
        return value * parameter
    if operation == "divide_floor" and parameter > 0:
        return value // parameter
    raise ValueError(f"Unsupported calculation: {operation}")


def answer_key(question, misleading=False, basic=False):
    a = question["misleading_value" if misleading else "correct_value"]
    b = question["other_value"]
    if not basic:
        a = calculate(a, question["operation"], question["parameter_a"])
        b = calculate(b, question["operation"], question["parameter_b"])
    if a == b:
        raise ValueError(f"{question['question_id']} has a tied answer.")
    choose_a = a > b if question["comparison"] == "larger" else a < b
    return question["entity_a" if choose_a else "entity_b"]


def load_study(root):
    root = Path(root)
    questions = json.loads((root / "data/scenarios.json").read_text())
    config = json.loads((root / "config.json").read_text())
    skill = (root / "skill.md").read_text().strip()
    validate_questions(questions)
    if not config["models"] or config["enable_thinking"] is not False:
        raise ValueError("This study requires at least one model and non-thinking mode.")
    if config["quantization"] != "none":
        raise ValueError("This runner supports unquantized models; use a new implementation/run for quantization.")
    if config["device"] not in ("auto", "cpu", "mps", "cuda"):
        raise ValueError("device must be auto, cpu, mps, or cuda")
    if config["dtype"] not in ("auto", "float32", "float16", "bfloat16"):
        raise ValueError("Unsupported dtype")
    for count in [config["max_attempts"], *config["repetitions"].values()]:
        if not isinstance(count, int) or count < 1:
            raise ValueError("Repetitions and attempt limits must be positive integers.")
    return questions, config, skill


def validate_questions(questions):
    ids = [q["question_id"] for q in questions]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate question IDs.")
    for q in questions:
        if q["phase"] not in ("pilot", "evaluation") or q["subtype"] not in ("distractor", "update"):
            raise ValueError(f"Invalid phase/subtype: {q['question_id']}")
        if q["difficulty"] not in ("basic", "calculation") or q["comparison"] not in ("larger", "smaller"):
            raise ValueError(f"Invalid difficulty/comparison: {q['question_id']}")
        if q["claim_order"] not in ("governing_first", "competing_first"):
            raise ValueError("Invalid claim order.")
        if q["entity_a"] == q["entity_b"] or q["correct_value"] == q["misleading_value"]:
            raise ValueError(f"Non-distinct entities/claims: {q['question_id']}")
        if answer_key(q) == answer_key(q, misleading=True):
            raise ValueError(f"Misleading claim does not change the answer: {q['question_id']}")
        if q["difficulty"] == "calculation" and answer_key(q) == answer_key(q, basic=True):
            raise ValueError(f"Calculation is unnecessary for the ranking: {q['question_id']}")
    pilot_entities = {q[k] for q in questions if q["phase"] == "pilot" for k in ("entity_a", "entity_b")}
    eval_entities = {q[k] for q in questions if q["phase"] == "evaluation" for k in ("entity_a", "entity_b")}
    if pilot_entities & eval_entities:
        raise ValueError("Pilot and evaluation entities overlap.")


def prompt_messages(q, condition, skill):
    flags = CONDITIONS[condition]
    competing_value = q["misleading_value"] if flags["misleading_info"] else q["correct_value"]
    a, b, metric, unit = q["entity_a"], q["entity_b"], q["metric"], q["unit"]
    if q["subtype"] == "distractor":
        rule = (
            "The official register is the source of record. The team estimate is unverified "
            "and cannot override the register. Both claims describe the same situation."
        )
        governing = f"Official register: {a}'s {metric} is {q['correct_value']} {unit}."
        competing = f"Unverified team estimate: {a}'s {metric} is {competing_value} {unit}."
    else:
        rule = (
            "The official notice dated June 3 supersedes the archived June 1 record for "
            f"{a}. The official register for {b} is unchanged."
        )
        governing = f"Official notice, June 3: {a}'s {metric} is {q['correct_value']} {unit}."
        competing = f"Archived record, June 1: {a}'s {metric} is {competing_value} {unit}."
    claims = [governing, competing]
    if q["claim_order"] == "competing_first":
        claims.reverse()
    context = "\n\n".join([
        rule,
        f"Official register: {b}'s {metric} is {q['other_value']} {unit}.",
        q["calculation_rule"], *claims, q["question"], OUTPUT_RULE,
    ])
    system = COMMON + ("\n\n" + skill if flags["skill_used"] else "")
    return [{"role": "system", "content": system}, {"role": "user", "content": context}]


def build_trials(questions, config, skill, phase):
    if phase not in config["repetitions"]:
        raise ValueError("Choose pilot or evaluation.")
    trials = []
    for model in config["models"]:
        model_trials = []
        for q in questions:
            if q["phase"] != phase:
                continue
            for condition, flags in CONDITIONS.items():
                for repetition in range(1, config["repetitions"][phase] + 1):
                    trial_id = f"{phase}|{q['question_id']}|{model}|{condition}|{repetition}"
                    model_trials.append({
                        "trial_id": trial_id, "phase": phase, "question_id": q["question_id"],
                        "model": model, "condition": condition, **flags, "repetition": repetition,
                        "seed": int(digest(f"{config['seed']}|{q['question_id']}|{repetition}")[:8], 16),
                        "subtype": q["subtype"], "difficulty": q["difficulty"], "domain": q["domain"],
                        "question": q["question"], "expected": answer_key(q),
                        "alternative": answer_key(q, misleading=True),
                        "messages": prompt_messages(q, condition, skill),
                    })
        random.Random(config["seed"]).shuffle(model_trials)
        trials.extend(model_trials)
    return trials


class LocalQwenBackend:
    """Loads one pinned checkpoint at a time. Only constructed for an explicit run."""

    def __init__(self, config):
        from packaging.version import Version
        if Version(importlib.metadata.version("transformers")) < Version("4.51"):
            raise RuntimeError("Qwen3 needs transformers>=4.51. Install requirements.txt in the notebook's environment.")
        import torch
        self.config, self.torch = config, torch
        self.device = config["device"]
        if self.device == "auto":
            self.device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
        self.dtype_name = config["dtype"]
        if self.dtype_name == "auto":
            self.dtype_name = "float32" if self.device == "cpu" else "float16"
        self.dtype = getattr(torch, self.dtype_name)
        self.model = self.tokenizer = None

    def runtime(self):
        packages = {}
        for name in ("torch", "transformers", "huggingface-hub", "accelerate"):
            packages[name] = importlib.metadata.version(name)
        return {"backend": "transformers", "python": platform.python_version(),
                "platform": platform.platform(), "device": self.device,
                "dtype": self.dtype_name, "quantization": "none", "packages": packages}

    def resolve(self, model):
        from huggingface_hub import HfApi
        from transformers import AutoTokenizer
        revision = HfApi().model_info(model["model_id"], revision=model["revision"]).sha
        tokenizer = AutoTokenizer.from_pretrained(model["model_id"], revision=revision, trust_remote_code=False)
        if not tokenizer.chat_template or "enable_thinking" not in tokenizer.chat_template:
            raise RuntimeError("The tokenizer must support Qwen's explicit non-thinking switch.")
        return {**model, "revision": revision, "chat_template_sha256": digest(tokenizer.chat_template)}

    def load(self, model):
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(model["model_id"], revision=model["revision"], trust_remote_code=False)
        if digest(self.tokenizer.chat_template) != model["chat_template_sha256"]:
            raise RuntimeError("The tokenizer template changed from the frozen run.")
        self.model = AutoModelForCausalLM.from_pretrained(
            model["model_id"], revision=model["revision"], torch_dtype=self.dtype,
            low_cpu_mem_usage=True, trust_remote_code=False,
        ).to(self.device).eval()

    def generate(self, trial):
        from transformers import set_seed
        set_seed(trial["seed"])
        rendered = self.tokenizer.apply_chat_template(
            trial["messages"], tokenize=False, add_generation_prompt=True, enable_thinking=False,
        )
        inputs = self.tokenizer(rendered, return_tensors="pt", add_special_tokens=False).to(self.device)
        limit = self.model.config.max_position_embeddings
        if inputs["input_ids"].shape[-1] + self.config["generation"]["max_new_tokens"] > limit:
            raise ValueError("Prompt plus output allowance exceeds the checkpoint context limit.")
        with self.torch.inference_mode():
            output = self.model.generate(
                **inputs, **self.config["generation"],
                pad_token_id=self.tokenizer.eos_token_id,
            )
        tokens = output[0, inputs["input_ids"].shape[-1]:].tolist()
        eos = self.model.generation_config.eos_token_id
        eos = set(eos if isinstance(eos, list) else [eos])
        stopped = bool(tokens) and tokens[-1] in eos
        return {"response": self.tokenizer.decode(tokens, skip_special_tokens=True),
                "status": "ok" if stopped else "truncated", "finish_reason": "eos" if stopped else "length",
                "input_tokens": inputs["input_ids"].shape[-1], "output_tokens": len(tokens),
                "rendered_prompt_sha256": digest(rendered)}

    def close(self):
        self.model = self.tokenizer = None
        gc.collect()
        if self.device == "cuda":
            self.torch.cuda.empty_cache()
        elif self.device == "mps":
            self.torch.mps.empty_cache()


@contextmanager
def run_lock(run_dir):
    """Prevent two notebook kernels from appending to the same run."""
    path = run_dir / ".collecting"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError(f"{path} already exists. If its kernel died, remove this lock only after confirming no run is active.") from exc
    try:
        with os.fdopen(fd, "w") as out:
            out.write(str(os.getpid()))
        yield
    finally:
        path.unlink(missing_ok=True)


def run_path(root, run_name):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", run_name):
        raise ValueError("Use a simple run name such as pilot_v1 or evaluation_v1.")
    return Path(root) / "runs" / run_name


def collect(root, phase, run_name, *, pilot_reviewed=False, max_new_trials=None, backend=None):
    """Freeze inputs on first call; resume without regenerating completed trials.

    Actual model calls require invoking this function; the notebook defaults to
    preview only. Errors receive at most max_attempts across all resumes.
    """
    root = Path(root)
    if phase == "evaluation" and not pilot_reviewed:
        raise ValueError("Review the pilot and set PILOT_REVIEWED=True before evaluation.")
    if max_new_trials is not None and max_new_trials < 1:
        raise ValueError("max_new_trials must be positive or None.")
    questions, config, skill = load_study(root)
    trials = build_trials(questions, config, skill, phase)
    if not trials:
        raise ValueError("No trials for this phase.")
    run_dir = run_path(root, run_name)
    run_dir.mkdir(parents=True, exist_ok=True)
    design = {"phase": phase, "config": config, "questions": questions, "skill": skill,
              "runner_sha256": digest(Path(__file__).read_text()), "trials": trials}
    with run_lock(run_dir):
        manifest_path = run_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else None
        if manifest and manifest["design_sha256"] != digest(design):
            raise ValueError("Run inputs/code changed. Restore them or choose a new run name; existing data are preserved.")
        backend = backend or LocalQwenBackend(config)
        runtime = backend.runtime()
        if manifest:
            if manifest["runtime"] != runtime:
                raise ValueError("Runtime changed; use the original environment or a new run name.")
        else:
            pinned = {name: backend.resolve(model) for name, model in config["models"].items()}
            manifest = {"created_at": utc_now(), "design_sha256": digest(design),
                        "design": design, "models": pinned, "runtime": runtime,
                        "pilot_reviewed": pilot_reviewed}
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        attempts = read_jsonl(run_dir / "responses.jsonl")
        known = {t["trial_id"] for t in trials}
        if any(r["trial_id"] not in known for r in attempts):
            raise ValueError("The response file contains trials outside this frozen design.")
        done = {r["trial_id"] for r in attempts if r["status"] in ("ok", "truncated")}
        counts = Counter(r["trial_id"] for r in attempts)
        remaining = [t for t in trials if t["trial_id"] not in done and counts[t["trial_id"]] < config["max_attempts"]]
        generated = 0
        for model in config["models"]:
            pending = [t for t in remaining if t["model"] == model]
            if not pending or (max_new_trials is not None and generated >= max_new_trials):
                continue
            print(f"Loading {model}; {len(pending)} unfinished trials.", flush=True)
            try:
                backend.load(manifest["models"][model])
                for trial in pending:
                    if max_new_trials is not None and generated >= max_new_trials:
                        break
                    while counts[trial["trial_id"]] < config["max_attempts"]:
                        started = time.monotonic()
                        counts[trial["trial_id"]] += 1
                        try:
                            completion = backend.generate(trial)
                            if completion["status"] not in ("ok", "truncated"):
                                raise ValueError("Unexpected completion status.")
                            record = {**trial, **completion, "error": None}
                        except Exception as exc:
                            record = {**trial, "response": "", "status": "error",
                                      "error": f"{type(exc).__name__}: {exc}"}
                        record.update(attempt=counts[trial["trial_id"]], timestamp=utc_now(),
                                      latency_s=round(time.monotonic() - started, 3),
                                      checkpoint=manifest["models"][model],
                                      design_sha256=manifest["design_sha256"])
                        append_jsonl(run_dir / "responses.jsonl", record)
                        if record["status"] != "error":
                            break
                    generated += 1
                    print(f"{trial['trial_id']}: {record['status']}", flush=True)
            finally:
                backend.close()
        print(f"Processed {generated} new trials. Results: {run_dir}")
    return run_dir


def normalize_answer(text):
    return re.sub(r"\s+", " ", re.sub(r"[*`_]", "", text).strip().rstrip(".")).casefold()


def auto_score(response, expected, alternative, misleading_info, status="ok"):
    if status != "ok":
        return {"label": None, "final_answer": None, "review_reason": status}
    clean = re.sub(r"[*`_]", "", response).strip()
    matches = list(re.finditer(r"(?im)^\s*final answer\s*:\s*([^\n]+)$", clean))
    if len(matches) != 1 or clean[matches[0].end():].strip():
        return {"label": None, "final_answer": None, "review_reason": "missing, repeated, or non-final answer field"}
    answer = matches[0].group(1).strip()
    normalized = normalize_answer(answer)
    if normalized == normalize_answer(expected):
        label = "correct"
    elif normalized == normalize_answer(alternative):
        label = "adopted_misleading" if misleading_info else "other_error"
    elif normalized in ("cannot determine", "insufficient information", "unknown", "undetermined"):
        label = "abstained"
    else:
        label = None
    return {"label": label, "final_answer": answer,
            "review_reason": "ambiguous final answer" if label is None else ""}


def response_id(row):
    # Binds a manual label to this exact completion, not just to a reusable trial ID.
    return digest({"trial_id": row["trial_id"], "response": row["response"], "status": row["status"]})[:24]


def result_frame(trials, run_dir):
    records = read_jsonl(Path(run_dir) / "responses.jsonl")
    latest, manual = {}, {}
    allowed = {t["trial_id"] for t in trials}
    for row in records:
        if row["trial_id"] not in allowed:
            raise ValueError("Results do not match the selected phase/design.")
        latest[row["trial_id"]] = row
    for row in read_jsonl(Path(run_dir) / "manual_labels.jsonl"):
        manual[row["review_id"]] = row
    output = []
    for trial in trials:
        row = latest.get(trial["trial_id"], {**trial, "response": "", "status": "not_collected"})
        row = dict(row)
        row.update(auto_score(row["response"], row["expected"], row["alternative"], row["misleading_info"], row["status"]))
        row["review_id"] = response_id(row)
        row["label_source"] = "auto" if row["label"] else "pending"
        if row["review_id"] in manual and row["status"] in ("ok", "truncated"):
            row["label"] = manual[row["review_id"]]["label"]
            if row["label"] not in LABELS:
                raise ValueError("Invalid manual label.")
            row["label_source"] = "manual"
        row["correct"] = None if row["label"] is None else int(row["label"] == "correct")
        output.append(row)
    return pd.DataFrame(output)


def load_results(root, phase, run_name):
    """Existing runs are analyzed using their frozen snapshots, not edited inputs."""
    directory = run_path(root, run_name)
    manifest_path = directory / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        design = manifest["design"]
        if design["phase"] != phase:
            raise ValueError("Run name belongs to a different phase.")
        trials, config = design["trials"], design["config"]
    else:
        questions, config, skill = load_study(root)
        trials = build_trials(questions, config, skill, phase)
    return result_frame(trials, directory), config


def summarize(frame, repetitions):
    temp = frame.assign(
        collected=frame["status"].isin(["ok", "truncated"]),
        execution_error=frame["status"].eq("error"),
        awaiting_review=frame["status"].isin(["ok", "truncated"]) & frame["label"].isna(),
    )
    coverage = temp.groupby(["model", "condition"], observed=True).agg(
        planned=("trial_id", "size"), collected=("collected", "sum"),
        scored=("correct", "count"), execution_errors=("execution_error", "sum"),
        awaiting_review=("awaiting_review", "sum"),
    )
    cells = temp.groupby(["model", "question_id", "condition", "subtype", "difficulty"], observed=True).agg(
        scored=("correct", "count"), accuracy=("correct", "mean"),
    ).reset_index()
    complete = cells[cells["scored"].eq(repetitions)]
    paired = complete.pivot(index=["model", "question_id", "subtype", "difficulty"], columns="condition", values="accuracy")
    paired = paired.reindex(columns=list(CONDITIONS)).dropna()
    models = list(frame["model"].unique())
    table = pd.DataFrame(index=pd.Index(models, name="model"), columns=["questions", *CONDITIONS], dtype=float)
    table["questions"] = 0
    for model in models:
        subset = paired.loc[paired.index.get_level_values("model") == model]
        if len(subset):
            table.loc[model, "questions"] = len(subset)
            table.loc[model, list(CONDITIONS)] = subset.mean().values * 100
    effects = pd.DataFrame(index=table.index)
    effects["misleading_drop_pp"] = table["A"] - table["B"]
    effects["skill_gain_under_misleading_pp"] = table["D"] - table["B"]
    effects["baseline_skill_gain_pp"] = table["C"] - table["A"]
    effects["reduction_in_drop_pp"] = (table["A"] - table["B"]) - (table["C"] - table["D"])
    return coverage, paired, table, effects


def export_review(frame, directory):
    """Blind IDs; review every error/ambiguous response plus a fixed 10% correct sample.

    Existing choices and notes are preserved. The queue contains no model or
    condition columns; expected/alternative describe answer choices, not labels.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    valid = frame[frame["status"].isin(["ok", "truncated"])].copy()
    sample = valid["review_id"].map(lambda key: int(key[:8], 16) % 10 == 0)
    queue = valid[valid["label"].ne("correct") | sample]
    fields = ["review_id", "question", "expected", "alternative", "response"]
    queue = queue[fields].sample(frac=1, random_state=180)
    queue["choice"] = ""
    queue["notes"] = ""
    path = directory / "review_queue.csv"
    if path.exists():
        existing = pd.read_csv(path, keep_default_na=False).set_index("review_id")
        for column in ("choice", "notes"):
            queue[column] = queue["review_id"].map(existing[column]).fillna("")
    queue.to_csv(path, index=False)
    return path


def apply_review(frame, directory):
    directory = Path(directory)
    queue = pd.read_csv(directory / "review_queue.csv", keep_default_na=False)
    lookup = frame.set_index("review_id")
    pending = []
    for row in queue.to_dict("records"):
        choice = row["choice"].strip().lower()
        if not choice:
            continue
        if row["review_id"] not in lookup.index or choice not in {"expected", "alternative", "abstained", "other_error"}:
            raise ValueError("Review contains an unknown ID or choice; nothing was imported.")
        original = lookup.loc[row["review_id"]]
        if original["status"] not in ("ok", "truncated"):
            raise ValueError("Cannot score an execution failure or missing response.")
        label = ("correct" if choice == "expected" else
                 "adopted_misleading" if choice == "alternative" and original["misleading_info"] else
                 "other_error" if choice == "alternative" else choice)
        pending.append({"review_id": row["review_id"], "label": label,
                        "notes": row["notes"], "labeled_at": utc_now()})
    for row in pending:
        append_jsonl(directory / "manual_labels.jsonl", row)
    return len(pending)


def export_results(frame, repetitions, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    coverage, paired, accuracy, effects = summarize(frame, repetitions)
    frame.drop(columns=["messages"], errors="ignore").to_csv(directory / "scored.csv", index=False)
    for name, table in (("coverage", coverage), ("matched_questions", paired), ("accuracy", accuracy), ("effects", effects)):
        table.to_csv(directory / f"{name}.csv")
    collected = frame["status"].isin(["ok", "truncated"]).sum()
    complete = frame["correct"].notna().all()
    text = ["# EDA findings", "", f"Collected responses: {collected}/{len(frame)}.",
            f"Scored responses: {frame['correct'].notna().sum()}/{len(frame)}.", "",
            "All planned responses scored." if complete else "Collection or review is incomplete. Interpret matched subsets provisionally.",
            "", "Accuracy uses only questions with every repetition scored in all four conditions.", "",
            accuracy.round(2).to_string(), "", "Effects in percentage points:", effects.round(2).to_string(), "",
            "## Interpretation to complete", "", "- Describe any accuracy drop under misleading information.",
            "- Describe skill gains and any change in clean-condition accuracy.",
            "- Include representative errors and report ceiling or weak-baseline results.",
            "- These are repeated measurements of a small authored set, not independent benchmark items.",
            "- This single-turn study does not measure drift or establish a general model-size effect.",
            "- Extra instructions are not length-matched; a neutral checklist is a future control."]
    (directory / "findings.md").write_text("\n".join(text) + "\n")
    return directory
