---
name: budget-withdrawal-ledger
description: Compute a budget from Finance records by resolving withdrawal chains before summing the surviving signed changes.
---

For this budget-record task, separate deciding which updates count from adding their amounts.

1. Use the supplied policy. Only Finance Office budget updates affect the budget; administrative messages and other sources' budget claims contribute nothing. Preserve each Finance update's record number and exact signed amount.
2. For explicit withdrawals, resolve their target record numbers from later records toward earlier ones. An effective withdrawal makes its target ineffective. An ineffective withdrawal does not cancel its target. Thus a withdrawal of a withdrawal can restore the original change. Follow the complete chain and retain ordinary Finance changes unrelated to it.
3. Start from the opening budget once. Add each effective increase and subtract each effective decrease once. A withdrawn change contributes zero. Do not subtract its amount again after excluding it. In the explicit-reversal version, the stated reversing increases and decreases are ordinary signed changes; do not additionally cancel their earlier counterparts.
4. Sum the retained changes in short contiguous record blocks. Check each block's signs, included record numbers, and subtotal, then combine the subtotals with the opening budget. Cross-check by grouping retained increases and retained decreases separately. If totals disagree, locate the mismatched records or arithmetic before choosing an answer.
5. Check that gossip, filler, duplicated changes, and inactive updates have not entered the total. Report the current budget in the requested ANSWER format. Do not infer a missing change from an expected range or a plausible-looking total.
