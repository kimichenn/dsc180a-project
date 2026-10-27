---
name: budget-chronological-replay
description: Compute a budget by replaying authoritative signed changes and explicit withdrawal effects with running checkpoints.
---

For this budget-record task, follow the supplied Finance authority and withdrawal policy and replay the records in order.

Initialize the running budget from the opening Finance record. Ignore administrative messages and budget claims from other sources. For each Finance increase or decrease, store its record number and signed effect and apply it once.

When Finance withdraws an earlier update, look up the referenced record rather than guessing its amount from nearby text. Reverse that update's effect. In a chain where each update is withdrawn once, a withdrawal has the opposite signed effect of its target, so withdrawing that withdrawal reverses the reversal and restores the original change. Track the effect of the withdrawal itself under its own record number. If references overlap, resolve their effective status under the policy so an already-inactive update is not removed twice.

Use one accounting method consistently: this chronological replay includes a change when it arrives and its reversal when it is withdrawn. Do not also delete that change from the accumulated total. Explicit increases and decreases that represent reversals are applied as written once.

Keep short blocks of signed effects and running-budget checkpoints. Verify each block's arithmetic and that every effective Finance event appears exactly once with the right sign. Reconcile the final running budget with the opening budget plus all block effects. Never adjust the result just to make it fall in a plausible range. End in the requested ANSWER format.
