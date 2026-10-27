# Workflow v1: clean-case failure review

Reviewed all 100 C responses: 50 workflow and 50 baseline. Repeats share five logs and are not independent questions. Only final response text is available for diagnosis; hidden reasoning is not inferred.

| Log | No skill correct/10 | Workflow correct/10 |
|---|---:|---:|
| s750000_n1600 | 9 | 8 |
| s750001_n1600 | 10 | 6 |
| s750002_n1600 | 9 | 8 |
| s750003_n1600 | 8 | 9 |
| s750004_n1600 | 10 | 6 |

## Response behavior

- none: 46/50 correct; 0/50 responses expose record-range tables; mean output tokens 2759.
- workflow_v1: 37/50 correct; 49/50 responses expose record-range tables; mean output tokens 3053.

All 13 workflow failures explicitly recognize that no withdrawals appear. Each exposes a numerical table with at least one source-inconsistent row. Thus those visible tables do not substantiate successful verification. A correct policy statement does not establish correct record selection or arithmetic. The cause of a bad segment total cannot be determined from its numerical offset alone.

The audit compares every parseable range in both arms, including correct answers, with exact C records. It distinguishes segment net changes from cumulative states. It also recombines exposed net rows below: a mismatch with the final answer is a separate visible aggregation inconsistency. Agreement with the final answer does not validate the source-derived rows.

| Failed trial | Expected | Answer | Wrong/table rows | First source discrepancy | Opening + exposed net rows |
|---|---:|---:|---:|---|---:|
| s750000_n1600_C_none_gpt_r3 | 1728 | 1628 | 0/0 | not exposed | not applicable |
| s750000_n1600_C_workflow_v1_gpt_r1 | 1728 | 1858 | 1/8 | 801-1000: 39 vs -91 | 1858 |
| s750000_n1600_C_workflow_v1_gpt_r5 | 1728 | 1663 | 2/8 | 401-600: 39 vs 29 | 1663 |
| s750001_n1600_C_workflow_v1_gpt_r1 | 845 | 829 | 3/16 | 801-900: 483 vs 479 | 829 |
| s750001_n1600_C_workflow_v1_gpt_r2 | 845 | 945 | 1/16 | 1401-1500: 880 vs 780 | 945 |
| s750001_n1600_C_workflow_v1_gpt_r6 | 845 | 784 | 1/16 | 801-900: 418 vs 479 | 784 |
| s750001_n1600_C_workflow_v1_gpt_r9 | 845 | 1078 | 2/16 | 2-100: 491 vs 242 | 1078 |
| s750002_n1600_C_none_gpt_r2 | 1054 | 1044 | 0/0 | not exposed | not applicable |
| s750002_n1600_C_workflow_v1_gpt_r10 | 1054 | 1044 | 16/16 | 1-100: 1653 vs 1663 | not applicable |
| s750002_n1600_C_workflow_v1_gpt_r4 | 1054 | 964 | 1/4 | 2-400: 2846 vs 2936 | 964 |
| s750003_n1600_C_none_gpt_r2 | 470 | 475 | 0/0 | not exposed | not applicable |
| s750003_n1600_C_none_gpt_r6 | 470 | 475 | 0/0 | not exposed | not applicable |
| s750003_n1600_C_workflow_v1_gpt_r9 | 470 | 500 | 1/16 | 1201-1300: -35 vs -65 | 500 |
| s750004_n1600_C_workflow_v1_gpt_r1 | 1044 | 1144 | 1/16 | 2-100: 1978 vs 1878 | 1144 |
| s750004_n1600_C_workflow_v1_gpt_r3 | 1044 | 999 | 1/16 | 101-200: -218 vs -173 | 999 |
| s750004_n1600_C_workflow_v1_gpt_r4 | 1044 | 1104 | 1/16 | 901-1000: 250 vs 190 | 1104 |
| s750004_n1600_C_workflow_v1_gpt_r8 | 1044 | 1114 | 2/16 | 101-200: -88 vs -173 | 1114 |

## Revision hypothesis and limits

V1 places its direct-path instruction after mapping evidence, then still prescribes long-input segments and two separate challenge checks. A candidate can therefore correctly recognize a clean input while performing the elaborate calculation procedure anyway. Workflow v2 moves the task-dependent route before conflict bookkeeping, explicitly skips dependency machinery when irrelevant, and makes segmentation/regrouping optional. It preserves authority, exact revision targets, nested revisions, scope, and operation semantics. It distinguishes source extraction, local calculation, and aggregation in verification.

This is a plausible prompt-level intervention, not proof that tables, length, or extra reasoning caused degradation. Baseline also makes calculation errors, and the arms use different stochastic responses. A new skill-versus-baseline pilot cannot isolate routing from simultaneous wording/length changes or directly estimate v2 minus v1. No instruction contains these log identifiers, numerical answers, or budget-specific rules.

Detailed audit: [workflow_v1_clean_checkpoint_audit.csv](workflow_v1_clean_checkpoint_audit.csv).
