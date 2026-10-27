"""
Eval harness for the LLM-generated decision explanation — not a pytest test,
run manually:

    python evals/explain_eval.py

This costs real OpenAI calls (one embedding call per new golden case, one
explanation call per case, every run) — deliberately kept separate from the
pytest suite, which never hits the real API.

Golden cases are built from sample-documents/, one per verdict (APPROVED,
CONDITIONAL, DENIED). Each case's idempotency key is deterministic (same
hash the real upload endpoint uses), so re-running this script reuses the
existing application instead of creating duplicates or crashing on the
unique constraint.

Scoring is rule-based, not an LLM judge: does the explanation mention the
correct verdict, and does it avoid claiming a different one. This is a
narrow, cheap check — it doesn't verify the explanation's prose is good,
only that it isn't contradicting the actual decision.
"""

import asyncio
import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from arbiter.constant.constant import loanApplicationClass
from arbiter.db import SessionLocal
from arbiter.models import Application
from arbiter.services.processdata import (
    parseLoanApplicationText,
    receiveLoanApplication,
    retrieveForDecisionFunc,
)

SAMPLES = Path(__file__).resolve().parent.parent / "sample-documents"
RESULTS_DIR = Path(__file__).resolve().parent / "results"

GOLDEN_CASES = [
    {"file": "7_loan_application_approved.txt", "expected_verdict": "APPROVED"},
    {"file": "8_loan_application_conditional.txt", "expected_verdict": "CONDITIONAL"},
    {"file": "6_loan_application_valid.txt", "expected_verdict": "DENIED"},
]

VERDICT_WORDS = {
    "APPROVED": ["approved", "approval"],
    "CONDITIONAL": ["conditional", "condition"],
    "DENIED": ["denied", "denial", "rejected", "rejection"],
}


def _existing_application_id(idempotency_key: uuid.UUID) -> int | None:
    with SessionLocal() as session:
        app = session.query(Application).filter_by(idempotency_key=idempotency_key).first()
        return app.id if app else None


async def _ensure_application(file_name: str) -> tuple[int, str]:
    raw_bytes = (SAMPLES / file_name).read_bytes()
    # same computation the real upload endpoint uses, so re-running this
    # script (or uploading the same file for real) reuses the same row
    idempotency_key = uuid.uuid5(uuid.NAMESPACE_OID, raw_bytes.hex())

    existing_id = _existing_application_id(idempotency_key)
    if existing_id is not None:
        return existing_id, "reused"

    parsed = parseLoanApplicationText(raw_bytes.decode("utf-8"))
    data = loanApplicationClass(
        applicant=parsed.applicant,
        loan_request=parsed.loan_request,
        employment=parsed.employment,
        liabilities=parsed.liabilities,
        idempotency_key=idempotency_key,
    )
    record = await receiveLoanApplication(data)
    return record["id"], "created"


def _score_explanation(explanation: str, expected_verdict: str) -> dict:
    text = explanation.lower()
    mentions_expected = any(w in text for w in VERDICT_WORDS[expected_verdict])
    other_verdicts = [v for v in VERDICT_WORDS if v != expected_verdict]
    mentions_wrong_verdict = any(w in text for v in other_verdicts for w in VERDICT_WORDS[v])

    return {
        "mentions_expected_verdict": mentions_expected,
        "mentions_wrong_verdict": mentions_wrong_verdict,
        "says_inconclusive": "inconclusive" in text,
        "passed": mentions_expected and not mentions_wrong_verdict,
    }


async def run() -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    results = []

    for case in GOLDEN_CASES:
        application_id, status = await _ensure_application(case["file"])
        outcome = await retrieveForDecisionFunc(application_id, k=3)

        if outcome is None:
            results.append(
                {**case, "application_id": application_id, "application_status": status,
                 "error": "no decision context found", "passed": False}
            )
            continue

        score = _score_explanation(outcome["explanation"], case["expected_verdict"])
        results.append(
            {
                "file": case["file"],
                "application_id": application_id,
                "application_status": status,
                "expected_verdict": case["expected_verdict"],
                "explanation": outcome["explanation"],
                **score,
            }
        )

    passed = sum(1 for r in results if r.get("passed"))
    summary = {
        "run_at": datetime.now(UTC).isoformat(),
        "total": len(results),
        "passed": passed,
        "cases": results,
    }

    out_file = RESULTS_DIR / f"baseline_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    out_file.write_text(json.dumps(summary, indent=2))

    print(f"{passed}/{len(results)} passed — results written to {out_file}")
    for r in results:
        mark = "PASS" if r.get("passed") else "FAIL"
        print(f"  [{mark}] {r['file']} (expected {r['expected_verdict']}, application {r.get('application_status')})")


if __name__ == "__main__":
    asyncio.run(run())
