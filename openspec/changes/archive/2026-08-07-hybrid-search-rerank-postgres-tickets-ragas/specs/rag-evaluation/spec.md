# rag-evaluation Specification

## MODIFIED Requirements

### Requirement: Ragas ground-truth evaluation pipeline
The system SHALL provide an automated evaluation script `scripts/evaluate_rag.py` that reads test cases from `data/workspace/eval_dataset.json` (containing `question`, `ground_truth`, and `retrieved_contexts`). The script SHALL calculate Faithfulness, Answer Relevance, Context Precision, and Context Recall metrics using live LLM-as-a-Judge execution when API keys are available, and output a formatted evaluation report.

#### Scenario: Live LLM-as-a-Judge execution
- **WHEN** `python scripts/evaluate_rag.py` is executed with valid `LLM_API_KEY` environment configuration
- **THEN** it SHALL invoke LLM API judges via `ragas.evaluate` for Faithfulness, Answer Relevance, Context Precision, and Context Recall, outputting results to `eval_report.md`

#### Scenario: Offline fallback execution
- **WHEN** `python scripts/evaluate_rag.py` is executed without `LLM_API_KEY`
- **THEN** it SHALL execute heuristic fallback scoring without external API calls and output results to `eval_report.md`
