"""Validate AI-extracted invoice JSON using schema and business rules."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

TOLERANCE = Decimal("0.01")


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def decimal_value(value: Any) -> Decimal | None:
    """Return a Decimal for real JSON numbers, excluding booleans."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def issue(record_index: int, invoice_id: str, severity: str, rule: str, path: str, message: str) -> dict[str, Any]:
    return {
        "record_index": record_index,
        "invoice_id": invoice_id,
        "status": "FLAGGED",
        "severity": severity,
        "rule": rule,
        "path": path,
        "message": message,
    }


def validate_batch(invoices: Any, schema: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate a batch and return one or more report rows per record."""
    if not isinstance(invoices, list):
        raise ValueError("Input JSON must be an array of invoice objects.")

    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    report: list[dict[str, Any]] = []
    seen_ids: dict[str, int] = {}

    for record_index, invoice in enumerate(invoices, start=1):
        invoice_id = invoice.get("invoice_id", "UNKNOWN") if isinstance(invoice, dict) else "UNKNOWN"
        invoice_id = str(invoice_id) if invoice_id is not None else "UNKNOWN"
        record_issues: list[dict[str, Any]] = []

        if not isinstance(invoice, dict):
            record_issues.append(
                issue(record_index, invoice_id, "CRITICAL", "schema", "$", "Invoice record must be a JSON object.")
            )
        else:
            schema_errors = sorted(
                validator.iter_errors(invoice),
                key=lambda error: list(error.absolute_path),
            )
            for error in schema_errors:
                path = "$" + "".join(
                    f"[{part}]" if isinstance(part, int) else f".{part}"
                    for part in error.absolute_path
                )
                record_issues.append(
                    issue(record_index, invoice_id, "ERROR", "schema", path, error.message)
                )

            if invoice_id != "UNKNOWN" and invoice_id.strip():
                if invoice_id in seen_ids:
                    record_issues.append(
                        issue(
                            record_index,
                            invoice_id,
                            "ERROR",
                            "duplicate_invoice_id",
                            "$.invoice_id",
                            f"Duplicate invoice_id; first seen at record {seen_ids[invoice_id]}.",
                        )
                    )
                else:
                    seen_ids[invoice_id] = record_index

            line_items = invoice.get("line_items")
            calculated_invoice_total = Decimal("0")
            can_reconcile = isinstance(line_items, list) and len(line_items) > 0

            if isinstance(line_items, list):
                for item_index, item in enumerate(line_items):
                    if not isinstance(item, dict):
                        can_reconcile = False
                        continue

                    quantity = decimal_value(item.get("quantity"))
                    unit_price = decimal_value(item.get("unit_price"))
                    line_total = decimal_value(item.get("line_total"))
                    if None in (quantity, unit_price, line_total):
                        can_reconcile = False
                        continue

                    expected = quantity * unit_price
                    if abs(line_total - expected) > TOLERANCE:
                        record_issues.append(
                            issue(
                                record_index,
                                invoice_id,
                                "ERROR",
                                "line_total_math",
                                f"$.line_items[{item_index}].line_total",
                                f"Expected {expected:.2f} from quantity × unit_price, got {line_total:.2f}.",
                            )
                        )
                    calculated_invoice_total += line_total

            invoice_total = decimal_value(invoice.get("invoice_total"))
            if invoice_total is None:
                can_reconcile = False

            if (
                can_reconcile
                and invoice_total is not None
                and abs(invoice_total - calculated_invoice_total) > TOLERANCE
            ):
                record_issues.append(
                    issue(
                        record_index,
                        invoice_id,
                        "CRITICAL",
                        "invoice_reconciliation",
                        "$.invoice_total",
                        f"Expected {calculated_invoice_total:.2f} from line-item totals, got {invoice_total:.2f}.",
                    )
                )

        if record_issues:
            report.extend(record_issues)
        else:
            report.append(
                {
                    "record_index": record_index,
                    "invoice_id": invoice_id,
                    "status": "VALID",
                    "severity": "INFO",
                    "rule": "passed_all_checks",
                    "path": "$",
                    "message": "Passed schema and business-rule validation.",
                }
            )

    return report


def summarize(report: list[dict[str, Any]], total_records: int) -> dict[str, Any]:
    """Create batch-level QA metrics using unique record counts."""
    flagged_records = {
        row["record_index"] for row in report if row["status"] == "FLAGGED"
    }
    valid_records = total_records - len(flagged_records)
    issues = [row for row in report if row["status"] == "FLAGGED"]

    return {
        "total_records": total_records,
        "valid_records": valid_records,
        "flagged_records": len(flagged_records),
        "pass_rate_pct": round((valid_records / total_records * 100), 2)
        if total_records
        else 0.0,
        "total_issues": len(issues),
        "severity_counts": dict(Counter(row["severity"] for row in issues)),
        "rule_counts": dict(Counter(row["rule"] for row in issues)),
    }


def save_csv(report: list[dict[str, Any]], path: str | Path) -> None:
    fieldnames = [
        "record_index",
        "invoice_id",
        "status",
        "severity",
        "rule",
        "path",
        "message",
    ]
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(report)


def save_json(data: dict[str, Any], path: str | Path) -> None:
    with Path(path).open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate AI-extracted invoice JSON."
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="ai_extracted_data.json",
        help="Input JSON array",
    )
    parser.add_argument(
        "--schema",
        default="invoice_schema.json",
        help="JSON Schema file",
    )
    parser.add_argument(
        "--report",
        default="validation_report.csv",
        help="CSV validation report",
    )
    parser.add_argument(
        "--summary",
        default="validation_summary.json",
        help="JSON batch summary",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        invoices = load_json(args.input)
        schema = load_json(args.schema)
        report = validate_batch(invoices, schema)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Validation failed: {exc}")
        return 1

    save_csv(report, args.report)
    summary = summarize(report, len(invoices))
    save_json(summary, args.summary)

    print(
        f"Records: {summary['total_records']} | "
        f"Valid: {summary['valid_records']} | "
        f"Flagged: {summary['flagged_records']} | "
        f"Pass rate: {summary['pass_rate_pct']}% | "
        f"Issues: {summary['total_issues']}"
    )
    print(f"CSV report: {args.report}")
    print(f"JSON summary: {args.summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
