from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, File, UploadFile, Form, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.api import deps
from app.schemas.api import DocumentUploadResponse, PipelineStatusResponse
from app.models.user import User
from app.models.document import Document, DocumentType, ProcessingStatus

router = APIRouter()

from app.services.storage import storage_service
from app.worker import process_document_pipeline

@router.post("/upload", response_model=List[DocumentUploadResponse])
async def upload_documents(
    patient_id: UUID = Form(...),
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
):
    # 1. Verify user has access to patient_id (Skipped for presentation simplicity)
    
    responses = []
    for f in files:
        # Read bytes
        file_data = await f.read()
        
        # 2. Upload file bytes to MinIO
        object_name = f"{patient_id}/{f.filename}"
        storage_path = await storage_service.upload_document(object_name, file_data, f.content_type)
        
        # 3. Create Document DB record
        db_doc = Document(
            patient_id=patient_id,
            original_filename=f.filename,
            document_type=DocumentType.unknown,
            storage_path=storage_path,
            processing_status=ProcessingStatus.queued
        )
        db.add(db_doc)
        await db.commit()
        await db.refresh(db_doc)
        
        # 4. Enqueue Celery tasks for LangGraph ingestion pipeline
        envelope = {
            "document_id": str(db_doc.id),
            "patient_id": str(patient_id),
            "storage_path": storage_path,
            "document_type": DocumentType.unknown.value,
            "quality_score": 0.0,
            "quality_flags": [],
            "routing": "ocr",
            "metadata": {"original_filename": f.filename}
        }
        task = process_document_pipeline.delay(envelope, str(patient_id))
        
        # Update DB with Celery task ID
        db_doc.pipeline_job_id = task.id
        await db.commit()
        
        responses.append(
            DocumentUploadResponse(
                document_id=db_doc.id,
                job_id=task.id,
                filename=f.filename,
                status=ProcessingStatus.queued,
                message="Document uploaded and queued for processing"
            )
        )
    return responses

@router.get("/{document_id}/status", response_model=PipelineStatusResponse)
async def get_document_status(
    document_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
):
    from sqlalchemy import select
    result = await db.execute(select(Document).where(Document.id == document_id))
    db_doc = result.scalar_one_or_none()
    
    if not db_doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    status_map = {
        ProcessingStatus.queued: (0, "Queued"),
        ProcessingStatus.ingesting: (10, "Ingestion & Triage"),
        ProcessingStatus.ocr: (30, "OCR & Layout Extraction"),
        ProcessingStatus.ner: (50, "Medical Entity Recognition"),
        ProcessingStatus.normalizing: (60, "Ontology Normalization"),
        ProcessingStatus.trend_analysis: (70, "Trend Analysis"),
        ProcessingStatus.reasoning: (80, "Reasoning & Insight Generation"),
        ProcessingStatus.verifying: (90, "Independent Verification"),
        ProcessingStatus.complete: (100, "Complete"),
        ProcessingStatus.failed: (0, "Failed"),
        ProcessingStatus.needs_rescan: (0, "Needs Rescan"),
    }
    
    progress, step_name = status_map.get(db_doc.processing_status, (0, "Unknown"))
    
    return PipelineStatusResponse(
        document_id=db_doc.id,
        status=db_doc.processing_status,
        current_step=step_name,
        progress_percentage=progress
    )

@router.delete("/{document_id}")
async def delete_document(
    document_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
):
    from sqlalchemy import delete
    result = await db.execute(delete(Document).where(Document.id == document_id))
    await db.commit()
    
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Document not found")
        
    return {"message": "Document deleted"}
