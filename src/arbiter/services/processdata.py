import hashlib
import math
import re
import uuid
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from openai import AsyncOpenAI
from qdrant_client.models import Distance, PointStruct, VectorParams
from arbiter.constant.constant import (
    ExtractedLoanApplication,
    loanApplicationClass,
    chunk,
    # Aliased to avoid clashing with the ORM classes of the same name
    Applicant as PydanticApplicant,
    LoanRequest as PydanticLoanRequest,
    Employment as PydanticEmployment,
    Liability as PydanticLiability,
)
from arbiter.db import (
    getPublishEvent,
    save_application_with_events,
    get_application as getApp,
    get_decision as getDec,
    is_loan_accepted as isLoanAccepted,
    get_decision_context as getDecisionContext,
    get_decision_for_application as getDecisionForApplication,
    updataPublisEvents,
)
from arbiter.models import Application, Employment, Liability, LoanRequest, Decision
from arbiter.config import settings
import qdrant_client

from arbiter.models.outbox_events import OutboxEvents

from opentelemetry import trace

client = AsyncOpenAI(api_key=settings.OPEN_AI_KEY)
qdrantClient = qdrant_client.QdrantClient(path="qdrant_data")
collection_name = "rag_arbiter"
if not qdrantClient.collection_exists(collection_name):
    qdrantClient.create_collection(
        collection_name,
        vectors_config=VectorParams(size=3072, distance=Distance.COSINE),
    )
EMBED_MODEL = "text-embedding-3-large"

async def searchFromRAGFunc(input: str, limit: int = 3):
    resp = await client.embeddings.create(model=EMBED_MODEL, input=input)
    query_vector = resp.data[0].embedding
    data = qdrantClient.query_points(
        collection_name=collection_name,
        query= query_vector,
        limit=limit,
        with_payload=True,
        )
    return [{"score": p.score, "text": p.payload["text"]} for p in data.points]


def buildDecisionQuery(context: dict) -> str:
    # No PII, this text is sent to the embeddings API
    lines = [
        f"Loan decision: {context['verdict']}",
        f"Loan purpose: {context['purpose']}",
        f"Loan amount: {context['amount']}",
        f"Employment type: {context['employment_type']}",
    ]
    for rule in context["rules"]:
        outcome = "passed" if rule["passed"] else "failed"
        lines.append(f"Rule {rule['rule_name']} {outcome}: {rule.get('details') or ''}")
    return "\n".join(lines)

async def get_publish_events():
    data = getPublishEvent()
    return data

async def save_publish_events(id: int):
    updataPublisEvents(id)
    return True

async def retrieveForDecisionFunc(application_id: int, k: int = 3):
    context = getDecisionContext(application_id)
    if context is None:
        return None
    query = buildDecisionQuery(context)
    chunks = await searchFromRAGFunc(query, limit=k)

    # Explain the decision using only the retrieved policy text
    policy_text = "\n---\n".join(c["text"] for c in chunks) or "No matching policy text was found."
    response = await client.responses.create(
        model="gpt-4o",
        input=[
            {
                "role": "system",
                "content": (
                    "Explain this loan decision in plain language, using ONLY "
                    "the policy text given below. If the policy text doesn't "
                    "clearly support a reason, say the explanation is "
                    "inconclusive rather than inventing one."
                ),
            },
            {"role": "user", "content": f"Decision:\n{query}\n\nRelevant policy:\n{policy_text}"},
        ],
    )

    return {
        "application_id": application_id,
        "query": query,
        "chunks": chunks,
        "explanation": response.output_text,
    }


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


async def keywordSearchFromRAGFunc(input: str, limit: int = 3):
    chunks = []
    offset = None
    while True:
        points, offset = qdrantClient.scroll(
            collection_name, limit=256, offset=offset, with_payload=True, with_vectors=False
        )
        chunks.extend(points)
        if offset is None:
            break

    if not chunks:
        return []

    docs = [tokenize(p.payload["text"]) for p in chunks]
    avg_len = sum(len(d) for d in docs) / len(docs)
    doc_freq = Counter(term for d in docs for term in set(d))

    # BM25 scoring
    k1, b = 1.5, 0.75
    query_terms = set(tokenize(input))
    results = []
    for p, doc in zip(chunks, docs):
        term_freq = Counter(doc)
        score = 0.0
        for term in query_terms:
            tf = term_freq[term]
            if tf == 0:
                continue
            idf = math.log((len(docs) - doc_freq[term] + 0.5) / (doc_freq[term] + 0.5) + 1)
            score += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * len(doc) / avg_len))
        if score > 0:
            results.append({"score": round(score, 4), "text": p.payload["text"]})

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:limit]


async def embed(text: list[str]):
    if settings.load_test_mode:
        # Load-test stub: skip the real OpenAI call and Qdrant write — not used
        # outside a load-test run, real requests always go through the branch below.
        return 1
    resp = await client.embeddings.create(model=EMBED_MODEL, input=text)
    # Unique id per point so new embeddings don't overwrite old ones
    points = [
        PointStruct(id=str(uuid.uuid4()), vector=data.embedding, payload={"text": text})
        for data, text in zip(resp.data, text)
    ]
    qdrantClient.upsert(collection_name, points)
    return 1


async def processRAGContent(data):
    await embed(chunk(data))    
    span = trace.get_current_span()
    span.set_attribute("process_rag", 1)
    return {"status": "success", "detail": 1}

async def processFile(reader: str):
    # Extract text from every page of the PDF
    extracted_text = ""
    for page in reader.pages:
        text = page.extract_text()
        if text:
            extracted_text += text + "\n"
            
    return {"text": extracted_text.strip()}

async def get_application(id: int):
    data = getApp(id)
    return data

async def get_decision(id: int):
    data = getDec(id)
    return data

async def get_decision_for_application(application_id: int):
    return getDecisionForApplication(application_id)

async def is_loan_accepted(id: int) -> bool:
    return isLoanAccepted(id)


# Bump when the rule thresholds or logic change, stored with each rule result
RULES_VERSION = "v1"


def mockBureauData(pan: str) -> dict:
    """Deterministic mock bureau lookup, hashed from the PAN."""
    digest = hashlib.sha256(pan.encode()).hexdigest()
    credit_score = 300 + (int(digest[:8], 16) % 601)  # maps into [300, 900]
    return {"credit_score": credit_score, "default_count": 0, "payment_flags": []}


def evaluateApplication(data: loanApplicationClass, bureau: dict) -> dict:
    span = trace.get_current_span()
    """Rules engine, records every rule checked whether it passed or failed."""
    total_emi = sum(liability.emi for liability in data.liabilities)
    income = data.loan_request.declared_monthly_income
    debt_to_income = (total_emi / income) if income else 1.0
    credit_score = bureau["credit_score"]

    def rule(name: str, passed: bool, details: str) -> dict:
        return {"rule_name": name, "passed": passed, "details": details, "rule_version": RULES_VERSION}

    rules = [
        rule("dti_below_40", debt_to_income < 0.40, f"debt_to_income={debt_to_income:.2f}"),
        rule("credit_score_650_plus", credit_score >= 650, f"credit_score={credit_score}"),
        rule("dti_below_55", debt_to_income < 0.55, f"debt_to_income={debt_to_income:.2f}"),
        rule("credit_score_600_plus", credit_score >= 600, f"credit_score={credit_score}"),
    ]

    if debt_to_income < 0.40 and credit_score >= 650:
        verdict, confidence = "APPROVED", 95
    elif debt_to_income < 0.55 and credit_score >= 600:
        verdict, confidence = "CONDITIONAL", 70
    else:
        verdict, confidence = "DENIED", 85
    all_result = {"verdict": verdict, "confidence": confidence, "rules": rules}
    span.set_attribute("evaluate_decision", all_result)
    
    return all_result 


async def receiveLoanApplication(data: loanApplicationClass) -> dict:
    if data.loan_request.declared_monthly_income <= 90000:
        return {"error": "income too low"}

    # Build the ORM object from the validated data
    application = Application(
        applicant_name=data.applicant.name,
        phone=data.applicant.phone,
        email=data.applicant.email,
        pan=data.applicant.pan,
        idempotency_key=data.idempotency_key,
    )

    # Assign via relationships so application_id is filled in on save
    application.loan_request = LoanRequest(
        amount=Decimal(str(data.loan_request.amount)),
        purpose=data.loan_request.purpose,
        tenure_months=data.loan_request.tenure_months,
        declared_monthly_income=Decimal(str(data.loan_request.declared_monthly_income)),
    )
    application.employment = Employment(
        employer=data.employment.employer,
        years_at_company=Decimal(str(data.employment.years_at_company)),
        employment_type=data.employment.employment_type,
    )
    application.liabilities = [
        Liability(
            type=liability.type,
            outstanding=Decimal(str(liability.outstanding)),
            emi=Decimal(str(liability.emi)),
        )
        for liability in data.liabilities
    ]

    # Verdict is computed server-side from the declared data and bureau lookup
    bureau = mockBureauData(data.applicant.pan)
    evaluation = evaluateApplication(data, bureau)
    application.decision = Decision(
        verdict=evaluation["verdict"],
        confidence=Decimal(str(evaluation["confidence"])),
        rules_json=evaluation["rules"],
        decision_timestamp=datetime.now(UTC),
    )

    
    def build_events(application_id: int) -> list[OutboxEvents]:
        payload = {
            "application_id": application_id,
            "applicant_name": data.applicant.name,
            "loan_amount": data.loan_request.amount,
            "loan_purpose": data.loan_request.purpose,
            "verdict": evaluation["verdict"],
        }
        return [
            OutboxEvents(aggregate_id=application_id, event_type="applications_submitted", payload=payload),
            OutboxEvents(aggregate_id=application_id, event_type="applications_decision_made", payload=payload),
        ]

    # One transaction: application + decision + both outbox events commit together
    application_id = save_application_with_events(application, build_events)

    # PII-free summary for RAG
    liability_lines = "; ".join(
        f"{l.type} outstanding={l.outstanding} emi={l.emi}" for l in data.liabilities
    )
    summary = "\n".join(
        [
            "Loan application",
            f"Purpose: {data.loan_request.purpose}",
            f"Amount: {data.loan_request.amount}",
            f"Tenure: {data.loan_request.tenure_months} months",
            f"Employment type: {data.employment.employment_type}",
            f"Declared monthly income: {data.loan_request.declared_monthly_income}",
            f"Liabilities: {liability_lines}",
        ]
    )
    await processRAGContent(summary)

    # mode="json" so the record can be dumped into Redis
    record = {"id": application_id, **data.model_dump(mode="json")}
    span = trace.get_current_span()
    span.set_attribute("application_id", application_id)
    return record


async def processLoanApplicationExtraction(
    content: str, attempts: int = 2
) -> ExtractedLoanApplication:
    """Extract loan application fields with the LLM, raising if all attempts fail."""
    for n in range(attempts):
        response = await client.responses.parse(
            model="gpt-4o",
            input=[
                {
                    "role": "system",
                    "content": (
                        "Extract the applicant, loan request, employment, and "
                        "liabilities fields from this loan application document."
                    ),
                },
                {"role": "user", "content": content},
            ],
            text_format=ExtractedLoanApplication,
        )
        if response.output_parsed is not None:
            return response.output_parsed
    raise ValueError("Could not extract loan application fields from the document.")


def _find_field(text: str, label: str) -> str:
    match = re.search(rf"{label}\s*:\s*(.+)", text, re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _to_number(raw: str) -> float:
    match = re.search(r"[\d.]+", raw.replace(",", ""))
    return float(match.group(0)) if match else 0.0


def parseLoanApplicationText(text: str) -> ExtractedLoanApplication:
    """Parse the document with regex, missing fields are left for Pydantic to reject."""
    employment_type_raw = _find_field(text, "Declared Employment Type").lower()
    if "self" in employment_type_raw:
        employment_type = "self_employed"
    elif "salaried" in employment_type_raw:
        employment_type = "salaried"
    else:
        employment_type = "unemployed"

    tenure_match = re.search(r"Requested Tenure\s*:\s*(\d+)", text, re.IGNORECASE)
    years_match = re.search(r"Years at Current Employer\s*:\s*([\d.]+)", text, re.IGNORECASE)

    liabilities = []
    for line in text.splitlines():
        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) >= 4 and parts[0] not in ("Lender", "") and not parts[0].startswith(("---", "===")):
            status = parts[4] if len(parts) > 4 else ""
            if "closed" in status.lower():
                continue  # a paid-off liability isn't a current one
            liabilities.append(
                PydanticLiability(type=parts[1], outstanding=_to_number(parts[2]), emi=_to_number(parts[3]))
            )

    return ExtractedLoanApplication(
        applicant=PydanticApplicant(
            name=_find_field(text, "Applicant Name"),
            phone=_find_field(text, "Phone"),
            email=_find_field(text, "Email"),
            pan=_find_field(text, "PAN"),
        ),
        loan_request=PydanticLoanRequest(
            amount=_to_number(_find_field(text, "Loan Amount Requested")),
            purpose=_find_field(text, "Loan Purpose"),
            tenure_months=int(tenure_match.group(1)) if tenure_match else 0,
            declared_monthly_income=_to_number(_find_field(text, "Declared Monthly Income")),
        ),
        employment=PydanticEmployment(
            employer=_find_field(text, "Employer Name"),
            years_at_company=float(years_match.group(1)) if years_match else 0.0,
            employment_type=employment_type,
        ),
        liabilities=liabilities,
    )