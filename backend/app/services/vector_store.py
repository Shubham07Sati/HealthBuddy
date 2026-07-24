from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels
from typing import List, Dict, Any, Optional
from app.core.config import get_settings

settings = get_settings()

class VectorStoreService:
    def __init__(self):
        self.client = AsyncQdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
        self.knowledge_col = settings.qdrant_collection_knowledge
        self.patient_prefix = settings.qdrant_collection_patient_prefix
        self.dim = settings.embedding_dimension

    async def initialize_collections(self):
        # Create knowledge collection if not exists
        exists = await self.client.collection_exists(collection_name=self.knowledge_col)
        if not exists:
            await self.client.create_collection(
                collection_name=self.knowledge_col,
                vectors_config=qmodels.VectorParams(size=self.dim, distance=qmodels.Distance.COSINE)
            )

    def _get_patient_collection(self, patient_id: str) -> str:
        return f"{self.patient_prefix}_{patient_id}"

    async def initialize_patient_collection(self, patient_id: str):
        col_name = self._get_patient_collection(patient_id)
        exists = await self.client.collection_exists(collection_name=col_name)
        if not exists:
            await self.client.create_collection(
                collection_name=col_name,
                vectors_config=qmodels.VectorParams(size=self.dim, distance=qmodels.Distance.COSINE)
            )

    async def upsert_patient_embedding(self, patient_id: str, point_id: str, vector: List[float], payload: dict):
        col_name = self._get_patient_collection(patient_id)
        await self.client.upsert(
            collection_name=col_name,
            points=[qmodels.PointStruct(id=point_id, vector=vector, payload=payload)]
        )

    async def search_patient_history(self, patient_id: str, query_vector: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
        col_name = self._get_patient_collection(patient_id)
        results = await self.client.query_points(
            collection_name=col_name,
            query=query_vector,
            limit=top_k,
            score_threshold=settings.retrieval_similarity_threshold,
            with_payload=True,
        )
        return [{"id": hit.id, "score": hit.score, "payload": hit.payload} for hit in results.points]

    async def search_knowledge_base(
        self,
        query_vector: List[float],
        top_k: int = 8,
        score_threshold: Optional[float] = None,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search the shared clinical-guideline collection (`knowledge_col`).

        This is the retrieval primitive the Knowledge Agent (Agent 8) builds
        on -- it does not talk to Qdrant directly, only through this
        service, consistent with every other agent's use of vector_store.

        `category` optionally filters by a `category` payload field (e.g.
        "medication_guidance", "reference_range") if the ingested guideline
        points carry one; when omitted, search spans the whole collection.
        """
        query_filter = None
        if category:
            query_filter = qmodels.Filter(
                must=[qmodels.FieldCondition(key="category", match=qmodels.MatchValue(value=category))]
            )

        results = await self.client.query_points(
            collection_name=self.knowledge_col,
            query=query_vector,
            query_filter=query_filter,
            limit=top_k,
            with_payload=True,
        )
        return [{"id": hit.id, "score": hit.score, "payload": hit.payload} for hit in results.points]

vector_store = VectorStoreService()
