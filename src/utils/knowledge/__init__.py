from qdrant_client.models import Condition, FieldCondition, MatchValue


def active_generation_conditions(version: str, generation: str) -> list[Condition]:
    """Require knowledge from the active collection version and dataset."""
    return [
        FieldCondition(key="collection_version", match=MatchValue(value=version)),
        FieldCondition(key="dataset_generation", match=MatchValue(value=generation)),
    ]
