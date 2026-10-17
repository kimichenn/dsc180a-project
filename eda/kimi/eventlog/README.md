# v4: generated event logs (`eventlog/`)

Run every command from `eda/kimi`. The write-up is [reports/v4/eda_report.md](../reports/v4/eda_report.md).

Each log covers N fictional Atlas projects. It contains a policy memo, an authority handover, a staff directory with one person who changes offices, a project roster, and changelog, email, and ticket records. Traps are non-governing launch dates placed across the question's threshold. The resolver ([resolver.py](resolver.py)) applies the memo's rules to compute every answer, and every log has a matched Consistent version.

| Step | Command |
| --- | --- |
| Generator validation (hand logs vs resolver, checks on generated logs) | `python -m eventlog validate` |
| Write one log pair to read end to end | `python -m eventlog generate --seed 1` |
| Stage A, see calls and estimated cost | `python -m eventlog run A --dry-run` |
| Stage A probe (18 calls) | `python -m eventlog run A` |
| Tables plus the decision rule, which prints the next command | `python -m eventlog analyze results/v4/A_step0` |
| Lower the general dials (Stage A rule 2) | `python -m eventlog run A --step 1` (through `--step 5`) |
| Stage A rule 3 options | `--set n_projects=200`, `--models-config config/v4_small_models.toml`, `--response-format final_only` |
| Stage B (126 calls) | `python -m eventlog run B --step K` |
| Stage C (108 calls, fresh seeds) | the command `analyze` prints after Stage B |

- **Configs.** Models, reasoning settings, and prices are in [config/v4_models.toml](../config/v4_models.toml). Reasoning is set to `low`, the lowest level each flagship allows, standing in for "standard mode without extended reasoning".
- **Validation data.** The 12 hand-written logs are in [data/v4/hand_logs.json](../data/v4/hand_logs.json).
- **Run directories.** Each run directory holds `logs/` (every generated log pair with its answer and per-project metadata), `responses.jsonl` (raw responses, including any first attempt that lacked an ANSWER line), and `manifest.json`.

**Where the code interprets the proposal:**
- **Dates.** Records are dated Sep 2 to Oct 31, and launch dates fall in Nov 3 to Dec 19, so issue dates and values never overlap.
- **Within-section order.** In grouped order, records inside each source section are shuffled, as in the proposal's example ticket export.
- **Trap placement.** Distractor notes and pre-authority records always come after the project's last counting record, so believing one changes the answer.
- **Pre-authority traps** come in two forms: a Release Board member writing before the handover, or the person who moves writing before their move.
- **Projects without traps** may also get an authoritative confirmation or an agreeing note, so a note's presence doesn't give a trap away.
- **Staff names** never share a first or a last name.
- **Out-of-program records** are as numerous as in-program ones. They are written by Helios staff about projects whose names extend Atlas names (e.g. Kavel and Kavelra).
