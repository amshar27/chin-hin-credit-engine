"""
bank_statement_analyst_agent.py
--------------------------------
Extracts and analyses a bank statement PDF using pdfplumber for text
extraction and the Bank Statement Analyst Foundry agent for interpretation.
"""

import io
import logging
import os

import pdfplumber

from app.agents.foundry_client import call_agent

logger = logging.getLogger(__name__)

_INSTRUCTIONS = (
    "Analyze this bank statement text. Extract financial behavior. "
    "Output STRICT JSON exactly matching these keys: "
    "{'average_balance': 0.0, 'total_deposits': 0.0, "
    "'total_withdrawals': 0.0, 'bounced_checks': 0, 'summary': 'String'}."
)


def analyze_bank_statement(pdf_bytes: bytes) -> dict:
    """
    Extract text from a bank statement PDF and call the Foundry analyst agent.

    Args:
        pdf_bytes: Raw bytes of the uploaded bank statement PDF.

    Returns:
        Dict with keys: average_balance, total_deposits, total_withdrawals,
        bounced_checks, summary.

    Raises:
        ValueError:   If the PDF contains no extractable text or the agent
                      returns malformed JSON.
        RuntimeError: If the agent call fails.
    """
    # Extract all text from the PDF
    pages: list[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    raw_text = "\n".join(pages).strip()

    if not raw_text:
        raise ValueError("Bank statement PDF contains no extractable text.")

    logger.info("Bank statement text extracted — %d chars", len(raw_text))

    payload = f"{_INSTRUCTIONS}\n\n{raw_text}"

    agent_id = os.environ.get("BANK_AGENT_ID")
    logger.info("Calling Bank Statement Analyst agent (agent_id=%s) …", agent_id)

    result = call_agent(agent_id, payload, expect_json=True)
    logger.info(
        "Bank Statement analysis received — bounced_checks=%s avg_balance=%s",
        result.get("bounced_checks", "?"),
        result.get("average_balance", "?"),
    )
    return result
