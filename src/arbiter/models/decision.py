from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from arbiter.db import Base

if TYPE_CHECKING:
    from arbiter.models.application import Application


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    # One decision per application
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), unique=True)
    verdict: Mapped[str] = mapped_column(String(20))  # APPROVED / CONDITIONAL / DENIED
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 2))  # 0-100
    # Audit trail of rules applied
    rules_json: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    decision_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    reviewed_by: Mapped[str | None] = mapped_column(String(100))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    application: Mapped["Application"] = relationship(back_populates="decision")
