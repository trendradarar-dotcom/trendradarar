# Instagram M26.10 — Human / Cold Engineer Drill Checklist

This document is an execution checklist, not PASS evidence.

A reviewer/operator with no prior build context must perform the drill without help from the original producer or prior chat context.

Required outcomes:
1. identify R5_EXACT_TARGET_COMMIT and R5_EXACT_TARGET_TREE;
2. verify Git objects and evidence hashes;
3. rebuild from captured trusted source and wheelhouse;
4. identify live deployment commit/tree and publication kill switches;
5. explain UNKNOWN and no-blind-retry semantics;
6. restore the isolated recovery database and verify constraints/indexes/state;
7. demonstrate how secrets are supplied without printing them;
8. identify rollback to the promoted Golden/LKG baseline;
9. keep public publication disabled throughout;
10. produce timestamps, commands, failures, corrections, and final outcome.

Required independent statuses:
HUMAN_TAKEOVER =
COLD_ENGINEER_HANDOVER =
OWNER_RECOVERY_PACKAGE_EXECUTION =
RECOVERY_RUNBOOK_EXECUTION =

Until actually executed by a human/cold engineer, all remain NOT VERIFIED.
