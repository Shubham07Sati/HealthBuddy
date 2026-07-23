"""
LMIS User Model
===============
Represents an application user (patient, clinician, or admin).
Has a 1-to-1 optional relationship with the Patient profile.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import UUIDBase

if TYPE_CHECKING:
    from app.models.patient import Patient


class UserRole(str, enum.Enum):
    """Application-level role that controls access permissions."""

    patient = "patient"
    clinician = "clinician"
    admin = "admin"


class User(UUIDBase):
    """Application user with JWT-based authentication.

    Relationships
    -------------
    patient_profile : Patient
        The patient profile linked to this user (only for ``role=patient``).
    """

    __tablename__ = "users"

    # ─── Identity ─────────────────────────────────────────────────────────────
    email: Mapped[str] = mapped_column(
        String(320),
        nullable=False,
        unique=True,
        index=True,
        doc="RFC-5321 email address — used as the login username",
    )
    hashed_password: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
        doc="Bcrypt-hashed password; never store plaintext",
    )
    full_name: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        default="",
        doc="Display name of the user",
    )

    # ─── Role & Status ────────────────────────────────────────────────────────
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role_enum"),
        nullable=False,
        default=UserRole.patient,
        index=True,
        doc="Access-control role",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        doc="Soft-disable an account without deleting it",
    )
    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        doc="True after email verification",
    )
    last_login: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="UTC timestamp of the user's last successful login",
    )

    # ─── Relationships ────────────────────────────────────────────────────────
    patient_profile: Mapped[Optional["Patient"]] = relationship(
        "Patient",
        back_populates="user",
        uselist=False,
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} role={self.role.value}>"
