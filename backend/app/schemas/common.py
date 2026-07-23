from typing import TypeVar, Generic, List, Optional
from pydantic import BaseModel, Field, ConfigDict

T = TypeVar("T")

class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    size: int
    pages: int

class ErrorResponse(BaseModel):
    detail: str
    code: str

class SuccessResponse(BaseModel):
    message: str

class ConfidenceScore(BaseModel):
    score: float = Field(..., ge=0.0, le=1.0)

class BoundingBox(BaseModel):
    x: float
    y: float
    width: float
    height: float
    page: int

class DateRange(BaseModel):
    start_date: str
    end_date: str
