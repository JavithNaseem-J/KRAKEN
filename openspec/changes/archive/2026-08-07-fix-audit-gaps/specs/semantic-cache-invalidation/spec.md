## ADDED Requirements

### Requirement: Cache TTL & Mutation Invalidation
The SemanticCache SHALL enforce a time-to-live limit on cached vector entries and support explicit invalidation upon ticket data mutations.

#### Scenario: Expiring stale cache entries
- **WHEN** a cached vector result exceeds its max TTL
- **THEN** semantic cache treats entry as a miss and fetches fresh response from agent pipeline

#### Scenario: Invalidating cache on data mutation
- **WHEN** an action mutates ticket status or SLA rules
- **THEN** action service calls cache invalidation to purge affected query responses
