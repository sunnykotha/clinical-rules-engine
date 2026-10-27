# Clinical Rules Engine

A configurable clinical rules engine using validated JSON rule sets,
condition evaluation, alert conflict resolution, cooldowns, historical
evaluation, rule chaining, evaluation traces, and lazy batch processing.
## Worked diabetes example

The two-rule example is configured in
`rules/diabetes-worked-example.json` and loaded through the validated JSON
rule loader. It includes:

- A priority-1, severity-5 alert for HbA1c above 8 with an emergency visit
  in the last 30 days.
- A priority-2, severity-2 care-gap alert for HbA1c above 8 without an
  endocrinology visit in the last 180 days.

When both rules match the same diabetes issue, the higher-severity alert
wins and the lower-severity alert is suppressed. Evaluation traces explain
the decisions and list the facts used.

### Run the tests

From the project root, activate the virtual environment and run:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pytest -q
```

### Batch evaluation

Use `evaluate_patients` from `clinical_rules.batch` to evaluate an iterable
of `(patient_id, facts)` pairs lazily. Each result is yielded as
`(patient_id, traces)`, so the caller can process results incrementally.