# Sample documents

Stand-ins for scanned/uploaded loan-application documents (mostly
plain-text, one real PDF), each built around a different extraction
problem. No code or extraction design here — just source material for
you to write extraction logic against.

1. **`1_payslip_clean.txt`** — clean, well-labeled baseline. Everything a
   good extractor should get right with no ambiguity.

2. **`2_bank_statement_ocr_noisy.txt`** — simulates OCR output: `0`/`O`
   and `1`/`l`/`I` confusion, a line that wraps mid-transaction, one
   amount marked `[illegible]`, and a closing balance you can cross-check
   arithmetically against the running balance.

3. **`3_id_document_incomplete.txt`** — missing/truncated fields (PAN cut
   off, father's name not legible), and two attached ID documents whose
   names don't quite match (`ANITA ________` vs `Anita Rajeshwari D.`).
   Tests what your pipeline does when it can't confidently extract a
   field, or when two sources of "truth" disagree.

4. **`4_loan_application_multi_section.txt`** — a 3-page scan where page 3
   is, by mistake, an excerpt of the *lender's internal* credit policy
   rather than an applicant document. Also contains applicant-asserted
   claims (a "closed" loan) that shouldn't be trusted without
   verification against bureau data. Tests document-boundary handling,
   what your pipeline does with data that was never meant to be in an
   applicant's file, and the difference between "applicant says" and
   "verified."

5. **`5_payslip_real_pdf.pdf`** — the only file here that's an actual PDF,
   not a plain-text stand-in. Same clean, well-labeled payslip shape as
   file 1, but this one exercises your real PDF-text-extraction step
   (Day 11–12) itself, before any OCR noise or LLM parsing is involved.

6. **`6_loan_application_valid.txt`** — complete, well-labeled loan
   application: unlike file 4, this one includes phone/email/PAN, so
   `POST /route/loan_application` can actually extract, save, and embed
   it end to end instead of being rejected for missing applicant fields.
   One liability is excluded on purpose (closed, same rule as file 4).
   Its PAN's mocked credit score lands on **DENIED** (confidence 85) —
   low debt-to-income, but a poor mocked bureau score.

7. **`7_loan_application_approved.txt`** — same complete shape as file 6,
   but income/liabilities/PAN are tuned so the rules engine lands on
   **APPROVED** (confidence 95): debt-to-income 0.25 and a mocked credit
   score of 733.

8. **`8_loan_application_conditional.txt`** — tuned to land on
   **CONDITIONAL** (confidence 70): debt-to-income 0.45 (the 40-55% band)
   and a mocked credit score of 612 (600-649) — not good enough for
   `APPROVED`, not bad enough for `DENIED`.

None of these are real people or real financial data — all names,
numbers, and account details are invented for testing.
