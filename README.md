# Arbiter

Arbiter is an explainable credit decisioning engine. A loan application
comes in with supporting documents; the system extracts structured data
from those documents, pulls (mocked) bureau data, runs a deterministic
decision, explains the outcome in plain language, and routes anything
it isn't confident about to a human reviewer. Every decision is
traceable and auditable.

The LLM in this system never makes the credit decision — it only
extracts data and writes explanations. Deterministic rules decide.
That's the core design choice the rest of the project follows from.
