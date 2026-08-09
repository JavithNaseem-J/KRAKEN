## ADDED Requirements

### Requirement: Code-Level Relevance Filtering
The Reasoner node SHALL filter retrieved knowledge chunks against a minimum score threshold of 0.40 before passing context to the LLM.

#### Scenario: Filtering low-relevance chunks
- **WHEN** retrieved chunks contain items with relevance scores below 0.40
- **THEN** reasoner node removes low-score chunks from context prior to LLM reasoning call

### Requirement: Explicit Grounding Refusal State
The Reasoner node SHALL set an explicit `insufficient_knowledge` flag and refusal reasoning state when zero valid knowledge chunks satisfy the relevance threshold.

#### Scenario: Refusal on empty or low-relevance retrieval
- **WHEN** all retrieved chunks fall below the 0.40 threshold for a domain query
- **THEN** reasoner node sets `insufficient_knowledge: True` and outputs an explicit refusal statement preventing parametric memory hallucination
