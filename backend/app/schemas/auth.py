from typing import Optional
from uuid import UUID
from datetime import date
from pydantic import BaseModel, EmailStr
from app.models.user import UserRole

class Token(BaseModel):
    access_token: str
    token_type: str
    
class TokenData(BaseModel):
    id: Optional[str] = None
    role: Optional[UserRole] = None

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    role: UserRole

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: UUID
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    is_verified: bool

class PatientCreate(BaseModel):
    date_of_birth: date
    sex: str
    blood_type: Optional[str] = None

class PatientResponse(BaseModel):
    id: UUID
    user_id: UUID
    date_of_birth: date
    sex: str
    blood_type: Optional[str] = None
    known_conditions: Optional[list[str]] = None
    known_medications: Optional[list[str]] = None
    allergies: Optional[list[str]] = None
    consent_given: bool
