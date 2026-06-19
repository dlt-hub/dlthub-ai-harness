---
name: deploy-run-sample-pipeline
description: "Deploy and run the pre-shipped Jaffle Shop sample pipeline on dltHub Platform — an educational end-to-end run after uvx dlthub-start, NOT a production-grade pipeline. Use when the user wants to complete the onboarding deploy-and-run flow with the bundled pipeline.py."
argument-hint: ""
---

Deploy `pipeline.py` — already present in the project root — to dltHub Platform. This pipeline loads data from the Jaffle Shop API into the dltHub playground cloud data warehouse (cloud storage handled by dltHub — no credentials needed).

Do not use when `pipeline.py` does not exist in the project root, or when the user wants to build their own pipeline rather than run the sample.

## Orientation

Print this to the user before doing anything else:

- [x] **Scaffolded the example dltHub project and created a virtual environment**
- [x] **Created a dltHub free trial account for you on app.dlthub.com**
- [ ] **Deploy an example pipeline to load data from the Jaffle Shop API to the dltHub playground cloud data warehouse**
- [ ] **Run your pipeline on dltHub (stream the logs)**
- [ ] **Build your own production pipeline or keep exploring**

Then ask the user: "Shall I start with Step 3?"

Wait for confirmation before proceeding. If the user says no or wants to do something else, stop and ask what they'd like to do instead.

## Step 3 — Deploy

Print to the user: `- [ ] Step 3/5 — Deploy an example pipeline`

```bash
uv run dlthub deploy
```

Summarize which jobs were created or updated.

Print to the user: "- [x] Step 3/5"

## Step 4 — Run on the cloud

Print to the user: `- [ ] Step 4/5 — Run your pipeline on dltHub`

```bash
uv run dlthub run load_sample_shop -f
```

The `-f` flag streams logs in real time. Wait for the job to complete.

If it fails:

```bash
uv run dlthub job logs load_sample_shop
```

| Error | Cause | Fix |
|-------|-------|-----|
| `Trial period has ended` | Plan expired | Contact your workspace admin |

Print to the user: "- [x] Step 4/5"

## Step 5 — Next steps

Print to the user: `- [ ] Step 5/5 — Build your own production pipeline or keep exploring`

**Onboarding complete!** Your pipeline ran on dltHub Platform. Explore the loaded data at [app.dlthub.com](https://app.dlthub.com) — the query editor lets you run SQL directly against the results.

Ready to build a real pipeline? Just describe what you want, e.g. "I want to load my Stripe payment data into a database — invoices and subscriptions."