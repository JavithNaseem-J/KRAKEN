# knowledge-loader-consolidation Specification

## Purpose
Unified knowledge loader framework with container-aware filesystem resolution and modular source formatters.

## Requirements

### Requirement: Shared generic chunk loader
The Knowledge Service SHALL provide a generic `load_chunks` function in `services/knowledge/loaders/base.py` that handles directory existence validation, file extension filtering, file iteration, error logging, and structure aggregation. Specific loaders (`ticket_loader`, `sla_loader`, `faq_loader`) SHALL delegate file processing to `load_chunks` by providing a natural-language text formatter function.

#### Scenario: Generic loader handles missing directory
- **WHEN** `load_chunks` is called with a directory path that does not exist
- **THEN** it logs a warning and returns an empty list without raising an exception

#### Scenario: Generic loader processes files cleanly
- **WHEN** valid files exist in the target directory
- **THEN** `load_chunks` parses each file using the supplied record-to-text formatter and returns structured chunk dictionaries

### Requirement: Container-safe data directory resolution
Knowledge loaders SHALL resolve the base data directory using a dual-strategy lookup: checking `Path(__file__).resolve().parents[3] / "data"` first, and falling back to `/app/data` (or an environment override `KNOWLEDGE_DATA_DIR`) when running inside Docker containers where `parents[3]` resolves to root `/`.

#### Scenario: Running locally
- **WHEN** loaders are invoked in a local repository checkout
- **THEN** paths resolve to `<repo-root>/data/knowledge/<source>`

#### Scenario: Running inside Docker container
- **WHEN** loaders are invoked inside a Docker container where `/app/loaders/` is 2 levels below `/app`
- **THEN** paths resolve to `/app/data/knowledge/<source>` and files are loaded successfully
