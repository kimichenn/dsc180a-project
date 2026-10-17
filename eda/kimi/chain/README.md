# v5: budget chains (`chain/`)

Each prompt is a policy, a numbered log of N records about one fictional project's budget (in $K), and one question: "What is <project>'s budget now?" Only the Finance Office changes the budget; messages from other offices ("notes") do not. The Finance Office can withdraw an earlier update, and a withdrawal can itself be withdrawn. Every chain has a matched **control** version with the same N, the same official updates, and the same answer: notes, withdrawals, and withdrawn updates become harmless records from the same author ("kickoff moved to Building 4"). The gap between the two versions is the result.

Run every command from `eda/kimi`. The write-up is [reports/v5/findings.md](../reports/v5/findings.md).

| Step | Command |
| --- | --- |
| Hand chains vs the resolver, then the generator checks on 1,000 seeds at N 20 / 200 / 800 | `python -m chain validate` |
| Read one chain pair, its answer, lures, and a record-by-record trace | `python -m chain preview --seed 1 --n 30 [--profile P0]` |
| One small call per model: login, isolation, right answer | `python -m chain check-models` |
| Break phase, see the plan and cost | `python -m chain run break --dry-run` |
| Break phase (N 20-800, seeds 1-5, both versions) | `python -m chain run break [--profile P0] [--levels ...]` |
| Tables, figure, break points, and the decision rule, which prints the next command | `python -m chain analyze results/v5/break_P0` |
| Sweep phase (fresh seeds from 1001, 30 per level) | the command `analyze` prints once every flagship breaks |

- **Models and billing.** [config/v5_models.toml](../config/v5_models.toml) runs GPT through `codex exec` on the ChatGPT login and Claude through `claude -p` on the Claude login ([harness/subscriptions.py](../harness/subscriptions.py)), so no call bills an API key. Each call replaces the agent's system prompt with ours, has no tools, loads none of your CLAUDE.md / AGENTS.md / skills / plugins / MCP servers, runs in an empty folder, and gets an environment with API keys removed. Everything runs at `low`, the lowest reasoning level the flagships allow.
- **Budget.** API-billed providers (`openai`, `anthropic`, `google`) count against a $10 cap summed over every run under `results/v5`. Before each billed call the runner reserves its worst case, so the cap holds with calls in flight. The v5 config has no billed models.
- **Usage limits.** When a subscription hits its limit, the runner stops that model after three errors in a row. Rerun the same command later; finished calls are skipped.
- **Profiles.** Every setting except N lives in a profile ([dials.py](dials.py)). Escalation, used only if a flagship survives the largest N: P0 → P1 (withdrawals named by date and kind) → P2 (5 interleaved projects) → P3 (answer line only).
- **Validation data.** The 10 hand chains in [data/v5/hand_chains.json](../data/v5/hand_chains.json) each exercise one rule. Each has an `expected` answer worked out by hand from its lines (not by the resolver), with the steps in `work`; these were drafted by Claude and still need a person to check them. `validate` fails while any `expected` is blank and never prints the resolver's answer for a blank chain.
- **Run directories.** `chains/` (every chain pair with its answer, lures, and per-record flags), `responses.jsonl` (raw responses, including a first attempt that lacked an ANSWER line), `manifest.json`, and after `analyze`: `report.txt`, `accuracy_vs_n.png`, `errors.csv`, `scored.csv`, `failures.md`.

**How a chain is guaranteed correct:**
- The generator is deterministic: the same (N, seed) always gives the same chain, and profiles that change only wording (P0, P1, P3) share chains.
- The answer never comes from the generator's plan. The resolver ([resolver.py](resolver.py)) applies the policy: status runs from the newest record backward (a counting record is active unless an active withdrawal targets it), then the active updates are folded in order.
- [checks.py](checks.py) reads the rendered text back using only the policy's wording, resolves it, and requires the same answer for both versions. It also requires that every lure differs from the answer, that at least one note and one withdrawal change the answer, that withdrawal targets exist and come earlier, that dates strictly increase, and that the true budget stays within $200K-$3,000K. The generator resamples until every check passes.

**Where the code interprets the plan:**
- **`relative_rate` is 1.0** (the plan said 0.80): only #001 sets the budget. An active set erases every earlier record's effect, so at 0.80 the answer depended on only the last ~7 records at any N and no attempt met the guarantees at N ≥ 200.
- **Dates are ISO with the year.** Records are 1-2 days apart from 2025-09-02, so N=800 runs into 2027 and N=3200 into the 2030s.
- **N counts every record**, across all projects when there are several (P2 gives the question's project N/5 records, so P2 starts at N=50).
- **Notes** are half absolute ("is going to $950K") and half relative ("goes up $40K"). Each record is withdrawn at most once, and a project gets at least three withdrawals when nesting is on, at least one of them nested.
- **Lures** that equal the answer by design are waived (`ignore_nested` without nesting, `withdraw_pops_latest` with `withdraw_target=latest`). Lure values may be negative; only the true budget is kept in range.
- **`missed_one_update`** means the answer is off by the size of any active adjustment. Amounts are multiples of $5K up to $150K, so at large N nearly any small slip matches it, and also matches a mishandled note or withdrawal; read it as "off by one record's amount".
- **Output limit.** A response longer than `max_output_tokens` (32K) scores as truncated. Claude Code resumes such responses up to three times on its own; the API would have cut them off before the ANSWER line.
- **Harness context.** Claude Code adds an identity block, the account email, and today's date (~500 tokens), so a long log's future dates can be noticed. Codex adds one tool definition it cannot use (`request_user_input`) and has no settable output limit. Both are the same in every condition.
