"""Harness for the v4 design in eda_proposal_v2.md: generated event logs with many rule-governed conflicts.

Pipeline: dials + seed -> generated log pair (Conflict / Consistent) -> resolver-computed answer
-> model calls -> parsed ANSWER line -> per-project decisions -> stage tables and decision rules.
Run `python -m eventlog --help` from eda/kimi.
"""
