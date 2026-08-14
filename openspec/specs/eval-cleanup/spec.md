# eval-cleanup Specification

## Purpose
TBD - created by archiving change codebase-health-remediation. Update Purpose after archive.
## Requirements
### Requirement: Single evaluation harness targeting golden dataset
The repository SHALL use `tests/evals/eval_harness.py` and `tests/evals/golden_dataset.json` as the unified RAG evaluation path. `scripts/evaluate_rag.py` SHALL be deleted. `scripts/run_preprod_qa_gate.py` step 5 SHALL execute `scripts/benchmark.py` instead of missing scripts.

#### Scenario: Running evaluation harness
- **WHEN** evaluation suite is executed via pytest or harness script
- **THEN** it loads `golden_dataset.json` and reports precision/recall without file missing errors

#### Scenario: Pre-production QA gate execution
- **WHEN** `scripts/run_preprod_qa_gate.py` runs
- **THEN** step 5 executes `scripts/benchmark.py` and all 5 gates evaluate without file-not-found failures

