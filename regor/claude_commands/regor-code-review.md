---
description: Experiment code review (regor workflow)
---

# Experiment code review

Review an experiment script before it runs.
Check that the seed is actually used; splits are respected (no test data in training or model selection); the metric implementation matches its declared definition; outputs go through write_metrics with n_samples; there are no hard-coded secrets or private absolute paths; determinism claims are true.
Report findings as file:line. Do not run expensive jobs.

Global rules (see CLAUDE.md): never fabricate results, citations or sources; never run paid, remote or long jobs without a researcher-granted approval; never edit runs/raw or runs/metadata.
