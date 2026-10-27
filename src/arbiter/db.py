
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from arbiter.config import settings

# sync engine, owns the connection pool
engine = create_engine(settings.database_url, echo=True)

# Session factory, one session per unit of work
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_application(id: int):
    from arbiter.models.application import Application
    data: Any
    with SessionLocal() as session:
        data = session.get(Application, id)
    return data

def get_decision(id: int):
    from arbiter.models.decision import Decision
    data: Any
    with SessionLocal() as session:
        data = session.get(Decision, id)
        return data

def is_loan_accepted(id: int) -> bool:
    from arbiter.models.application import Application

    # Read inside the session because loan_request is lazy-loaded
    with SessionLocal() as session:
        application = session.get(Application, id)
        return application.loan_request.amount > 70000

def get_decision_context(application_id: int) -> dict | None:
    from arbiter.models.application import Application

    # Build a plain dict inside the session because the relationships are lazy-loaded
    with SessionLocal() as session:
        application = session.get(Application, application_id)
        if application is None or application.decision is None:
            return None
        return {
            "verdict": application.decision.verdict,
            "rules": application.decision.rules_json,
            "purpose": application.loan_request.purpose,
            "amount": float(application.loan_request.amount),
            "employment_type": application.employment.employment_type,
        }

def get_decision_for_application(application_id: int) -> dict | None:
    from arbiter.models.application import Application

    # Build a plain dict inside the session — decision is lazy-loaded
    with SessionLocal() as session:
        application = session.get(Application, application_id)
        if application is None or application.decision is None:
            return None
        decision = application.decision
        return {
            "id": decision.id,
            "application_id": decision.application_id,
            "verdict": decision.verdict,
            "confidence": float(decision.confidence),
            "rules_json": decision.rules_json,
            "decision_timestamp": decision.decision_timestamp,
            "reviewed_by": decision.reviewed_by,
            "reviewed_at": decision.reviewed_at,
        }

def save_application(dataSerialise):
    with SessionLocal() as session:
        session.add(dataSerialise)
        session.commit()
        print(f"data saved {dataSerialise.applicant_name}")
        # id is populated at commit so its safe to read after session closes
        return dataSerialise.id

def save_application_with_events(application, build_events):
    # Same session/commit as the application so the outbox rows are written
    # in the same transaction as the business data (atomic, no dual-write gap)
    with SessionLocal() as session:
        session.add(application)
        session.flush()  # assigns application.id without committing yet
        for event in build_events(application.id):
            session.add(event)
        session.commit()
        return application.id

def getPublishEvent():
    from arbiter.models.outbox_events import OutboxEvents
    statement = select(OutboxEvents).where(OutboxEvents.published_at.is_(None))
    with SessionLocal() as session:
        # materialize rows before the session closes
        return session.execute(statement).scalars().all()

def updataPublisEvents(id: int):
    from arbiter.models.outbox_events import OutboxEvents
    statement = update(OutboxEvents).where(OutboxEvents.id == id).values(published_at=datetime.now(UTC))
    with SessionLocal() as session:
        session.execute(statement)
        session.commit()
    return True

class Base(DeclarativeBase):
    """Base class for all ORM tables."""
