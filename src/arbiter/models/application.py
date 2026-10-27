import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from arbiter.db import Base

if TYPE_CHECKING:
    from arbiter.models.bureau_data import BureauData
    from arbiter.models.decision import Decision
    from arbiter.models.employment import Employment
    from arbiter.models.liability import Liability
    from arbiter.models.loan_request import LoanRequest


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    applicant_name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str] = mapped_column(String(15))
    email: Mapped[str] = mapped_column(String(255))
    pan: Mapped[str] = mapped_column(String(10))
    # unique backstop for idempotency if Redis is flushed
    idempotency_key: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    loan_request: Mapped["LoanRequest"] = relationship(back_populates="application", uselist=False)
    employment: Mapped["Employment"] = relationship(back_populates="application", uselist=False)
    liabilities: Mapped[list["Liability"]] = relationship(back_populates="application")
    bureau_data: Mapped["BureauData | None"] = relationship(
        back_populates="application", uselist=False
    )
    decision: Mapped["Decision | None"] = relationship(back_populates="application", uselist=False)
