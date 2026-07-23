"""
Tests for Agent 4: Normalization & Coding.

Runs against the project's real knowledge_base ontology + reference
range files, same as the NER tests, so these double as a regression
check on the data files themselves.
"""
import pytest

from app.agents.normalization.agent import NormalizationAgent
from app.models.clinical_entity import AssertionStatus, EntityType
from app.schemas.agent_messages import ClinicalEntitySet, ExtractedEntity


def _entity(entity_type, raw_value, entity_label=None, unit_raw=None, temp_id="t1"):
    return ExtractedEntity(
        temp_id=temp_id,
        entity_type=entity_type,
        raw_value=raw_value,
        entity_label=entity_label,
        unit_raw=unit_raw,
        source_span_start=0,
        source_span_end=0,
        ocr_confidence=0.9,
        ner_confidence=0.9,
        combined_confidence=0.81,
        is_negated=False,
        assertion_status=AssertionStatus.present,
        related_entities=[],
        ambiguity_flag=False,
    )


def _entity_set(*entities):
    return ClinicalEntitySet(
        document_id="00000000-0000-0000-0000-000000000001",
        patient_id="00000000-0000-0000-0000-000000000002",
        entities=list(entities),
        intra_document_conflicts=[],
        processing_time_ms=0,
    )


@pytest.fixture(scope="module")
def agent() -> NormalizationAgent:
    return NormalizationAgent()


@pytest.mark.asyncio
async def test_exact_match_via_entity_label_for_lab(agent):
    es = _entity_set(_entity(EntityType.lab_value, "12.1", entity_label="Hemoglobin", unit_raw="g/dL"))
    result = await agent.normalize(es)
    assert len(result.coded_entities) == 1
    coded = result.coded_entities[0]
    assert coded.canonical_code == "718-7"
    assert coded.coding_system == "LOINC"
    assert coded.coding_method == "exact"
    assert coded.normalized_value == "12.1"


@pytest.mark.asyncio
async def test_reference_range_depends_on_sex_and_age(agent):
    es = _entity_set(_entity(EntityType.lab_value, "12.1", entity_label="Hemoglobin"))
    male = await agent.normalize(es, patient_sex="M", patient_age=45)
    female = await agent.normalize(es, patient_sex="F", patient_age=45)
    assert (male.coded_entities[0].reference_range_low, male.coded_entities[0].reference_range_high) == (13.5, 17.5)
    assert (female.coded_entities[0].reference_range_low, female.coded_entities[0].reference_range_high) == (12.0, 15.5)


@pytest.mark.asyncio
async def test_reference_range_defaults_to_adult_when_age_unknown(agent):
    """Adult bands, not a peds/adult mix, when age isn't supplied at all."""
    es = _entity_set(_entity(EntityType.lab_value, "12.1", entity_label="Hemoglobin"))
    result = await agent.normalize(es)
    coded = result.coded_entities[0]
    assert coded.reference_range_low >= 12.0  # not the pediatric 11.0 floor


@pytest.mark.asyncio
async def test_multi_band_lab_reports_the_normal_band_not_the_patients_own_band(agent):
    """HbA1c of 7.2 falls in the 'Diabetes' interpretation band, but the
    reference range returned should be the Normal band (4.0-5.6) -- that's
    what 'reference range' means clinically, not the value's own category."""
    es = _entity_set(_entity(EntityType.lab_value, "7.2", entity_label="HbA1c"))
    result = await agent.normalize(es)
    coded = result.coded_entities[0]
    assert (coded.reference_range_low, coded.reference_range_high) == (4.0, 5.6)


@pytest.mark.asyncio
async def test_exact_match_via_entity_label_for_medication(agent):
    es = _entity_set(_entity(EntityType.medication, "Metformin", entity_label="Metformin",
                              unit_raw="1000mg twice daily"))
    result = await agent.normalize(es)
    coded = result.coded_entities[0]
    assert coded.coding_system == "RxNorm"
    assert coded.coding_method == "exact"
    assert coded.coding_confidence == pytest.approx(0.97)


@pytest.mark.asyncio
async def test_fuzzy_match_for_medication_typo_without_entity_label(agent):
    """No entity_label (simulating a non-dictionary upstream source) but
    a near-miss spelling should still resolve via fuzzy matching."""
    es = _entity_set(_entity(EntityType.medication, "Metfromin"))
    result = await agent.normalize(es)
    assert len(result.coded_entities) == 1
    coded = result.coded_entities[0]
    assert coded.coding_method == "fuzzy"
    assert coded.normalized_value == "Metformin"


@pytest.mark.asyncio
async def test_exact_match_for_diagnosis(agent):
    es = _entity_set(_entity(EntityType.diagnosis, "Type 2 Diabetes", entity_label="Type 2 Diabetes"))
    result = await agent.normalize(es)
    coded = result.coded_entities[0]
    assert coded.coding_system == "ICD-10"
    assert coded.canonical_code  # non-empty


@pytest.mark.asyncio
async def test_lab_without_entity_label_is_unmatched(agent):
    """A lab value with no name attached (entity_label missing) can't be
    coded -- raw_value is just the number, there's nothing to look up."""
    es = _entity_set(_entity(EntityType.lab_value, "42"))
    result = await agent.normalize(es)
    assert result.coded_entities == []
    assert len(result.unmatched_entities) == 1


@pytest.mark.asyncio
async def test_gibberish_medication_is_unmatched_not_forced(agent):
    es = _entity_set(_entity(EntityType.medication, "Zzzblorp9000"))
    result = await agent.normalize(es)
    assert result.coded_entities == []
    assert len(result.unmatched_entities) == 1


@pytest.mark.asyncio
async def test_vital_sign_uses_lab_coding_path(agent):
    es = _entity_set(_entity(EntityType.vital_sign, "145", entity_label="BloodPressureSystolic", unit_raw="mmHg"))
    result = await agent.normalize(es)
    coded = result.coded_entities[0]
    assert coded.canonical_code == "8480-6"
    assert coded.unit_canonical == "mmHg"


@pytest.mark.asyncio
async def test_non_numeric_lab_value_is_unmatched(agent):
    es = _entity_set(_entity(EntityType.lab_value, "Hemoglobin", entity_label="Hemoglobin"))
    result = await agent.normalize(es)
    assert result.coded_entities == []
    assert len(result.unmatched_entities) == 1


@pytest.mark.asyncio
async def test_empty_entity_set_produces_empty_result(agent):
    es = _entity_set()
    result = await agent.normalize(es)
    assert result.coded_entities == []
    assert result.unmatched_entities == []
