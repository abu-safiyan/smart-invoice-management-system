# Smart Invoice Processing & Financial Document Automation System

**TEYZIX CORE Internship — Task PY-3**

A production-style Python system that automatically extracts, validates, stores,
and reports on vendor invoices from PDF documents, built with a Streamlit
dashboard on top of a MySQL backend.

---

## Features

- **PDF Invoice Upload & Extraction** — upload one or more PDF invoices; the
  system extracts invoice number, vendor, customer, dates, tax, total,
  currency, and payment status using regex-based parsing that handles
  multiple real-world invoice layouts and label conventions.
- **Validation** — normalizes inconsistent date formats, flags missing or
  invalid fields, detects duplicate invoice numbers, catches merged/malformed
  vendor addresses, and checks that extracted names look plausible.
- **Normalized Database** — vendors and invoices are stored in separate,
  related MySQL tables (not duplicated per-invoice), so two vendors with the
  same name are never confused with each other.
- **Search & Filter** — search by invoice number or vendor name (with
  disambiguation when multiple vendors share a name), and filter by date
  range (invoice date, due date, or processed date), payment status, or
  amount range.
- **Reports** — Daily Invoice Report, Monthly Invoice Summary, Vendor-Wise
  Report, Tax Summary (broken down by currency and vendor), and Outstanding
  Payments Report with urgency indicators.
- **Manage Invoices** — search, edit, or delete any stored invoice; edits are
  diffed so only changed fields are written to the database. Includes a
  manual override for validation status/errors after human review.
- **Dashboard** — live totals for invoices, vendors, invoice amount, pending
  payments, and validation errors, plus a recently-processed invoices table.
- **Data Export** — every report and search result can be downloaded as
  Excel (.xlsx) or CSV.
- **Activity Logging** — uploads, processing outcomes, validation issues,
  updates, deletions, and export requests are logged to `logs/system_logs.log`.
- **Error Handling** — corrupted PDFs, fake/renamed files, missing database
  connections, and duplicate records are all caught and reported cleanly
  rather than crashing the app.

---

## Tech Stack

| Purpose | Library |
|---|---|
| Language | Python 3.10+ |
| Web UI | Streamlit |
| PDF text extraction | pdfplumber |
| Database | MySQL (via mysql-connector-python) |
| Data handling | pandas |
| Excel export | openpyxl |
| Configuration | python-dotenv |

---

## Project Structure

```
Task-3/
├── app.py                      # Streamlit app - all pages
├── core/
│   ├── __init__.py             # package imports
│   ├── models.py               # Invoice, Vendor data classes
│   ├── extractor.py            # PDF text extraction + field parsing
│   ├── validation.py           # validation, normalization, duplicate checks
│   ├── database.py             # connection, CRUD, search, filter, dashboard stats
│   ├── reports.py              # daily/monthly/vendor/tax/outstanding reports
│   ├── exporter.py             # Excel/CSV export helpers
│   └── logger.py               # activity logging setup
├── logs/
│   └── system_logs.log         # generated at runtime
├── sample_invoices/            # sample PDFs for testing
├── .env                        # local DB credentials (not committed)
├── .env.example                # template for .env
├── .gitignore
├── requirements.txt
├── schema.sql                  # database schema
└── README.md
```

---

## Setup Instructions

### 1. Clone and set up a virtual environment

```bash
git clone <your-repo-url>
cd Task-3
python -m venv task3venv
task3venv\Scripts\activate        # Windows
# source task3venv/bin/activate   # macOS/Linux
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Set up MySQL

Make sure a MySQL server is running locally, then run the schema:

```bash
mysql -u root -p < schema.sql
```

This creates the `invoice_management` database with the `vendor` and
`invoice` tables.

### 4. Configure environment variables

Copy `.env.example` to `.env` and fill in your MySQL credentials:

```
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=your_password_here
DB_NAME=invoice_management
```

`.env` is excluded from version control via `.gitignore` — never commit real
credentials.

### 5. Run the app

```bash
streamlit run app.py
```

The dashboard opens at `http://localhost:8501`.

---

## Usage Overview

- **Dashboard** — landing page with key stats and recently processed invoices.
- **Upload Invoices** — drag-and-drop one or more PDF invoices; each is
  extracted, validated, and (if valid) saved automatically. Invalid invoices
  are reported but not saved to the database.
- **Manage Invoices** — look up an invoice by number to edit its fields
  (including vendor name/address — note this updates the vendor record for
  *all* their invoices) or delete it.
- **Search & Filter** — five tabs for locating invoices by number, vendor,
  date range, payment status, or amount range.
- **Reports** — generate and export any of the five report types.

---

## Design Notes & Known Limitations

These are deliberate design decisions, documented for transparency:

- **Date format ambiguity**: some date formats (e.g. `05/06/2026`) are
  genuinely ambiguous between day-first and month-first conventions. The
  extractor tries a prioritized list of formats and takes the first match;
  this can't be resolved with certainty without vendor-specific context.
- **Vendor plausibility checks are heuristic**, not guaranteed-accurate —
  extraction from unlabeled fields (like vendor name, which usually has no
  label at all on the invoice) relies on positional guessing plus sanity
  checks, with low-confidence extractions flagged as "Needs Review" rather
  than silently trusted.
- **Orphaned vendors are kept**, not deleted, when their last invoice is
  removed — this preserves vendor history for future invoices from the same
  vendor, at the cost of the vendor list growing over time.
- **Tax/amount totals are never summed across different currencies** — the
  Tax Summary report breaks totals down per-currency rather than producing a
  single (meaningless) combined number.
- **Export download logging** records when a download was *requested*
  (button clicked), not confirmation that the browser finished saving the
  file, since that isn't observable from server-side code.

---

## Sample Data

Sample invoice PDFs covering multiple real-world layouts (different label
wording, date formats, currencies, and one intentionally corrupted file for
testing error handling) are included in `sample_invoices/`.

---

## Author

Built as part of the TEYZIX CORE Internship Program, June Batch — Task PY-3.
