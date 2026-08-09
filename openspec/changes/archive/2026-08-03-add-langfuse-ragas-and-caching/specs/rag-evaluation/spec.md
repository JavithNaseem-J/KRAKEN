# rag-evaluation Specification

## ADDED Requirements

### Requirement: Ragas ground-truth evaluation pipeline
The system SHALL provide an automated evaluation script `scripts/evaluate_rag.py` that reads test cases from `data/workspace/eval_dataset.json` (containing `question`, `ground_truth`, and `retrieved_contexts`). The script SHALL calculate Faithfulness, Answer Relevance, Context Precision, and Context Recall metrics using Ragas and output a formatted evaluation report.

#### Scenario: Evaluation pipeline execution
- **WHEN** `python scripts/evaluate_rag.py` is executed
- **THEN** it SHALL evaluate all test cases, display average metric scores (0.00 to 1.00), and write the results to `eval_report.md`

#### Scenario: Ground truth dataset format validation
- **WHEN** `data/workspace/eval_dataset.json` is loaded
- **THEN** it MUST contain valid JSON array objects with required fields `user_input`, `reference`, and `retrieved_contexts`
