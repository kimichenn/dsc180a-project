# Jeremy's EDA

Run [eda.py](eda.py) from a terminal, or open the original [eda.ipynb](eda.ipynb).
They implement the smaller-model study on the `jeremy/eda` branch, using
Qwen3-1.7B and Qwen3-4B in non-thinking mode. [test.py](test.py) is the terminal
version of the CUDA check in `test.ipynb`.

- **Pilot:** 5 questions × 4 conditions × 2 models × 1 repetition = 40 responses.
- **Evaluation:** 100 separate questions × 4 conditions × 2 models × 3 repetitions
  = 2,400 responses. E01–E20 are hand-written; E21–E100 come from
  `data/generate_questions.py` (seeded, rerunnable).
- **Conditions:** clean/misleading context crossed with no skill/skill.

The dataset combines hand-written questions and seeded generated variants.
Answer keys are computed from explicit rules. Every calculation question changes the ordering of the original values.
No model responses are bundled or fabricated. Running `eda.py` without
`--collect` validates the design and exports analysis of any saved responses.

## Setup

Create a dedicated Python 3.11–3.13 environment, install `requirements.txt`, and
select it as the notebook kernel. For example, from this folder:

```bash
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m jupyterlab eda.ipynb
```

The runner uses local Hugging Face Transformers, with CUDA, Apple MPS, or CPU.
It loads one model at a time. It uses unquantized weights and therefore needs
sufficient memory for the selected checkpoint; CPU inference can be slow.
The first enabled collection downloads weights. It does not provision a GPU or
call a hosted paid API. Qwen3 requires Transformers 4.51 or later; an older
installation can run the EDA cells but cannot collect Qwen3 responses.

## Run the scripts

From the repository root, using the Python environment with `requirements.txt` installed:

```bash
# Check CUDA and save eda_results/environment.json.
python eda/jeremy/test.py

# Save dataset tables, coverage, analysis CSVs, and PNG plots.
python eda/jeremy/eda.py

# Collect the first two real responses, then export analysis.
python eda/jeremy/eda.py --collect --max-new-trials 2

# Resume and finish the pilot, skipping completed responses.
python eda/jeremy/eda.py --collect
```

The scripts resolve inputs and their default output folder relative to their own
location, so they also work when launched from another directory. Results go to
`eda_results/<run-name>/` at the repository root (`pilot_v1` by default).
Figures are saved under `plots/`; no graphical display or notebook kernel is needed.
Dataset and coverage plots are always saved. Accuracy and question-change plots
appear when complete matched scores exist; error plots appear when errors exist.
Generated outputs are ignored by Git. Original notebooks remain available.

Edit `choice` and `notes` in `eda_results/pilot_v1/review_queue.csv`, then run:

```bash
python eda/jeremy/eda.py --import-review
```

After reviewing the pilot, collect the evaluation with:

```bash
python eda/jeremy/eda.py --phase evaluation --collect --pilot-reviewed
```

Use `--run-name NAME` for a new run, `--results-dir PATH` to change the output
folder, and `--help` for all options. `--max-new-trials` requires `--collect`.
Tables, plots, and the generated `findings.md` draft are refreshed on each run;
keep handwritten interpretation in a separate file. Raw responses and imported
manual labels remain append-only.

Legacy notebook runs remain under `eda/jeremy/runs/`; they are not automatically
copied into `eda_results`. To analyze them, pass `--results-dir eda/jeremy/runs`.
Frozen runs reject collection after helper-code changes; use a new run name for
new collection after helper changes. Existing runs can still be analyzed: their
question tables, model tables, prompt previews, and scores use the frozen design.
Older runs therefore retain their original model choices and question counts.

## Run the notebook

1. Run the notebook with its defaults and inspect the question calculations,
   matched prompt preview, and dataset plots. Collection is off by default, and
   analysis works without CUDA. Existing run names display their frozen design.
2. Keep `PHASE="pilot"` and `RUN_NAME="pilot_v1"`. In section 6, set
   `RUN_COLLECTION=True`. Optionally use `MAX_NEW_TRIALS=2` for a smoke run,
   then set it to `None` and rerun that cell to finish.
3. Export the review queue in section 8. Edit only `choice` and `notes`, using
   `expected`, `alternative`, `abstained`, or `other_error`; import the choices
   and rerun the analysis cells. Every ambiguous/error response and a fixed 10%
   correct sample goes to review. The queue omits model/condition identifiers.
4. Review the pilot, document revisions, and freeze the final skill and questions.
   Use a new pilot run name after changing inputs. Keep the 100 evaluation items
   out of skill tuning.
5. Set `PHASE="evaluation"`, `RUN_NAME="evaluation_v1"`, and
   `PILOT_REVIEWED=True`. Run the collection and review steps again.
6. In section 13, set `EXPORT_RESULTS=True` and complete the generated findings
   draft using the tables and response examples. Reset collection to `False`
   when only analyzing results.

Collection freezes checkpoint commits, tokenizer-template hashes, prompts,
questions, skill, settings, runtime, and helper-code hash. Resume uses the frozen
checkpoint and refuses changed inputs/runtime. Each attempt is saved immediately.
Successful and truncated responses are not regenerated. Execution failures have
a total limit of three attempts across resumes. A run lock prevents two kernels
from writing the same run at once; after a kernel crash, remove a stale
`runs/<run>/.collecting` only after checking no collection is active.

## Files

| File | Purpose |
|---|---|
| `eda.py`, `eda.ipynb` | Main workflow, prompt previews, tables, and plots |
| `test.py`, `test.ipynb` | CUDA availability check |
| `../../eda_results/environment.json` | Script environment check |
| `../../eda_results/<name>/` | Script tables, review queue, findings draft, and collected responses |
| `../../eda_results/<name>/plots/` | Saved PNG figures |
| `study.py` | Collection, conservative scoring, review, and aggregation |
| `config.json` | Model selection and fixed generation settings |
| `skill.md` | Reusable instruction block |
| `data/scenarios.json` | 5 pilot and 100 evaluation scenarios |
| `data/generate_questions.py` | Regenerates evaluation items E21–E100 |
| `runs/<name>/manifest.json` | Frozen design and provenance, created on collection |
| `runs/<name>/responses.jsonl` | Append-only attempts with complete prompts and raw responses |
| `runs/<name>/review_queue.csv` | Editable blinded review choices |
| `runs/<name>/manual_labels.jsonl` | Manual decisions tied to exact responses |
| `runs/<name>/*.csv`, `findings.md` | Exported analysis and interpretation draft |

Accuracy excludes questions until every repetition in all four conditions is
scored. Missing data stay missing, not zero. Always report coverage alongside
accuracy. Repetitions are averaged within questions; the 100 questions are the
main comparison units. This first study measures single-turn accuracy, not drift.

The `matches_misleading` outcome means only that the final answer matches the
answer implied by the misleading value. It does not establish that the model
adopted that claim: skipping the calculation can produce the same answer. Old
`adopted_misleading` manual labels are interpreted as `matches_misleading` during
analysis without rewriting the saved decisions.

Report misleading-condition skill gain (`D − B`) alongside clean-condition gain
(`C − A`) and the interaction (`(A − B) − (C − D)`). A positive interaction can
come from lower clean-with-skill accuracy, even when misleading-condition
accuracy does not improve; it is not sufficient on its own to claim protection.

## Offline verification

From the repository root:

```bash
python -m unittest discover -s eda/jeremy/tests -v
```

Tests use a deterministic fake backend only in temporary directories. They check
dataset invariants, conservative final-answer scoring, missing-data handling,
matched comparisons, immutable resumes, retry limits, legacy label compatibility,
and manual review. They also check frozen-design exports, notebook defaults without
CUDA, chart limits, and compatible model-loading arguments. They make no network
requests and do not produce study results.

## Sources

- [Qwen3-1.7B model card](https://huggingface.co/Qwen/Qwen3-1.7B)
- [Qwen3-4B model card](https://huggingface.co/Qwen/Qwen3-4B)
- [Transformers generation documentation](https://huggingface.co/docs/transformers/main_classes/text_generation)
