# Rollout policy

This file is the design placeholder for configurable shadow and canary rules.

Planned states: `READY`, `SHADOW`, `CANARY`, `PROMOTED`, `PAUSED`, and `ROLLED_BACK`.

The controller should return:

- **Advance/promote** when configured health and labeled-quality criteria pass.
- **Hold** when the minimum request or feedback sample is missing.
- **Rollback** when a configured error, latency, or quality limit is breached.

Choose thresholds for the selected dataset and document them in the assignment report. Do not treat unlabeled prediction traffic as evidence of accuracy.
