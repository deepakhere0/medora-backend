import enum
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import ENUM as PgENUM, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin


class ReportType(str, enum.Enum):
    prescription      = "prescription"
    lab_report        = "lab_report"
    xray              = "xray"
    discharge_summary = "discharge_summary"
    other             = "other"


report_type_enum = PgENUM(
    "prescription", "lab_report", "xray",
    "discharge_summary", "other",
    name="report_type",
    create_type=False,
)


class Report(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "reports"

    __table_args__ = (
        Index("ix_reports_org_patient", "organization_id", "patient_id"),
        Index("ix_reports_org_appointment", "organization_id", "appointment_id"),
        Index("ix_reports_patient_type", "patient_id", "report_type"),
        {},
    )

    organization_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    patient_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    appointment_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("appointments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    uploaded_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    report_type: Mapped[str] = mapped_column(report_type_enum, nullable=False)
    file_url: Mapped[str] = mapped_column(Text, nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size_kb: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Patient self-upload fields (nullable for legacy org-admin uploads)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    upload_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    doctor_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ai_analysis: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_analysis_status: Mapped[str | None] = mapped_column(Text, nullable=True, default="pending")

    organization: Mapped["Organization"] = relationship(
        "Organization", back_populates="reports", lazy="noload"
    )
    patient: Mapped["Patient"] = relationship(
        "Patient", back_populates="reports", lazy="noload"
    )
    appointment: Mapped["Appointment"] = relationship(
        "Appointment", back_populates="reports", lazy="noload"
    )
    uploader: Mapped["User"] = relationship(
        "User",
        back_populates="reports",
        lazy="noload",
        foreign_keys="[Report.uploaded_by]",
    )
