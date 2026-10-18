"""Terminal version of eda.ipynb; save tables and plots under eda_results.

Run analysis: python eda/jeremy/eda.py
Collect two responses: python eda/jeremy/eda.py --collect --max-new-trials 2
"""

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_RESULTS_DIR = ROOT.parents[1] / "eda_results"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["pilot", "evaluation"], default="pilot")
    parser.add_argument("--run-name", help="Default: <phase>_v1")
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR,
                        help="Default: repository-root/eda_results")
    parser.add_argument("--collect", action="store_true", help="Download/load models and collect responses")
    parser.add_argument("--max-new-trials", type=int, help="Limit collection; omit to finish the phase")
    parser.add_argument("--pilot-reviewed", action="store_true", help="Confirm pilot review before evaluation collection")
    parser.add_argument("--import-review", action="store_true", help="Import choices from this run's review_queue.csv")
    parser.add_argument("--preview-question", help="Default: P03 for pilot, E01 for evaluation")
    parser.add_argument("--preview-condition", choices=list("ABCD"), default="D")
    args = parser.parse_args(argv)
    if args.max_new_trials is not None:
        if args.max_new_trials < 1:
            parser.error("--max-new-trials must be positive")
        if not args.collect:
            parser.error("--max-new-trials requires --collect")
    if args.collect and args.phase == "evaluation" and not args.pilot_reviewed:
        parser.error("Review the pilot and pass --pilot-reviewed before evaluation collection")
    args.run_name = args.run_name or f"{args.phase}_v1"
    args.preview_question = args.preview_question or ("P03" if args.phase == "pilot" else "E01")
    args.results_dir = args.results_dir.expanduser().resolve()
    return args


def main(argv=None):
    args = parse_args(argv)

    # 1. Load the study
    import importlib.metadata
    import matplotlib

    # Save figures on servers without a graphical display.
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pandas as pd
    import study

    # A saved run's tables and previews must describe the same inputs as its scores.
    design = study.load_run_design(ROOT, args.phase, args.run_name, results_root=args.results_dir)
    questions, config, skill = design["questions"], design["config"], design["skill"]
    if args.preview_question not in {t["question_id"] for t in design["trials"]}:
        raise ValueError(f"Preview question {args.preview_question} is not in the selected phase.")
    # Validate an existing run's phase before writing exports.
    study.load_results(ROOT, args.phase, args.run_name, results_root=args.results_dir)
    run_dir = study.run_path(ROOT, args.run_name, results_root=args.results_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    plots_dir = run_dir / "plots"
    plots_dir.mkdir(exist_ok=True)

    def display(table):
        print(table.to_string())
        print()

    def save_plot(name):
        figure = plt.gcf()
        figure.savefig(plots_dir / f"{name}.png", dpi=150, bbox_inches="tight")
        plt.close(figure)

    plt.rcParams.update({"figure.dpi": 110, "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False})
    pd.set_option("display.max_colwidth", 110)
    print(f"Study folder: {ROOT}")
    print(f"Results folder: {run_dir}")
    print(f"Loaded {len(questions)} questions from the selected design.")

    # 2. Choose the phase and inspect the design
    PHASE = args.phase
    RUN_NAME = args.run_name
    PILOT_REVIEWED = args.pilot_reviewed

    trials = design["trials"]
    plan = pd.DataFrame(trials)
    print(f"Selected phase: {PHASE} | Planned responses: {len(plan)}")
    sizes = []
    for phase in ("pilot", "evaluation"):
        n_questions = sum(q["phase"] == phase for q in questions)
        reps = config["repetitions"][phase]
        n_trials = n_questions * len(study.CONDITIONS) * len(config["models"]) * reps
        sizes.append(f"{phase.title()}: {n_questions} × {len(study.CONDITIONS)} × "
                     f"{len(config['models'])} × {reps} = {n_trials}")
    print(" | ".join(sizes))
    display(pd.DataFrame(config["models"]).T)
    display(pd.DataFrame(study.CONDITIONS).T.rename_axis("condition"))
    print("Thinking mode:", config["enable_thinking"])
    print("Generation settings:", config["generation"])
    pd.DataFrame(config["models"]).T.to_csv(run_dir / "models.csv")
    pd.DataFrame(study.CONDITIONS).T.rename_axis("condition").to_csv(run_dir / "conditions.csv")

    # 3. Explore and verify the question set
    question_rows = []
    for q in questions:
        question_rows.append({
            **q,
            "expected": study.answer_key(q),
            "misleading_answer": study.answer_key(q, misleading=True),
            "answer_without_calculation": study.answer_key(q, basic=True),
            "calculated_a": study.calculate(q["correct_value"], q["operation"], q["parameter_a"]),
            "calculated_b": study.calculate(q["other_value"], q["operation"], q["parameter_b"]),
            "question_words": len(q["question"].split()),
        })
    question_df = pd.DataFrame(question_rows)
    display(question_df.groupby(["phase", "subtype", "difficulty"]).size().rename("questions").to_frame())
    display(question_df[["question_id", "phase", "domain", "difficulty", "question", "expected"]].head(10))

    calculation_checks = question_df.loc[question_df.difficulty.eq("calculation"), [
        "question_id", "entity_a", "entity_b", "calculation_rule", "calculated_a", "calculated_b",
        "expected", "answer_without_calculation", "misleading_answer",
    ]]
    display(calculation_checks)
    question_df.to_csv(run_dir / "questions.csv", index=False)
    calculation_checks.to_csv(run_dir / "calculation_checks.csv", index=False)
    question_df.groupby(["phase", "subtype", "difficulty"]).size().rename("questions").to_csv(run_dir / "question_balance.csv")

    evaluation_questions = question_df.loc[question_df.phase.eq("evaluation")]
    balance = pd.crosstab(evaluation_questions.subtype, evaluation_questions.difficulty)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    balance.plot.bar(ax=axes[0], color=["#4776B4", "#50A18B"], rot=0)
    axes[0].set(title="Evaluation question balance", xlabel="Conflict subtype", ylabel="Questions")
    axes[0].legend(title="Difficulty", frameon=False)
    evaluation_questions.domain.value_counts().sort_values().plot.barh(ax=axes[1], color="#4776B4")
    axes[1].set(title="Evaluation domains", xlabel="Questions", ylabel="")
    fig.tight_layout()
    save_plot("dataset_overview")
    print("These plots describe the authored dataset, not model performance.")

    # 4. Inspect matched prompts and the reusable skill
    PREVIEW_QUESTION = args.preview_question
    PREVIEW_CONDITION = args.preview_condition
    preview_messages = {
        condition: next(t["messages"] for t in trials
                        if t["question_id"] == PREVIEW_QUESTION and t["condition"] == condition)
        for condition in study.CONDITIONS
    }
    print("Reusable skill:\n" + skill)
    print("\nPrompt preview:")
    for message in preview_messages[PREVIEW_CONDITION]:
        print(f"\n[{message['role']}]\n{message['content']}")
    preview_text = "Reusable skill:\n" + skill + "\n\nPrompt preview:\n"
    for message in preview_messages[PREVIEW_CONDITION]:
        preview_text += f"\n[{message['role']}]\n{message['content']}\n"

    # Inspect just the clean/misleading change. This does not call a model.
    import difflib
    clean = preview_messages["A"][1]["content"]
    misleading = preview_messages["B"][1]["content"]
    print("\n".join(difflib.unified_diff(clean.splitlines(), misleading.splitlines(),
                                         fromfile="clean", tofile="misleading", lineterm="")))
    preview_text += "\n" + "\n".join(difflib.unified_diff(
        clean.splitlines(), misleading.splitlines(), fromfile="clean", tofile="misleading", lineterm="",
    ))
    (run_dir / "prompt_preview.txt").write_text(preview_text + "\n", encoding="utf-8")

    # 5. Check the environment before collection
    versions = {}
    for package in ["pandas", "matplotlib", "torch", "transformers", "accelerate", "huggingface-hub"]:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "not installed"
    version_table = pd.Series(versions, name="installed_version").to_frame()
    display(version_table)
    version_table.to_csv(run_dir / "environment.csv")
    print("Before collection: transformers >= 4.51, accelerate, PyTorch, network access for uncached weights,")
    print("and enough memory for the selected unquantized checkpoint are required.")

    # 6. Collect the selected phase (explicit opt-in)
    RUN_COLLECTION = args.collect
    MAX_NEW_TRIALS = args.max_new_trials

    if RUN_COLLECTION:
        study.collect(ROOT, PHASE, RUN_NAME, pilot_reviewed=PILOT_REVIEWED,
                      max_new_trials=MAX_NEW_TRIALS, results_root=args.results_dir)
    else:
        print(f"Analysis only. Pass --collect to collect {PHASE} responses.")
        print("No weights downloaded and no model responses generated by this script.")

    # 7. Load results
    results, frozen_config = study.load_results(ROOT, PHASE, RUN_NAME, results_root=args.results_dir)
    repetitions = frozen_config["repetitions"][PHASE]
    coverage, matched, accuracy, effects = study.summarize(results, repetitions)

    # 8. Import manual scores and export the review queue
    if args.import_review:
        print("Manual labels imported:", study.apply_review(results, run_dir))
        results, frozen_config = study.load_results(ROOT, PHASE, RUN_NAME, results_root=args.results_dir)
        coverage, matched, accuracy, effects = study.summarize(results, repetitions)

    print("Review file:", study.export_review(results, run_dir))

    # Remove obsolete generated charts/tables when review changes their inputs.
    for name in ("accuracy", "question_changes", "error_types"):
        (plots_dir / f"{name}.png").unlink(missing_ok=True)
    for name in ("paired_changes", "error_counts", "category_summary"):
        (run_dir / f"{name}.csv").unlink(missing_ok=True)

    review_needed = results.loc[results.status.isin(["ok", "truncated"]) & results.label.isna()]
    print(f"Responses requiring manual scoring: {len(review_needed)}")
    if len(review_needed):
        display(review_needed[["review_id", "question", "response", "review_reason"]].head(8))

    # Check collection coverage
    display(coverage)
    print(f"Collected: {results.status.isin(['ok', 'truncated']).sum()}/{len(results)}")
    progress = pd.DataFrame({
        "Scored": coverage.scored,
        "Awaiting review": coverage.awaiting_review,
        "Execution error": coverage.execution_errors,
        "Not collected": coverage.planned - coverage.collected - coverage.execution_errors,
    })
    progress.index = [f"{model} / {condition}" for model, condition in progress.index]
    ax = progress.plot.barh(stacked=True, figsize=(9, 4.5),
                            color=["#50A18B", "#E6B35A", "#C76666", "#DDE2E8"])
    ax.set(title=f"{PHASE.title()} collection progress", xlabel="Response slots", ylabel="")
    ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left", frameon=False)
    plt.tight_layout()
    save_plot("collection_progress")

    # 9. Summarize accuracy and paired effects
    coverage, matched, accuracy, effects = study.summarize(results, repetitions)
    display(accuracy.round(2))
    display(effects.round(2))
    if matched.empty:
        print("Accuracy and effects are pending: no question has complete scores in all four conditions.")
    else:
        print(f"Matched model-question pairs: {len(matched)}")
        if results.correct.isna().any():
            print("Collection/review remains incomplete. These are provisional matched-subset results.")

    # 10. Plot accuracy by condition and model
    if not matched.empty:
        ax = accuracy[list(study.CONDITIONS)].T.plot.bar(figsize=(9, 4.5), rot=0,
                                                       color=["#4776B4", "#50A18B"])
        ax.set(ylim=(0, 110), title="Accuracy on matched questions", xlabel="Condition", ylabel="Correct (%)")
        ax.legend(title="Model", frameon=False)
        print("Matched questions per model:", accuracy.questions.astype(int).to_dict())
        plt.tight_layout()
        save_plot("accuracy")
    else:
        print("Accuracy plot pending real, fully scored responses.")

    # 11. Inspect changes question by question
    if not matched.empty:
        paired_changes = matched.reset_index()
        paired_changes["misleading_drop_pp"] = 100 * (paired_changes.A - paired_changes.B)
        paired_changes["skill_gain_pp"] = 100 * (paired_changes.D - paired_changes.B)
        paired_changes.to_csv(run_dir / "paired_changes.csv", index=False)
        models_with_data = paired_changes.model.unique()
        fig, axes = plt.subplots(1, len(models_with_data), figsize=(6 * len(models_with_data), 6), squeeze=False)
        for ax, model in zip(axes.flat, models_with_data):
            subset = paired_changes.loc[paired_changes.model.eq(model)].sort_values("question_id")
            y = list(range(len(subset)))
            ax.scatter(subset.misleading_drop_pp, [i + .12 for i in y], label="Misleading drop (A−B)", color="#C76666")
            ax.scatter(subset.skill_gain_pp, [i - .12 for i in y], label="Skill gain (D−B)", marker="s", color="#4776B4")
            ax.axvline(0, color="#999999", linewidth=1)
            ax.set_yticks(y, subset.question_id)
            ax.set(title=model, xlabel="Percentage points", xlim=(-110, 110), ylabel="Question")
            ax.legend(loc="best", fontsize=8, frameon=False)
        fig.tight_layout()
        save_plot("question_changes")
    else:
        print("Question-change plots pending completed question-condition pairs.")

    # 12. Explore error types and categories
    scored = results.loc[results.label.notna()]
    errors = scored.loc[scored.label.ne("correct")]
    errors.drop(columns=["messages"], errors="ignore").to_csv(run_dir / "errors.csv", index=False)
    if scored.empty:
        print("No scored responses yet; error analysis is pending.")
    elif errors.empty:
        print("No incorrect responses among the observations scored so far.")
    else:
        counts = pd.crosstab(errors.model, errors.label)
        counts.to_csv(run_dir / "error_counts.csv")
        ax = counts.plot.bar(figsize=(9, 4), rot=0)
        ax.set(title="Observed error types", xlabel="Model", ylabel="Responses (includes repetitions)")
        ax.legend(title="Outcome", frameon=False)
        plt.tight_layout()
        save_plot("error_types")
        display(errors[["question_id", "model", "condition", "expected", "alternative", "response", "label"]].head(10))

    if not matched.empty:
        groups = matched.reset_index().groupby(["model", "subtype", "difficulty"])
        category_summary = groups[list(study.CONDITIONS)].mean() * 100
        category_summary.insert(0, "questions", groups.size())
        display(category_summary.round(1))
        category_summary.to_csv(run_dir / "category_summary.csv")

    # 13. Export results
    print("Exports saved:", study.export_results(results, repetitions, run_dir))

    print(f"Run: {RUN_NAME}; phase: {PHASE}")
    print(f"Scored responses: {results.correct.notna().sum()}/{len(results)}")
    if matched.empty:
        print("Finding so far: dataset prepared; no model accuracy results are available.")
    else:
        display(effects.round(2))
        print("Use the tables and response examples to write your findings. findings.md is a regenerated draft.")


if __name__ == "__main__":
    main()
