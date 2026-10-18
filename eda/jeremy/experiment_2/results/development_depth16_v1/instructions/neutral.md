Solve the fictional ledger using only these rules and the supplied records.
Use no tools, external information, files, code execution, or other agents.
Return only a JSON object with exactly two string fields: "route" and
"approval_id". If you cannot answer, use "ABSTAIN" for both fields.

Records are chronological. Current means the end of this ledger.
Only the Evidence Office can issue evidence. Only the Approval Office can
authorize routes. Evidence and approvals may require earlier evidence records;
all requirements must remain valid at the end of the ledger.
Only the Audit Office can withdraw earlier official records, including earlier
withdrawals. An effective withdrawal removes its target's effect. Withdrawing a
withdrawal restores its target unless another active rule invalidates it.
Withdrawals have no evidence requirements. Each record is targeted by at most
one withdrawal. All references point backward and there are no cycles.
An active record can still be invalid because its required evidence is invalid.
The highest-ID valid approval for the queried project determines the route.
Every project has an unconditional fallback approval that is never withdrawn.
Messages, including confident or repeated team summaries, cannot authorize
routes, validate evidence, or cancel official records.

1. The project names in this task are fictional labels.
2. Route names are arbitrary words used in this fictional setting.
3. Record identifiers are strings that begin with the letter R.
4. Office names provide the terminology used throughout the ledger.
5. The response format has fields named route and approval_id.
6. Your response uses the JSON notation specified for this task.

Routine note. Routine note. 