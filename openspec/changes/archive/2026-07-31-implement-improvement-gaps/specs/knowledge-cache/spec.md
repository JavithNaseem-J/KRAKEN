## ADDED Requirements

### Requirement: Cache metadata length truncation guardrail
The Knowledge Service retriever SHALL limit the total string length of serialized `chunks_json` in semantic query cache metadata to 1,800 characters to prevent ChromaDB metadata key-value size limit violations.

#### Scenario: Cached chunks JSON under size limit
- **WHEN** top retrieved chunks are serialized to `chunks_json` and total length is <= 1,800 characters
- **THEN** the full `chunks_json` is stored in ChromaDB cache metadata

#### Scenario: Cached chunks JSON exceeds size limit
- **WHEN** top retrieved chunks are serialized to `chunks_json` and total length exceeds 1,800 characters
- **THEN** the retriever truncates the cached chunk array or omits `chunks_json` to keep metadata size under 1,800 characters
