from fastapi import APIRouter
from app.api.v1 import auth, documents, patients

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(patients.router, prefix="/patients", tags=["patients"])
