"""Elasticsearch indexer — syncs property records from Postgres to ES."""

from typing import Dict, Any, List

INDEX_NAME = "distressed-properties"


class PropertyIndexer:
    def __init__(self, es_client):
        self.client = es_client

    async def index_property(self, property_data: Dict[str, Any]) -> bool:
        """Index or update a single property document."""
        # TODO: transform property_data to match mappings.json shape
        # TODO: call self.client.index(index=INDEX_NAME, id=..., body=...)
        raise NotImplementedError

    async def bulk_index(self, properties: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Bulk index a list of property documents."""
        # TODO: build bulk actions list and call self.client.bulk()
        raise NotImplementedError

    async def delete_property(self, property_id: str) -> bool:
        """Remove a property document from the index."""
        # TODO: call self.client.delete(index=INDEX_NAME, id=property_id)
        raise NotImplementedError

    async def create_index(self) -> bool:
        """Create the index with mappings if it does not exist."""
        # TODO: load mappings.json and call self.client.indices.create()
        raise NotImplementedError
