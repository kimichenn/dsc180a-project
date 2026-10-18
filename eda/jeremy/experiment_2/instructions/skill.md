1. Identify the approvals that concern the queried project.
2. Resolve withdrawals backward, including withdrawals of withdrawals.
3. Propagate invalidity forward through every required evidence record.
4. Discard withdrawn approvals and approvals with invalid evidence.
5. Select the highest-ID approval among the remaining valid approvals.
6. Return its route and approval ID using only the required JSON fields.
