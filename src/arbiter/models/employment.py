from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from arbiter.db import Base

if TYPE_CHECKING:
    from arbiter.models.application import Application


class Employment(Base):
    __tablename__ = "employment"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), unique=True)
    employer: Mapped[str] = mapped_column(String(100))
    years_at_company: Mapped[Decimal] = mapped_column(Numeric(4, 1))
    # Plain string, validated by the Pydantic Literal
    employment_type: Mapped[str] = mapped_column(String(20))

    application: Mapped["Application"] = relationship(back_populates="employment")
