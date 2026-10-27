from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from arbiter.db import Base

if TYPE_CHECKING:
    from arbiter.models.application import Application


class LoanRequest(Base):
    __tablename__ = "loan_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    # One loan request per application
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), unique=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    purpose: Mapped[str] = mapped_column(String(100))
    tenure_months: Mapped[int]
    declared_monthly_income: Mapped[Decimal] = mapped_column(Numeric(14, 2))

    application: Mapped["Application"] = relationship(back_populates="loan_request")
