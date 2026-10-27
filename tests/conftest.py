import os

# Must be set before any `arbiter.*` import — db.py/redis_client.py build their
# engine/client from settings at import time, so this is the only point we can
# redirect them to the test database and an isolated Redis db.
os.environ["DATABASE_URL"] = "postgresql+psycopg://localhost:5432/arbiter_test"
os.environ["REDIS_DB"] = "1"

from unittest.mock import AsyncMock, patch

import pytest

from arbiter.db import Base, SessionLocal, engine
from arbiter.redis_client import redis_client


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
async def _clean_state():
    yield
    from arbiter.models import Application, BureauData, Decision, Employment, Liability, LoanRequest
    from arbiter.models.outbox_events import OutboxEvents

    with SessionLocal() as session:
        session.query(OutboxEvents).delete()
        session.query(Decision).delete()
        session.query(BureauData).delete()
        session.query(Liability).delete()
        session.query(LoanRequest).delete()
        session.query(Employment).delete()
        session.query(Application).delete()
        session.commit()
    await redis_client.flushdb()


@pytest.fixture(autouse=True)
def _no_real_rag():
    """Prevent tests from hitting the real OpenAI API or the local Qdrant store."""
    with patch("arbiter.services.processdata.processRAGContent", new=AsyncMock(return_value={"status": "success", "detail": 1})):
        yield
