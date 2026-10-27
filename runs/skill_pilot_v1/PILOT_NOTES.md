# General conflict-resolution skill: exploratory pilot v1

Prepared on 2026-10-25 before collecting pilot responses. This is development data,
not a confirmatory run. Seeds 610000-610004 must never enter the main study.

## Candidate and predictions

The candidate is the domain-general instruction in `experiment/prompts.py`, copied
verbatim into the hashed `system/skill.txt`. It covers authority, reference chains,
withdrawals/reinstatements, constructing the effective state, and checking the answer.
No budget examples, Finance-specific rules, or distinctive-amount tricks are included.

Before observing this batch: expect improvement on R and RG if explicitly resolving
validity helps. No improvement is required on C/E, but record any deterioration.
Arithmetic errors may remain even when validity is resolved correctly. The instruction
allows stating unresolved uncertainty; monitor missing ANSWER lines and score them wrong.

## Collection and interpretation

- Five new 1,600-record logs; C/R/RG/E; no skill and skill; one repeat in every cell.
- 40 planned calls per model. Start with GPT-6 Astra at low effort. Claude's login
  failed the access check; its 40 planned calls remain uncollected for now.
- Independent fresh sessions, identical base prompts, tools disabled, exact input
  hashes recorded, earliest eligible completed attempt counted. Never rerun wrong answers.
- Report per-version paired gains and the per-log average gain across R and RG.
  With five logs and one repeat, these are descriptive development results only.
- This batch checks format, output length, and preliminary accuracy. It does not
  establish repeatability, statistical efficacy, or transfer to another task.
- Keep this candidate fixed throughout the batch. Any revision uses a new run name.

## Known differences from the v2 proposal

This run uses the existing generator from the branch's base commit. It uses final
activity status when choosing change signs and gossip anchors. Final answers still
agree across all versions and both solvers, but intermediate budget paths are not
guaranteed to respect the configured range. A straightforward chronological fix with
whole-log rejection failed to produce a valid 1,600-record world in the first 10,000
candidate attempts for seed 610000. That experimental change was reverted before
preparing this run. Resolve and validate this generator issue before the final study.

The existing `analyze` command implements the older main-study comparisons and causal
bucket names. Use `pilot-report` for this run's descriptive accuracy comparison;
do not interpret those legacy bucket names as mechanisms. The v2 two-tier repeats,
updated confirmatory statistics, and final freeze guard remain future work.

This run was prepared from an uncommitted development branch (recorded in the manifest).
The manifest hashes the actual prompts, logs, answer keys, and schedule.

## Follow-up generator diagnostic (no model outcomes used)

The separate chronological rejection-sampling diagnostic eventually accepted its
first world at attempt 19,711 (76.6 seconds for that seed), compared with the existing
200-attempt cap. This establishes a practical retry-limit problem, not impossibility.
The diagnostic did not change the frozen pilot inputs. Replaying those inputs confirms
that all five can leave the intended range; the respective min/max values in $K are
(-2891, 5517), (-3218, 5316), (-783, 9846), (-403, 9172), and (-5061, 6690).
Keep conclusions specific to this legacy-generator pilot. A corrected-generator pilot
is needed before freezing the main study.
