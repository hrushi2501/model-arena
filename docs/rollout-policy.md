# Rollout Policy

This document defines the simplified, deterministic release criteria for Model Arena.

## Rollout States
- `READY`: Candidate model is deployed and healthy.
- `SHADOW`: Candidate receives duplicated production traffic asynchronously (0% user-facing impact).
- `CANARY`: Candidate receives a configurable percentage of live user traffic (e.g. 10% → 25% → 50% → 100%).
- `PROMOTED`: Candidate successfully replaces the Champion as the primary production model.
- `ROLLED_BACK`: Rollback triggered; 100% of traffic immediately reverts to the Champion.

## The 3 Decision Rules

The Release Decision Engine continuously evaluates live metrics and returns one of three decisions:

1. **HOLD** (Insufficient evidence):
   - Triggered when fewer than **20 requests** or feedback labels have been collected.
   - Traffic share remains unchanged while more data is gathered.

2. **ROLLBACK** (Safety or quality breach):
   - Triggered when any of the following safety limits are breached:
     - **Error Rate:** > 5% of requests result in errors (HTTP 500s or exceptions).
     - **Latency:** p95 latency exceeds 200 ms.
     - **Quality:** Labeled accuracy of the candidate drops by more than 5% compared to the champion (`candidate_acc < champion_acc - 0.05`).
   - Action: Serving immediately reverts 100% of user traffic to the Champion, and an audit record is logged with the breach reason.

3. **PROMOTE** (Candidate approved):
   - Triggered when minimum sample count is satisfied, error rate is ≤ 5%, latency is acceptable, and candidate accuracy meets or exceeds the champion.
   - Action: Candidate traffic advances to the next stage (e.g. 10% → 25% → 50% → 100% PROMOTED).
