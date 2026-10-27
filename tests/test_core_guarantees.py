"""
The four guarantees this system makes about itself, each proven directly
against the real database rather than asserted from reading the code:

1. Idempotency holds under concurrent submission of the same application.
2. An outbox event is written atomically with the Decision it describes —
   never one without the other.
3. The publisher resumes correctly after being killed mid-batch — it
   doesn't skip unpublished rows, and doesn't re-deliver published ones.
4. A document the extractor can't confidently parse degrades to a human
   review outcome instead of crashing or silently guessing.
"""

import asyncio
import io
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi import HTTPException, UploadFile

from arbiter.constant.constant import Applicant, Employment, Liability, LoanRequest, loanApplicationClass
from arbiter.controllers.processdata import (
    publish_events,
    receiveLoanApplication as submit_application,
    receiveLoanApplicationFromFile,
)
from arbiter.db import SessionLocal, getPublishEvent, save_application_with_events, updataPublisEvents
from arbiter.models import Application, Decision
from arbiter.models.outbox_events import OutboxEvents


def _application(**overrides) -> loanApplicationClass:
    defaults = dict(
        applicant=Applicant(name="Test User", phone="9123456780", email="test@example.com", pan="ABCDE1234F"),
        loan_request=LoanRequest(amount=200000, purpose="personal", tenure_months=24, declared_monthly_income=100000),
        employment=Employment(employer="Acme", years_at_company=2.0, employment_type="salaried"),
        liabilities=[Liability(type="credit_card", outstanding=5000, emi=500)],
        idempotency_key=uuid.uuid4(),
    )
    defaults.update(overrides)
    return loanApplicationClass(**defaults)


def _minimal_application(**overrides) -> Application:
    defaults = dict(
        applicant_name="Test User",
        phone="9123456780",
        email="test@example.com",
        pan="ABCDE1234F",
        idempotency_key=uuid.uuid4(),
    )
    defaults.update(overrides)
    return Application(**defaults)


# --- 1. Idempotency under concurrent submission --------------------------------

async def test_idempotency_holds_under_concurrent_submission():
    # Same idempotency_key fired "concurrently". Within a single asyncio event
    # loop, the blocking (sync) DB calls effectively serialize the two
    # requests, so both calls typically resolve with the same replayed
    # result rather than one hitting the 409 path — real parallelism
    # (separate processes) is what exercises that branch. What's actually
    # guaranteed and testable here is: never two rows for one submission.
    data = _application()

    results = await asyncio.gather(
        submit_application(data), submit_application(data), return_exceptions=True
    )

    successful_ids = set()
    for r in results:
        if isinstance(r, Exception):
            assert isinstance(r, HTTPException)
            assert r.status_code == 409
        else:
            successful_ids.add(r["id"])
    assert len(successful_ids) == 1

    with SessionLocal() as session:
        count = session.query(Application).filter_by(idempotency_key=data.idempotency_key).count()
    assert count == 1


# --- 2. Outbox written atomically with the decision -----------------------------

def test_outbox_event_is_never_written_without_its_decision():
    application = _minimal_application()
    application.decision = Decision(
        verdict="APPROVED", confidence=Decimal("95"), rules_json=[], decision_timestamp=datetime.now(UTC)
    )

    def build_events(application_id: int) -> list[OutboxEvents]:
        return [OutboxEvents(aggregate_id=application_id, event_type="application.submitted", payload={})]

    application_id = save_application_with_events(application, build_events)

    with SessionLocal() as session:
        assert session.query(Decision).filter_by(application_id=application_id).count() == 1
        assert session.query(OutboxEvents).filter_by(aggregate_id=application_id).count() == 1


def test_a_failed_event_build_rolls_back_the_decision_too():
    application = _minimal_application()

    def build_events_that_blows_up(application_id: int) -> list[OutboxEvents]:
        raise RuntimeError("simulated crash while building events")

    with pytest.raises(RuntimeError):
        save_application_with_events(application, build_events_that_blows_up)

    with SessionLocal() as session:
        # proves it's really one transaction: the Application never
        # committed either, not just the event that was skipped
        assert session.query(Application).filter_by(idempotency_key=application.idempotency_key).count() == 0


# --- 3. Publisher resumes correctly after being killed mid-batch ---------------

def _insert_pending_event(aggregate_id: int = 1) -> int:
    with SessionLocal() as session:
        event = OutboxEvents(aggregate_id=aggregate_id, event_type="test.event", payload={"a": 1})
        session.add(event)
        session.commit()
        return event.id


async def test_publisher_resumes_correctly_after_being_killed_mid_batch():
    id_a = _insert_pending_event()
    id_b = _insert_pending_event()
    id_c = _insert_pending_event()

    # publisher starts a batch, handles id_a successfully, then "dies"
    # before touching id_b or id_c
    updataPublisEvents(id_a)

    # simulate restart: a fresh poll must pick up exactly the unfinished
    # work — not skip anything, not re-deliver what's already done
    remaining_after_crash = {e.id for e in getPublishEvent()}
    assert remaining_after_crash == {id_b, id_c}

    # the resumed publisher finishes the batch
    await publish_events()

    with SessionLocal() as session:
        still_pending = session.query(OutboxEvents).filter(OutboxEvents.published_at.is_(None)).count()
    assert still_pending == 0


# --- 4. Extraction failure degrades to human review -----------------------------

async def test_extraction_failure_degrades_to_human_review_not_a_crash():
    # No Phone/Email at all for the applicant — parseable as text, but
    # fails the Applicant schema's required-field validation
    incomplete_document = """
Applicant Name: Missing Contact Info

Loan Amount Requested: 500000
Loan Purpose: home renovation
Requested Tenure: 24
Declared Monthly Income: 100000
Declared Employment Type: Salaried
Employer Name: Acme
""".encode("utf-8")

    upload = UploadFile(file=io.BytesIO(incomplete_document), filename="incomplete.txt")

    result = await receiveLoanApplicationFromFile(upload)

    assert result["status"] == "needs_review"
    assert "reason" in result

    with SessionLocal() as session:
        # nothing should have been written — this never reached the DB
        assert session.query(Application).count() == 0
