# Import every model so its table is registered on Base.metadata
from arbiter.models.application import Application
from arbiter.models.bureau_data import BureauData
from arbiter.models.decision import Decision
from arbiter.models.employment import Employment
from arbiter.models.liability import Liability
from arbiter.models.loan_request import LoanRequest
from arbiter.models.outbox_events import OutboxEvents

__all__ = [
    "Application",
    "BureauData",
    "Decision",
    "Employment",
    "Liability",
    "LoanRequest",
    "OutboxEvents"
]
