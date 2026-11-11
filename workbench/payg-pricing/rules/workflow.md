# Estimate pay-as-you-go cost

## Workflow Entry
**ALWAYS** start with **Pricing estimation** (`pricing-estimation`) — when the user asks what their jobs or workspace will cost, their monthly bill, or runtime hours on pay-as-you-go

## Core workflow
1. **Pricing estimation** (`pricing-estimation`) — read the deployed jobs, their runs and instance sizes; give a monthly cost range, a what-if cadence ladder and ways to cut cost

## Handover to other toolkits

### Outgoing (from payg-pricing)

- **performance** → `optimize-performance` — when a cost lever is "make runs shorter": tune the slow job before changing cadence or instance size (install if absent: `uv run dlthub --non-interactive ai toolkit install performance`)
- **dlthub-platform** → `deploy-workspace` — when the user decides to change a job's cadence or instance size; that toolkit's `job-resources` rule requires their explicit yes

References:
* **Instance size and budget multipliers**: https://dlthub.com/docs/hub/pipeline-operations/job-configuration#instance-size
* **Command line interface**: https://dlthub.com/docs/hub/command-line-interface.md
