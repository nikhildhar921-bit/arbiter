
import asyncio
import json
import logging
import uuid
from fastapi import HTTPException, UploadFile
from pypdf import PdfReader
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter, SimpleSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource


provider = TracerProvider(resource=Resource.create({"service.name": "arbiter"}))
provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))  # prints spans to stdout, no collector needed
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))  # ships to Jaeger at http://localhost:4318/v1/traces
trace.set_tracer_provider(provider)

tracer = trace.get_tracer(__name__)

from arbiter.constant.constant import (
    IDEMPOTENCY_PENDING_TTL_SECONDS,
    IDEMPOTENCY_SUBMITTED_TTL_SECONDS,
    loanApplicationClass,
)
from arbiter.redis_client import redis_client
from arbiter.services import processFile
from arbiter.services.processdata import get_publish_events, receiveLoanApplication as save_loan_application, get_application as getApplication, get_decision as getDec, get_decision_for_application as getDecisionForApplication, is_loan_accepted as isLoanAccepted, processRAGContent, save_publish_events, searchFromRAGFunc, keywordSearchFromRAGFunc, retrieveForDecisionFunc, parseLoanApplicationText
import io

log = logging.getLogger(__name__)


async def publish_events():
    resp = await get_publish_events()
    for row in resp:
        try:
            log.info("publishing event id=%s type=%s payload=%s", row.id, row.event_type, row.payload)
            await save_publish_events(row.id)
        except Exception:
            log.exception("publish event crashed for event id=%s", row.id)


async def keepRunning():
    while True:
        await publish_events()
        await asyncio.sleep(5)  # wait before checking again, without blocking the event loop

async def retrieveForDecision(application_id: int, k: int):
    with tracer.start_as_current_span("retrieveForDecision") as span:
        result = await retrieveForDecisionFunc(application_id, k)
        if result is None:
                raise HTTPException(status_code=404, detail="No decision found for this application")
        span.set_attribute('loan_decision_retrive', {"explanation": result["explanation"], "application_id": result["application_id"]})
    return result


async def searchRAG(input: str, mode: str = "semantic", limit: int = 3):
    if mode == "keyword":
        return await keywordSearchFromRAGFunc(input, limit)
    return await searchFromRAGFunc(input, limit)


async def loadFileForRAG(file: UploadFile):
    try:
        bytes = await file.read()
        if file.filename.endswith(".pdf"):
            pdfFile = io.BytesIO(bytes)
            reader = PdfReader(pdfFile)
            data = await processFile(reader)
            return await processRAGContent(data["text"])
        else:
            content = bytes.decode("utf-8")
            data = {"text": content}
            return await processRAGContent(data["text"])
    except HTTPException:
        raise
    except Exception as e:
        log.exception("rag extraction crashed")
        raise HTTPException(status_code=500, detail=str(e)) from e


async def receiveLoanApplicationFromFile(file: UploadFile):
    try:
        raw_bytes = await file.read()
        if file.filename.endswith(".pdf"):
            pdfFile = io.BytesIO(raw_bytes)
            reader = PdfReader(pdfFile)
            extracted = await processFile(reader)
            text = extracted["text"]
        else:
            text = raw_bytes.decode("utf-8")

        parsed = parseLoanApplicationText(text)

        # same file content always gives same idempotency key
        idempotency_key = uuid.uuid5(uuid.NAMESPACE_OID, raw_bytes.hex())

        data = loanApplicationClass(
            applicant=parsed.applicant,
            loan_request=parsed.loan_request,
            employment=parsed.employment,
            liabilities=parsed.liabilities,
            idempotency_key=idempotency_key,
        )
        return await receiveLoanApplication(data)
    except HTTPException:
        raise
    except Exception as e:
        log.exception("loan application extraction crashed")
        raise HTTPException(status_code=500, detail=str(e)) from e


async def receiveLoanApplication(data: loanApplicationClass):
    key = f"idempotency:{data.idempotency_key}"

    with tracer.start_as_current_span("handle_loan_application") as span:
        span.set_attribute('loan_app_receive', key)


        # Atomically claim the key so concurrent requests can't both win
        claimed = await redis_client.set(
            key,
            json.dumps({"status": "pending"}),
            nx=True,
            ex=IDEMPOTENCY_PENDING_TTL_SECONDS,
        )
        print(claimed)
        if not claimed:
            print('not claimed')
            existing_raw = await redis_client.get(key)
            if existing_raw is not None:
                existing = json.loads(existing_raw)
                if existing["status"] == "submitted":
                    # Already done, replay the original result
                    return existing["result"]
            # Still pending or just expired, ask the caller to retry
            raise HTTPException(
                status_code=409,
                detail="An application with this idempotency_key is already being processed",
            )

        result = await save_loan_application(data)

        print(result)
        await redis_client.set(
            key,
            json.dumps({"status": "submitted", "result": result}),
            ex=IDEMPOTENCY_SUBMITTED_TTL_SECONDS,
        )
        span.set_attribute('redis_set', f'{key}_redis')

    return result


async def get_application(id: int):
    return await getApplication(id)


async def get_decision(id: int):
    return await getDec(id)


async def get_decision_for_application(application_id: int):
    result = await getDecisionForApplication(application_id)
    if result is None:
        raise HTTPException(status_code=404, detail="No decision found for this application")
    return result


async def is_loan_accepted(id: int) -> bool:
    return await isLoanAccepted(id)
