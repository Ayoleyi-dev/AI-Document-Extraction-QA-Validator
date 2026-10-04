import json
from pathlib import Path

import pytest

from validator import summarize, validate_batch

SCHEMA = json.loads(Path("invoice_schema.json").read_text(encoding="utf-8"))


def valid_invoice(invoice_id="INV-001"):
    return {
        "invoice_id": invoice_id,
        "date": "2025-10-15",
        "client_name": "Acme Corp",
        "line_items": [
            {
                "item": "Consulting",
                "quantity": 2,
                "unit_price": 150.0,
                "line_total": 300.0,
            }
        ],
        "invoice_total": 300.0,
    }


def test_valid_invoice_passes():
    report = validate_batch([valid_invoice()], SCHEMA)
    assert len(report) == 1
    assert report[0]["status"] == "VALID"


def test_line_math_mismatch_is_flagged():
    invoice = valid_invoice()
    invoice["line_items"][0]["line_total"] = 250.0
    report = validate_batch([invoice], SCHEMA)
    rules = {row["rule"] for row in report}
    assert "line_total_math" in rules
    assert "invoice_reconciliation" in rules


def test_invalid_invoice_total_type_is_schema_error():
    invoice = valid_invoice()
    invoice["invoice_total"] = "300.00"
    report = validate_batch([invoice], SCHEMA)
    assert any(
        row["rule"] == "schema" and row["path"] == "$.invoice_total"
        for row in report
    )


def test_boolean_is_not_accepted_as_quantity():
    invoice = valid_invoice()
    invoice["line_items"][0]["quantity"] = True
    report = validate_batch([invoice], SCHEMA)
    assert any(row["rule"] == "schema" for row in report)


def test_duplicate_invoice_id_is_flagged():
    report = validate_batch(
        [valid_invoice("INV-1"), valid_invoice("INV-1")],
        SCHEMA,
    )
    assert any(row["rule"] == "duplicate_invoice_id" for row in report)


def test_summary_counts_records_not_issue_rows():
    invoice = valid_invoice()
    invoice["client_name"] = ""
    invoice["line_items"][0]["line_total"] = 250.0

    report = validate_batch([invoice, valid_invoice("INV-2")], SCHEMA)
    summary = summarize(report, 2)

    assert summary["flagged_records"] == 1
    assert summary["valid_records"] == 1
    assert summary["total_issues"] > 1


def test_input_must_be_array():
    with pytest.raises(ValueError):
        validate_batch({"invoice_id": "INV-1"}, SCHEMA)
