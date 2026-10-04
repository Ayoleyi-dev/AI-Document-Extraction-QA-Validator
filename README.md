# AI Document Extraction QA Validator

I originally built this project as a small Python script for checking invoice data extracted by an AI system.

When I revisited it, I expanded it into a more complete data-quality workflow. The validator now checks both the **structure of the extracted JSON** and the **business logic inside each invoice**, then produces record-level QA results and batch-level quality metrics.

## What it validates

The pipeline checks:

- required invoice fields;
- field data types;
- ISO date format;
- empty strings;
- positive quantities;
- non-negative prices and totals;
- line-item math: `quantity × unit_price = line_total`;
- invoice reconciliation: sum of line items = invoice total;
- duplicate invoice IDs.

The structural rules are defined in a real **JSON Schema** file instead of being hard-coded entirely inside the Python script.

## Why I rebuilt it

The first version could detect several useful errors, but there were a few weaknesses.

For example, it counted every flagged issue as if it were a separate failed invoice. An invoice with three problems could therefore inflate the flagged count.

The updated version separates:

- **records processed**;
- **valid records**;
- **flagged records**;
- **total issues**.

It also handles invalid invoice-total types, rejects booleans as numeric values, and uses `Decimal` for money comparisons rather than relying only on floating-point arithmetic.

## Sample result

Using the included four-invoice sample:

| Metric | Result |
|---|---:|
| Records processed | 4 |
| Valid invoices | 2 |
| Flagged invoices | 2 |
| Pass rate | 50% |
| Total issues found | 5 |

The sample contains intentionally bad records so the validation rules can be demonstrated.

## Severity levels

Issues are classified by severity:

- **INFO** — record passed all checks;
- **ERROR** — schema, duplicate-ID, or line-item validation problem;
- **CRITICAL** — invoice-level reconciliation failure.

## Outputs

Running the validator creates:

### `validation_report.csv`

A detailed row-level QA report containing:

- record number;
- invoice ID;
- status;
- severity;
- validation rule;
- JSON field path;
- human-readable error message.

### `validation_summary.json`

A batch summary containing:

- total records;
- valid records;
- flagged records;
- pass rate;
- issue count;
- issue counts by severity;
- issue counts by validation rule.

## Project files

```text
validator.py
invoice_schema.json
ai_extracted_data.json
requirements.txt
tests/
  test_validator.py
```

## Run it

Install the dependencies:

```bash
pip install -r requirements.txt
```

Run the validator on the included sample:

```bash
python validator.py
```

Or provide another extracted invoice file:

```bash
python validator.py invoices.json
```

Custom output paths can also be supplied:

```bash
python validator.py invoices.json \
  --report outputs/issues.csv \
  --summary outputs/summary.json
```

Run the automated tests:

```bash
python -m pytest -q
```

The current test suite covers valid records, math mismatches, invalid data types, booleans incorrectly used as numbers, duplicate invoice IDs, batch summary counting, and invalid input structure.

## What this project shows

The main point of the project is not AI model training. It focuses on the **quality-control step after extraction**.

An extraction system can return syntactically valid JSON and still produce unusable business data. This project separates schema checks from reconciliation rules so those errors can be found before the data is accepted into a downstream workflow.

## Possible extensions

A larger version could add batch folder processing, configurable rule sets for different document types, or a review dashboard for QA teams.
