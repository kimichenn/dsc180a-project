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

1. Identify the approvals that concern the queried project.
2. Resolve withdrawals backward, including withdrawals of withdrawals.
3. Propagate invalidity forward through every required evidence record.
4. Discard withdrawn approvals and approvals with invalid evidence.
5. Select the highest-ID approval among the remaining valid approvals.
6. Return its route and approval ID using only the required JSON fields.
