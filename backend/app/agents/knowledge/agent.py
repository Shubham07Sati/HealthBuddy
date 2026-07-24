"""
Agent 8: Knowledge Retrieval
============================
Consumes normalized/coded clinical entities (Agent 4 output), trend
analysis (Agent 5 output), and optional free-text clinical context, and
retrieves relevant clinical guideline/reference passages from the
existing Qdrant-backed knowledge base (`app.services.vector_store`) for
the Reasoning Agent (Agent 6) to ground its insights in.

Design contract this agent upholds:
  * Never invents guideline content. Every KnowledgeItem returned is built
    from an actual vector-store hit's payload -- there is no hardcoded
    guideline text anywhere in this module.
  * Returns `List[dict]` (via KnowledgeItem.model_dump()) so it plugs into
    ReasoningAgent.generate_insights(retrieved_guidelines=...) and
    evidence.build_guideline_evidence() completely unchanged: those only
    ever read `text` / `source` off each dict, which every KnowledgeItem
    carries alongside its richer citation metadata.
  * Empty/no-match retrieval is a normal outcome, not an error: a patient
    with no coded entities, or a knowledge base with no matching
    passages, yields an empty list rather than raising or fabricating
    guidance.
  * Genuine failures (embedding backend down, Qdrant unreachable) raise
    KnowledgeRetrievalError so the orchestrator's guarded_node can route
    to error handling instead of silently losing evidence.

Expected knowledge-collection payload shape (produced by whatever
ingestion process populates `settings.qdrant_collection_knowledge` --
out of scope for this agent, which only *reads* that collection):
    {
        "guideline_id": str,
        "title": str,
        "source": str,             # e.g. "ADA 2024", "KDIGO 2024"
        "section": str | None,
        "text": str,
        "category": str | None,    # one of KnowledgeCategory
        "citation": str | None,
        "reference_range_low": float | None,
        "reference_range_high": float | None,
        "reference_range_unit": str | None,
    }
Every field is read defensively with `.get()` -- a payload missing
optional fields degrades gracefully rather than crashing retrieval.
"""
import logging
import time
from typing import Dict, List, Optional
from uuid import UUID

from app.core.config import get_settings
from app.core.exceptions import KnowledgeRetrievalError
from app.schemas.agent_messages import ClinicalEntitySet, CodedEntitySet, KnowledgeItem, TrendSet
from app.services.embeddings import embedding_service
from app.services.vector_store import vector_store

from . import query_builder
from .models import RankedKnowledgeCandidate, RetrievalQuery
from .ranking import rank_and_filter

log = logging.getLogger(__name__)
settings = get_settings()

_VALID_CATEGORIES = {
    "lab_interpretation", "disease_guideline", "medication_guidance",
    "diagnostic_criteria", "follow_up", "monitoring", "contraindication",
    "reference_range", "general",
}


class KnowledgeAgent:
    """
    Agent 8: Knowledge Retrieval.

    Builds targeted retrieval queries from patient data, searches the
    existing clinical-guideline vector store, and returns ranked,
    deduplicated, structured knowledge objects.
    """

    def __init__(self) -> None:
        self.top_k = settings.knowledge_top_k
        self.max_results = settings.knowledge_max_results
        self.min_relevance = settings.knowledge_min_relevance
        self.max_query_terms = settings.knowledge_max_query_terms

    async def retrieve_guidelines(
        self,
        entity_set: Optional[ClinicalEntitySet] = None,
        coded_set: Optional[CodedEntitySet] = None,
        trend_set: Optional[TrendSet] = None,
        clinical_context: Optional[str] = None,
        patient_id: Optional[UUID] = None,
    ) -> List[dict]:
        """
        Retrieve relevant clinical knowledge for the current patient state.

        Never raises for "no evidence found" -- returns an empty list.
        Raises KnowledgeRetrievalError only when the retrieval backend
        itself fails (embedding generation or vector-store search).
        """
        import asyncio
        import socket

        # Fast reachability check before loading the embedding model (which
        # can take 60-120s on first load). If Qdrant is unreachable, bail
        # immediately without blocking the pipeline.
        qdrant_host = settings.qdrant_url.replace("http://", "").replace("https://", "").split(":")[0]
        qdrant_port = int(settings.qdrant_url.split(":")[-1]) if ":" in settings.qdrant_url else 6333
        try:
            sock = socket.create_connection((qdrant_host, qdrant_port), timeout=2)
            sock.close()
        except (socket.timeout, ConnectionRefusedError, OSError):
            log.warning(
                f"Qdrant not reachable at {settings.qdrant_url} -- "
                "skipping knowledge retrieval for this pipeline run"
            )
            return []

        start_time = time.time()
        log.info(f"Retrieving clinical knowledge for patient {patient_id}")

        queries = query_builder.build_queries(
            entity_set=entity_set,
            coded_set=coded_set,
            trend_set=trend_set,
            clinical_context=clinical_context,
            max_queries=self.max_query_terms,
        )

        if not queries:
            log.info(
                f"No retrieval queries could be built for patient {patient_id} -- "
                "skipping vector search, returning empty knowledge set"
            )
            return []

        try:
            candidates = await asyncio.wait_for(
                self._run_queries(queries, patient_id),
                timeout=10.0  # Don't let Qdrant hang the entire pipeline
            )
        except asyncio.TimeoutError:
            log.warning(
                f"Knowledge retrieval timed out for patient {patient_id} "
                "(Qdrant unreachable or slow) -- skipping, returning empty knowledge set"
            )
            return []
        except Exception as exc:
            log.warning(
                f"Knowledge retrieval failed for patient {patient_id}: {exc} "
                "-- skipping, returning empty knowledge set"
            )
            return []

        ranked = rank_and_filter(
            candidates=candidates,
            min_relevance=self.min_relevance,
            max_results=self.max_results,
        )

        items = [self._to_knowledge_item(c) for c in ranked]

        log.info(
            f"Knowledge retrieval for patient {patient_id} returned {len(items)} item(s) "
            f"from {len(queries)} quer{'y' if len(queries) == 1 else 'ies'} "
            f"({len(candidates)} raw hit(s) before ranking) in "
            f"{int((time.time() - start_time) * 1000)}ms"
        )

        return [item.model_dump(mode="json") for item in items]

    # ------------------------------------------------------------------ #
    # Retrieval
    # ------------------------------------------------------------------ #
    async def _run_queries(
        self,
        queries: List[RetrievalQuery],
        patient_id: Optional[UUID],
    ) -> List[RankedKnowledgeCandidate]:
        """
        Execute each planned query against the knowledge base.

        A single query's embedding/search failure is logged and skipped
        rather than aborting the whole retrieval -- one bad sub-query
        shouldn't discard evidence the other sub-queries successfully
        found. If every single query fails, that's treated as a genuine
        backend failure and raised.
        """
        candidates: List[RankedKnowledgeCandidate] = []
        failures = 0

        for q in queries:
            try:
                vector = embedding_service.embed_text(q.text, biomedical=False)
                hits = await vector_store.search_knowledge_base(
                    query_vector=vector,
                    top_k=self.top_k,
                    category=q.category if q.category != "general" else None,
                )
            except KnowledgeRetrievalError:
                failures += 1
                log.warning(f"Retrieval query failed for patient {patient_id}: '{q.text}'")
                continue
            except Exception as exc:
                failures += 1
                log.warning(
                    f"Unexpected error running retrieval query for patient {patient_id} "
                    f"('{q.text}'): {exc}"
                )
                continue

            for hit in hits:
                candidate = self._to_candidate(hit, q)
                if candidate is not None:
                    candidates.append(candidate)

        if failures and failures == len(queries):
            raise KnowledgeRetrievalError(
                message="All knowledge retrieval queries failed",
                detail=f"{failures} of {len(queries)} queries errored",
                patient_id=str(patient_id) if patient_id else "",
            )

        return candidates

    # ------------------------------------------------------------------ #
    # Hit -> candidate / item translation
    # ------------------------------------------------------------------ #
    def _to_candidate(self, hit: Dict, query: RetrievalQuery) -> Optional[RankedKnowledgeCandidate]:
        payload = hit.get("payload") or {}
        text = payload.get("text")
        if not text:
            log.warning(f"Skipping knowledge-base hit {hit.get('id')} -- missing 'text' in payload")
            return None

        # Support both the expected payload shape (guideline_id/title/source/section)
        # and the actual ingested shape (condition/metric_name/evidence_source).
        source = (
            payload.get("source")
            or payload.get("evidence_source")
            or "Clinical Guideline"
        )
        title = (
            payload.get("title")
            or payload.get("display_name")
            or payload.get("metric_name")
            or payload.get("condition")
            or source
        )
        section = payload.get("section") or payload.get("condition")
        guideline_id = payload.get("guideline_id") or str(hit.get("id"))
        category = payload.get("category") or query.category
        if category not in _VALID_CATEGORIES:
            category = query.category

        citation = (
            payload.get("citation")
            or (f"{source} -- {section}" if section else source)
        )

        return RankedKnowledgeCandidate(
            guideline_id=str(guideline_id),
            title=title,
            source=source,
            section=section,
            text=text,
            category=category,
            relevance_score=round(float(hit.get("score", 0.0)), 4),
            citation=citation,
            reference_range_low=payload.get("reference_range_low"),
            reference_range_high=payload.get("reference_range_high"),
            reference_range_unit=payload.get("reference_range_unit"),
            retrieval_query=query.text,
        )

    @staticmethod
    def _to_knowledge_item(candidate: RankedKnowledgeCandidate) -> KnowledgeItem:
        return KnowledgeItem(
            guideline_id=candidate.guideline_id,
            title=candidate.title,
            source=candidate.source,
            section=candidate.section,
            text=candidate.text,
            relevance_score=candidate.relevance_score,
            category=candidate.category,
            citation=candidate.citation,
            reference_range_low=candidate.reference_range_low,
            reference_range_high=candidate.reference_range_high,
            reference_range_unit=candidate.reference_range_unit,
            retrieval_query=candidate.retrieval_query,
        )
