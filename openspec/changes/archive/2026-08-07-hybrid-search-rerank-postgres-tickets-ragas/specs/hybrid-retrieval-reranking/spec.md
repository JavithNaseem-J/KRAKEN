# hybrid-retrieval-reranking Specification

## ADDED Requirements

### Requirement: Reciprocal Rank Fusion (RRF) hybrid search
The `KnowledgeRetriever` in `services/knowledge/retriever.py` SHALL combine dense vector similarity scores from Qdrant with BM25 keyword matching scores using Reciprocal Rank Fusion (RRF).

#### Scenario: RAG query execution with hybrid search
- **WHEN** `KnowledgeRetriever.retrieve()` is invoked with a query
- **THEN** it SHALL calculate both dense vector distance scores and keyword frequency match scores, merging them into an RRF hybrid score for candidate ranking

### Requirement: Cross-encoder re-ranking step
The `KnowledgeRetriever` SHALL re-rank top candidate chunks using cross-encoder relevance scoring before returning the top-k chunks in `RetrievalResult`.

#### Scenario: Re-ranking candidates
- **WHEN** top candidate chunks are retrieved from vector and keyword search
- **THEN** the retriever SHALL apply cross-encoder re-ranking, ordering final chunks by relevance score descending
