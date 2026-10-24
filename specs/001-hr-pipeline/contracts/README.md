# Data Contracts — `data/` (12 files + dictionary)

These contracts are the interface between immutable raw files and `raw.*` tables.
Every loader validates against them; violations fail the build (they mean the dataset changed
under us, which must not happen silently).

**Shared conventions**

- All raw columns land in `raw.*` **as TEXT**, exactly as delivered (Principle II).
- Expected `rows` must match exactly → Gate R (`ingestion/counts.py`).
- `_source_file` = filename, `_loaded_at` = load timestamp, `_row_hash` = sha256 over
  `'|'.join(field values in column order)` — metadata columns excluded from the hash.
- Date/timestamp formats observed are mixed on purpose; normalization happens in `staging`, never
  in `raw`.
- Rules = `data/data_dictionary.md` numbered business rules.

| # | File | Rows | Contract |
|---|---|---|---|
| 1 | employees.csv | 1,316 | [employees.contract.md](employees.contract.md) |
| 2 | employment_history.csv | 3,686 | [employment_history.contract.md](employment_history.contract.md) |
| 3 | departments.csv | 25 | [departments.contract.md](departments.contract.md) |
| 4 | shifts.json | 4 | [shifts.contract.md](shifts.contract.md) |
| 5 | shift_roster.csv | 36,402 | [shift_roster.contract.md](shift_roster.contract.md) |
| 6 | device_mapping.csv | 1,260 | [device_mapping.contract.md](device_mapping.contract.md) |
| 7 | biometric_punches.csv | 345,280 | [biometric_punches.contract.md](biometric_punches.contract.md) |
| 8 | holidays.csv | 12 | [holidays.contract.md](holidays.contract.md) |
| 9 | leave_requests.json | 5,372 | [leave_requests.contract.md](leave_requests.contract.md) |
| 10 | overtime_requests.csv | 22,098 | [overtime_requests.contract.md](overtime_requests.contract.md) |
| 11 | payroll_lines.csv | 53,617 | [payroll_lines.contract.md](payroll_lines.contract.md) |
| 12 | applications.csv | 3,835 | [applications.contract.md](applications.contract.md) |

**Note on counts**: listed counts are the case study's delivery numbers. If a local recount
disagrees, log it in `docs/profile_notes.md` and ask a mentor (never edit the file).
