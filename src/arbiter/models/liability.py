from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from arbiter.db import Base

if TYPE_CHECKING:
    from arbiter.models.application import Application


class Liability(Base):
    __tablename__ = "liabilities"

    id: Mapped[int] = mapped_column(primary_key=True)
    # One application can have many liabilities
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), index=True)
    type: Mapped[str] = mapped_column(String(50))
    outstanding: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    emi: Mapped[Decimal] = mapped_column(Numeric(14, 2))

    application: Mapped["Application"] = relationship(back_populates="liabilities")
