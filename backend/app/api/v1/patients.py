from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from app.api import deps
from app.schemas.api import TimelineResponse, InsightListResponse
from app.schemas.agent_messages import TrendSet, VerifiedInsight
from app.models.user import User
from app.models.document import Document
from app.models.insight import Insight
from app.schemas.auth import PatientResponse

router = APIRouter()

@router.get("/{patient_id}/summary", response_model=dict)
async def get_patient_summary(
    patient_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
):
    doc_count_result = await db.execute(select(func.count(Document.id)).where(Document.patient_id == patient_id))
    document_count = doc_count_result.scalar() or 0

    from app.models.clinical_entity import ClinicalEntity, EntityType
    from app.models.trend import Trend
    
    meds_count = await db.execute(select(func.count(ClinicalEntity.id)).where(ClinicalEntity.patient_id == patient_id, ClinicalEntity.entity_type == EntityType.medication))
    active_medications = meds_count.scalar() or 0
    
    metrics_count = await db.execute(select(func.count(func.distinct(Trend.metric_name))).where(Trend.patient_id == patient_id))
    tracked_metrics = metrics_count.scalar() or 0
    
    reviews_count = await db.execute(select(func.count(Insight.id)).where(Insight.patient_id == patient_id, Insight.requires_clinician_review == True, Insight.clinician_reviewed_by == None))
    pending_reviews = reviews_count.scalar() or 0

    insights_result = await db.execute(
        select(Insight).where(Insight.patient_id == patient_id).order_by(desc(Insight.id)).limit(3)
    )
    recent_insights_rows = insights_result.scalars().all()
    
    recent_insights = []
    for ri in recent_insights_rows:
        recent_insights.append({
            "insight_type": ri.insight_type.value if ri.insight_type else "general",
            "patient_facing_text": ri.patient_facing_text or ri.draft_text,
            "severity": ri.severity.value if ri.severity else "informational"
        })

    # Top trends for dashboard trend card
    from app.models.trend import Trend
    trends_result = await db.execute(
        select(Trend).where(Trend.patient_id == patient_id).order_by(desc(Trend.is_clinically_significant)).limit(3)
    )
    top_trends_rows = trends_result.scalars().all()
    top_trends = []
    for t in top_trends_rows:
        top_trends.append({
            "metric_name": t.metric_name,
            "metric_display": t.metric_name.replace("_", " ").title(),
            "direction": t.direction.value if hasattr(t.direction, "value") else str(t.direction),
            "data_point_count": t.data_point_count,
            "is_clinically_significant": t.is_clinically_significant,
        })

    # Recent documents
    docs_result = await db.execute(
        select(Document).where(Document.patient_id == patient_id).order_by(desc(Document.uploaded_at)).limit(5)
    )
    recent_docs_rows = docs_result.scalars().all()
    recent_documents = []
    for d in recent_docs_rows:
        recent_documents.append({
            "filename": d.original_filename,
            "status": d.processing_status.value if hasattr(d.processing_status, "value") else str(d.processing_status),
            "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
        })

    return {
        "active_medications": active_medications,
        "tracked_metrics": tracked_metrics,
        "document_count": document_count,
        "pending_reviews": pending_reviews,
        "recent_insights": recent_insights,
        "top_trends": top_trends,
        "recent_documents": recent_documents,
    }

@router.get("/{patient_id}/timeline", response_model=TimelineResponse)
async def get_patient_timeline(
    patient_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
):
    from app.models.clinical_entity import ClinicalEntity
    result = await db.execute(
        select(ClinicalEntity)
        .where(ClinicalEntity.patient_id == patient_id)
        .order_by(desc(ClinicalEntity.id))
    )
    entities = result.scalars().all()
    
    from collections import defaultdict
    import calendar
    
    # Group entities by Month Year
    groups = defaultdict(list)
    for e in entities:
        if e.entity_date:
            month_str = f"{calendar.month_name[e.entity_date.month]} {e.entity_date.year}"
            date_str = e.entity_date.strftime("%d %b")
        else:
            month_str = "Unknown Date"
            date_str = "Unknown"
            
        groups[month_str].append({
            "id": str(e.id),
            "date": date_str,
            "type": e.entity_type.value if hasattr(e.entity_type, "value") else str(e.entity_type),
            "label": e.normalized_value or e.raw_value,
            "value": e.normalized_value or e.raw_value,
            "unit": e.unit_canonical or e.unit_raw or "",
            "status": "normal",
            "doc": "Document",
            "confidence": e.confidence or 0.8
        })
        
    items = []
    for month, events in groups.items():
        items.append({
            "month": month,
            "events": events
        })
        
    return TimelineResponse(items=items, total=sum(len(g["events"]) for g in items), page=1, size=50, pages=1)

@router.get("/{patient_id}/trends", response_model=TrendSet)
async def get_patient_trends(
    patient_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
):
    from app.models.trend import Trend
    result = await db.execute(select(Trend).where(Trend.patient_id == patient_id))
    trends_db = result.scalars().all()
    
    from app.schemas.agent_messages import TrendObject
    trends_out = []
    for t in trends_db:
        trends_out.append(TrendObject(
            metric_name=t.metric_name,
            metric_canonical_code=t.metric_canonical_code,
            data_points=[],
            direction=t.direction,
            rate_of_change=t.rate_of_change,
            statistical_confidence=t.statistical_confidence,
            p_value=t.p_value,
            change_point_date=t.change_point_date,
            is_clinically_significant=t.is_clinically_significant,
            clinical_significance_reason=t.clinical_significance_reason,
            monitoring_gap_detected=False,
            expected_monitoring_interval_days=None,
            last_measurement_date=t.trend_end_date
        ))
        
    return TrendSet(patient_id=patient_id, trends=trends_out, gaps=[], insufficient_data_metrics=[], processing_time_ms=0)

@router.get("/{patient_id}/insights", response_model=InsightListResponse)
async def get_patient_insights(
    patient_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
):
    insights_result = await db.execute(
        select(Insight).where(Insight.patient_id == patient_id).order_by(desc(Insight.id))
    )
    insights = insights_result.scalars().all()
    
    items = []
    for i in insights:
        items.append(
            VerifiedInsight(
                draft_id=str(i.id),
                insight_db_id=i.id,
                final_text=i.final_text or i.draft_text,
                patient_facing_text=i.patient_facing_text or "",
                clinician_facing_text=i.clinician_facing_text or "",
                verification_status=i.verification_status.value if i.verification_status else "pending",
                verification_confidence=i.verification_confidence or 0.0,
                verification_rationale=i.verification_rationale or "",
                atomic_assertions=[],
                rejected_assertions=[],
                severity=i.severity.value if i.severity else "informational",
                requires_clinician_review=i.requires_clinician_review or False
            )
        )
        
    return InsightListResponse(items=items, total=len(items), page=1, size=50, pages=1)
