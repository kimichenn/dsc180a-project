# Frozen GPT repeat study: 10 repeats everywhere

The user selected ten repetitions of every question/version/instruction combination
on 2026-10-25, replacing the earlier three-repeat / ten-repeat tier design.

## Design fixed before collection

- GPT-6 Astra at low reasoning effort, through the existing isolated Codex client.
- Thirty new underlying logs, seeds 720000-720029, 1,600 records each.
- Versions C, R, RG, E; the same general skill v1 either absent or present.
- Ten identical-prompt repetitions in every condition: 2,400 calls, 80 per log.
- Skill wording is unchanged from the pilot, with its SHA-256 in the config.
- Randomized order within each log; collect log by log. Fresh sessions, no tools.
- Collection starts with up to ten simultaneous calls, paced at six starts per minute.
  This was selected before collection; rate-limit or capacity errors stop collection.
- All five skill-pilot logs and the earlier trial remain development data, excluded.
- No Claude collection is included; the user previously selected GPT only.

The thirty untested worlds were initially generated for a two-tier schedule while
the user clarified the repetition count. No model responses were collected on them.
Only their repeat schedule changes for this run; all worlds are revalidated before collection.

## Generator correction

The chronological generator counts a change immediately, applies each withdrawal
when it arrives, and restores changes when withdrawals are withdrawn. A withdrawal's
arrival effect is the negative of its target's effect; this relies on the existing
rule that a record can be targeted at most once. Whole candidates are rejected if
any chronological total leaves $200K-$3,000K. The retry cap is 500,000 candidates per
seed because 200 retries were insufficient. No model outcomes guide generation.

Two independent solvers must agree across every version, including text round-trip
checks. Unique amounts are retained. For the chronological generator, overlapping
error signatures no longer reject an otherwise valid log. The old exclusive error
bucket names may remain in raw collector output; this study reports correctness,
signed numerical error, and neutral response status instead of treating those labels
as established causes. The known distinctiveness of special amounts limits transfer.

## Predictions and analysis

The candidate may improve withdrawal conditions by separating source authority and
revision resolution from answer construction. This is a hypothesis, not established
by the development pilot (R decreased, RG increased). Arithmetic errors may remain.
C/E check for general improvements and degradation. No neutral-instruction control
is present, so gains cannot establish a procedure-specific mechanism.

The primary contrasts for this GPT-only run are H1: E minus R without the skill;
and H2: skill minus no skill averaged equally over R and RG per log. All ten repeats
are averaged within a log before these comparisons. The independent sample size is
30 logs, not 2,400 calls. Use only logs with all 80 eligible responses for primary
analysis; report incomplete collection separately. Reports produced before completion
are descriptive, and results never trigger early stopping or prompt revisions.

Report paired percentage-point effects, 95% percentile bootstrap intervals using
10,000 whole-log resamples, and two-sided sign-flip tests (exact for at most twenty
nonzero differences; otherwise 100,000 flips). Holm correction covers the two primary
GPT tests. The sign-flip test assumes symmetry of log differences under the null.
A cell with every log perfect also reports a one-sided 95% upper bound on the probability
that a log has any error across its ten repetitions. All-perfect bootstrap intervals
alone are not evidence of zero uncertainty. Individual condition gains are descriptive.

For repeatability, report each prompt's correct count out of ten, the distribution
of those counts across logs, and the share of all 45 response pairs with the same
numeric answer. Missing numbers never count as a matching pair. Identical wrong
answers show repeatable output, not a proven failure mechanism.

## Stopping, retries, and provenance

Target 2,400 eligible completed responses. Stop for subscription/authentication issues,
a failed isolation audit, or the collector's repeated infrastructure failures; do not
change settings or reduce the target after seeing answers. Resume the same frozen run
when the external issue is resolved. Completed wrong/missing answers count as wrong
and are never retried. Interrupted/no-response requests remain pending. Preserve any
ineligible response and its audit record; it is not a clean trial of this protocol.

All inputs, schedules, skill text, configuration, this protocol, and execution sources
are hashed in the manifest. Source changes block collection until the frozen source is
restored. This content snapshot freezes uncommitted development changes as well as the
base commit; it does not claim that the working tree was clean or committed.
