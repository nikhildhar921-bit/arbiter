from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# How long an idempotency key stays pending before it can be claimed again
IDEMPOTENCY_PENDING_TTL_SECONDS = 30

# How long a submitted result is cached for duplicate submissions
IDEMPOTENCY_SUBMITTED_TTL_SECONDS = 60 * 60 * 24  # 24 hours


class Applicant(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=2, max_length=100)
    phone: str = Field(min_length=10, max_length=15)
    email: EmailStr
    pan: str = Field(min_length=10, max_length=10, description="PAN / ID number")


class LoanRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    amount: float = Field(gt=0)
    purpose: str = Field(min_length=3, max_length=100)
    tenure_months: int = Field(gt=0, le=360)
    declared_monthly_income: float = Field(gt=0)


class Employment(BaseModel):
    model_config = ConfigDict(frozen=True)

    employer: str = Field(min_length=1, max_length=100)
    years_at_company: float = Field(ge=0)
    employment_type: Literal["salaried", "self_employed", "unemployed"]


class Liability(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: str = Field(min_length=1, max_length=50, description="car_loan, credit_card, etc")
    outstanding: float = Field(ge=0)
    emi: float = Field(ge=0)


SAMPLE_LOAN_APPLICATION = {
    "applicant": {
        "name": "Nikhil Dhar",
        "phone": "9876543210",
        "email": "nikhil@example.com",
        "pan": "ABCDE1234F",
    },
    "loan_request": {
        "amount": 50000,
        "purpose": "home renovation",
        "tenure_months": 24,
        "declared_monthly_income": 95000,
    },
    "employment": {
        "employer": "Acme Corp",
        "years_at_company": 3.5,
        "employment_type": "salaried",
    },
    "liabilities": [
        {"type": "credit_card", "outstanding": 2000, "emi": 500},
    ],
    "idempotency_key": "336a049e-e39b-46a3-9834-a8305b711452",
}


class BureauData(BaseModel):
    """Mocked credit bureau data."""

    model_config = ConfigDict(frozen=True)

    credit_score: int = Field(ge=300, le=900)
    default_count: int = Field(ge=0)
    payment_flags: list[str] = Field(default_factory=list)


class Verdict(StrEnum):
    APPROVED = "APPROVED"
    CONDITIONAL = "CONDITIONAL"
    DENIED = "DENIED"


class RuleResult(BaseModel):
    """One rule the engine evaluated and its result."""

    model_config = ConfigDict(frozen=True)

    rule_name: str
    passed: bool
    details: str | None = None


class Decision(BaseModel):
    """The verdict on an Application, written once and never edited."""

    model_config = ConfigDict(frozen=True)

    application_id: int
    verdict: Verdict
    confidence: float = Field(ge=0, le=100)
    rules_applied: list[RuleResult] = Field(default_factory=list)
    decision_timestamp: datetime
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None



class ExtractedLoanApplication(BaseModel):
    """Fields extracted from an uploaded loan application document."""

    model_config = ConfigDict(frozen=True)

    applicant: Applicant
    loan_request: LoanRequest
    employment: Employment
    liabilities: list[Liability] = Field(default_factory=list)


class loanApplicationClass(BaseModel):
    # Immutable once submitted
    model_config = ConfigDict(frozen=True)

    applicant: Applicant
    loan_request: LoanRequest
    employment: Employment
    liabilities: list[Liability] = Field(default_factory=list)
    idempotency_key: UUID

def chunk(data: str) -> list[str]:
    size = 800
    overlap = 100
    step = size - overlap
    return [data[i:i + size] for i in range(0, len(data), step)]
