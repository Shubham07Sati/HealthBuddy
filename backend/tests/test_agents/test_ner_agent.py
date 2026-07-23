"""
Tests for Agent 3: Medical NER & Relations.

Runs against the project's real knowledge_base ontology files, so these
double as a regression check that the dictionaries stay parseable and
that this agent's regex layer keeps matching them correctly.
"""
import pytest

from app.agents.ner.agent import NERAgent
from app.models.clinical_entity import AssertionStatus, EntityType
from app.schemas.agent_messages import RawExtraction, TextSpan


def _raw(text: str, confidence: float = 0.9) -> RawExtraction:
    lines = text.split("\n")
    spans = [TextSpan(text=line, confidence=confidence, page=1, span_type="text") for line in lines]
    return RawExtraction(
        document_id="00000000-0000-0000-0000-000000000001",
        spans=spans,
        tables=[],
        full_text=text,
        avg_confidence=confidence,
        low_confidence_spans=[],
        ocr_engine="test",
        processing_time_ms=0,
    )


@pytest.fixture(scope="module")
def agent() -> NERAgent:
    return NERAgent()


@pytest.mark.asyncio
async def test_lab_value_with_unit_is_parsed(agent):
    raw = _raw("Hemoglobin: 12.1 g/dL")
    result = await agent.extract_entities(raw, patient_id="p1")
    labs = [e for e in result.entities if e.entity_type == EntityType.lab_value]
    assert len(labs) == 1
    assert labs[0].raw_value == "12.1"
    assert labs[0].unit_raw == "g/dL"
    assert labs[0].assertion_status == AssertionStatus.present
    assert not labs[0].ambiguity_flag


@pytest.mark.asyncio
async def test_lab_alias_without_value_is_flagged_ambiguous(agent):
    raw = _raw("Patient's hemoglobin was discussed but not yet resulted.")
    result = await agent.extract_entities(raw, patient_id="p1")
    labs = [e for e in result.entities if e.entity_type == EntityType.lab_value]
    assert len(labs) == 1
    assert labs[0].ambiguity_flag
    assert labs[0].unit_raw is None


@pytest.mark.asyncio
async def test_vital_sign_tagged_separately_from_lab_value(agent):
    raw = _raw("Heart rate 88 bpm.")
    result = await agent.extract_entities(raw, patient_id="p1")
    assert any(e.entity_type == EntityType.vital_sign for e in result.entities)


@pytest.mark.asyncio
async def test_medication_dosage_and_frequency_parsed(agent):
    raw = _raw("Metformin 1000mg BD.")
    result = await agent.extract_entities(raw, patient_id="p1")
    meds = [e for e in result.entities if e.entity_type == EntityType.medication]
    assert len(meds) == 1
    assert meds[0].raw_value == "Metformin"
    assert meds[0].unit_raw == "1000mg twice daily"


@pytest.mark.asyncio
async def test_dosage_does_not_bleed_into_next_medication(agent):
    """Regression test for a real bug caught during development: a wide
    lookahead window let the frequency parser pick up the *next* drug's
    frequency abbreviation on a densely packed medication line."""
    raw = _raw("Metformin 1000mg BD. Lisinopril 10mg OD.")
    result = await agent.extract_entities(raw, patient_id="p1")
    meds = {e.raw_value: e.unit_raw for e in result.entities if e.entity_type == EntityType.medication}
    assert meds["Metformin"] == "1000mg twice daily"
    assert meds["Lisinopril"] == "10mg once daily"


@pytest.mark.asyncio
async def test_pre_negation_detected(agent):
    raw = _raw("No hypertension noted on exam.")
    result = await agent.extract_entities(raw, patient_id="p1")
    dx = [e for e in result.entities if e.entity_type == EntityType.diagnosis]
    assert len(dx) == 1
    assert dx[0].assertion_status == AssertionStatus.absent


@pytest.mark.asyncio
async def test_post_negation_detected(agent):
    raw = _raw("Atrial fibrillation was ruled out.")
    result = await agent.extract_entities(raw, patient_id="p1")
    dx = [e for e in result.entities if e.entity_type == EntityType.diagnosis]
    assert len(dx) == 1
    assert dx[0].assertion_status == AssertionStatus.absent


@pytest.mark.asyncio
async def test_hypothetical_detected(agent):
    raw = _raw("If creatinine rises further, consider nephrology referral.")
    result = await agent.extract_entities(raw, patient_id="p1")
    labs = [e for e in result.entities if e.entity_type == EntityType.lab_value]
    assert len(labs) == 1
    assert labs[0].assertion_status == AssertionStatus.hypothetical


@pytest.mark.asyncio
async def test_possible_uncertainty_detected(agent):
    raw = _raw("Possible gout flare.")
    result = await agent.extract_entities(raw, patient_id="p1")
    dx = [e for e in result.entities if e.entity_type == EntityType.diagnosis]
    assert len(dx) == 1
    assert dx[0].assertion_status == AssertionStatus.possible


@pytest.mark.asyncio
async def test_family_history_flagged_not_patients_own(agent):
    raw = _raw("Family history of heart failure noted.")
    result = await agent.extract_entities(raw, patient_id="p1")
    dx = [e for e in result.entities if e.entity_type == EntityType.diagnosis]
    assert len(dx) == 1
    assert dx[0].ambiguity_flag
    assert "family" in dx[0].ambiguity_reason.lower()


@pytest.mark.asyncio
async def test_ocr_confidence_taken_from_overlapping_span_not_document_average(agent):
    lines = ["Hemoglobin: 12.1 g/dL", "Creatinine 1.8 mg/dL"]
    spans = [
        TextSpan(text=lines[0], confidence=0.99, page=1, span_type="text"),
        TextSpan(text=lines[1], confidence=0.40, page=1, span_type="text"),
    ]
    full_text = "\n".join(lines)
    raw = RawExtraction(
        document_id="d1", spans=spans, tables=[], full_text=full_text,
        avg_confidence=0.70, low_confidence_spans=[], ocr_engine="test",
        processing_time_ms=0,
    )
    result = await agent.extract_entities(raw, patient_id="p1")
    by_value = {e.raw_value: e.ocr_confidence for e in result.entities}
    assert by_value["12.1"] == pytest.approx(0.99)
    assert by_value["1.8"] == pytest.approx(0.40)


@pytest.mark.asyncio
async def test_short_acronym_alias_requires_word_boundary(agent):
    """'K' (potassium) should not fire inside an unrelated word."""
    raw = _raw("The kidney function is stable.")
    result = await agent.extract_entities(raw, patient_id="p1")
    assert not any(e.raw_value == "K" for e in result.entities)


@pytest.mark.asyncio
async def test_empty_document_produces_no_entities(agent):
    raw = _raw("")
    result = await agent.extract_entities(raw, patient_id="p1")
    assert result.entities == []
