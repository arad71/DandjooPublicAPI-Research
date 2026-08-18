from typing import Any, Dict, List, Optional

from app.helpers.mongo import get_lookup_taxon_collection
from app.settings import Settings


def get_taxonomic_autocomplete_results(
    field: str,
    settings: Settings,
    search_term: Optional[str] = None,
    filter_conditions: Optional[List[dict]] = None,
) -> List[str]:
    """
    Common function to handle taxonomic autocomplete searches.

    Args:
        field: The taxonomic field to search (e.g., "phylum", "class_", "order")
        search_term: Optional search term to filter results
        filter_conditions: Additional filter conditions as a list of dictionaries
        settings: Application settings

    Returns:
        List of matching taxonomic terms (_id values)
    """
    must = (
        [{"autocomplete": {"query": search_term, "path": "value"}}]
        if search_term
        else []
    )

    filters: List[Dict[str, Any]] = [{"term": {"query": field, "path": "field"}}] 
    if filter_conditions:
        filters.append({"compound": {"should": filter_conditions }})

    aggregate_query = [
        {"$search": {"compound": {"must": must, "filter": filters}}},
        {"$limit": 100},
    ]

    collection = get_lookup_taxon_collection(settings)
    return [doc["value"] for doc in collection.aggregate(aggregate_query)]
