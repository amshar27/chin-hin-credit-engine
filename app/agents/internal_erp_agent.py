"""
internal_erp_agent.py
---------------------
Looks up a company's internal trade / credit record from the mock ERP dataset.

Matching logic (either condition triggers a hit):
  1. company_name matches case-insensitively.
  2. reg_no contains the entry's reg_no_keywords substring.

Returns the entry's `internal_data` dict on a hit, or a "New Customer" default.
"""

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Path is relative to the project root (where uvicorn is launched from).
_ERP_DATA_PATH = os.path.join("data", "mock_erp", "mock_erp_data.json")

_NEW_CUSTOMER_DEFAULT: dict[str, Any] = {
    "status": "New Customer",
    "payment_conduct": "New/Clean",
    "existing_group_exposure": 0.00,
    "relationship_years": 0,
}


def _load_erp_records() -> list[dict[str, Any]]:
    """Load and return the ERP JSON array from disk."""
    with open(_ERP_DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def query_internal_erp(company_name: str | None, reg_no: str) -> dict[str, Any]:
    """
    Search the internal ERP dataset for a matching company record.

    Matching is attempted in this order:
      1. company_name equality (case-insensitive, stripped).
      2. reg_no contains the entry's reg_no_keywords as a substring.

    Args:
        company_name: Company name to search. Pass None or empty string if unknown.
        reg_no:       Company registration number supplied by the user.

    Returns:
        The matched entry's `internal_data` dict, or a "New Customer" default
        dict if no match is found.
    """
    try:
        records = _load_erp_records()
    except FileNotFoundError:
        logger.error("ERP data file not found at: %s", _ERP_DATA_PATH)
        return _NEW_CUSTOMER_DEFAULT.copy()
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse ERP data file: %s", exc)
        return _NEW_CUSTOMER_DEFAULT.copy()

    name_normalised = (company_name or "").strip().upper()
    reg_no_normalised = reg_no.strip()

    for entry in records:
        entry_name: str = entry.get("company_name", "").strip().upper()
        entry_keyword: str = entry.get("reg_no_keywords", "").strip()

        name_match = bool(name_normalised) and (name_normalised == entry_name)
        reg_match = bool(entry_keyword) and (entry_keyword in reg_no_normalised)

        if name_match or reg_match:
            logger.info(
                "ERP match found for company_name=%r reg_no=%r → entry=%r",
                company_name,
                reg_no,
                entry.get("company_name"),
            )
            return entry["internal_data"]

    logger.info(
        "No ERP match for company_name=%r reg_no=%r — returning New Customer default.",
        company_name,
        reg_no,
    )
    return _NEW_CUSTOMER_DEFAULT.copy()
