# Jeremy's EDA

Open [eda.ipynb](eda.ipynb). It implements the smaller-model study on the
`jeremy/eda` branch, using Qwen3-4B and Qwen3-8B in non-thinking mode.

- **Pilot:** 5 questions × 4 conditions × 2 models × 1 repetition = 40 responses.
- **Evaluation:** 20 separate questions × 4 conditions × 2 models × 3 repetitions
  = 480 responses.
- **Conditions:** clean/misleading context crossed with no skill/skill.

The dataset is hand-authored and the answer keys are computed from explicit
rules. Every calculation question changes the ordering of the original values.
No model responses are bundled or fabricated. Running the notebook with its
defaults only validates and explores the design.

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

## Run the study

1. Run the notebook with its defaults and inspect the question calculations,
   matched prompt preview, and dataset plots.
2. Keep `PHASE="pilot"` and `RUN_NAME="pilot_v1"`. In section 6, set
   `RUN_COLLECTION=True`. Optionally use `MAX_NEW_TRIALS=2` for a smoke run,
   then set it to `None` and rerun that cell to finish.
3. Export the review queue in section 8. Edit only `choice` and `notes`, using
   `expected`, `alternative`, `abstained`, or `other_error`; import the choices
   and rerun the analysis cells. Every ambiguous/error response and a fixed 10%
   correct sample goes to review. The queue omits model/condition identifiers.
4. Review the pilot, document revisions, and freeze the final skill and questions.
   Use a new pilot run name after changing inputs. Keep the 20 evaluation items
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
| `eda.ipynb` | Main workflow, prompt previews, tables, and plots |
| `study.py` | Collection, conservative scoring, review, and aggregation |
| `config.json` | Model selection and fixed generation settings |
| `skill.md` | Reusable instruction block |
| `data/scenarios.json` | 5 pilot and 20 evaluation scenarios |
| `runs/<name>/manifest.json` | Frozen design and provenance, created on collection |
| `runs/<name>/responses.jsonl` | Append-only attempts with complete prompts and raw responses |
| `runs/<name>/review_queue.csv` | Editable blinded review choices |
| `runs/<name>/manual_labels.jsonl` | Manual decisions tied to exact responses |
| `runs/<name>/*.csv`, `findings.md` | Exported analysis and interpretation draft |

Accuracy excludes questions until every repetition in all four conditions is
scored. Missing data stay missing, not zero. Always report coverage alongside
accuracy. Repetitions are averaged within questions; the 20 questions are the
main comparison units. This first study measures single-turn accuracy, not drift.

## Offline verification

From the repository root:

```bash
python -m unittest discover -s eda/jeremy/tests -v
```

Tests use a deterministic fake backend only in temporary directories. They check
dataset invariants, conservative final-answer scoring, missing-data handling,
matched comparisons, immutable resumes, retry limits, and manual review. They
make no network requests and do not produce study results.

## Sources

- [Qwen3-4B model card](https://huggingface.co/Qwen/Qwen3-4B)
- [Qwen3-8B model card](https://huggingface.co/Qwen/Qwen3-8B)
- [Transformers generation documentation](https://huggingface.co/docs/transformers/main_classes/text_generation)
