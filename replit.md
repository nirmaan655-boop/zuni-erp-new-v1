# Zuni Dairy ERP

## Overview
A complete Corporate Dairy ERP built with Python + Streamlit + PostgreSQL.
Designed for deployment to 3 separate dairy farms with full data persistence.

## Stack
- Python 3.11
- Streamlit (UI)
- PostgreSQL (Replit-managed; accessed via `DATABASE_URL`)
- psycopg2-binary (RealDictCursor)
- Pandas, Plotly, XlsxWriter

## Run
The "Start application" workflow runs:
```
streamlit run zuni_erp/app.py --server.port 5000
```

Default logins: admin/admin123, vet/vet123, account/account123.

## UI / Sidebar Navigation
The default flat Streamlit `pages/` auto-navigation is hidden via CSS
(`[data-testid="stSidebarNav"] { display: none }`). Instead, a custom
grouped navigation is rendered by `render_user_sidebar()` in `auth.py`
using `st.page_link()` calls inside collapsible sections (`st.expander`):

- 🐄 Livestock — Animals, RFID, Pens, Weights, Calving, Breeding,
  Vaccinations, Treatments
- 🥛 Operations — Milk, Feed, Inventory
- 💰 Accounts & Sales — Sales/Purchase, Accounting, Animal P&L
- 👥 HR — Employees, Users
- 📈 Reports & Admin — Reports, Admin Edit Log

Each link is filtered through `role_can_access()` so users only see pages
their role permits. The sidebar dark theme + grouped-nav CSS is injected
via `inject_sidebar_css()` (called from both `_login_form()` and
`render_user_sidebar()`) so it applies to the login screen and every
sub-page, not just the dashboard. Section list lives in
`auth.py::NAV_GROUPS`.

## Database

The app uses Replit-managed PostgreSQL. Schema, seeds, and idempotent
column-level migrations are auto-applied on first connection inside an
advisory-locked transaction (`init_db()` in `db.py`).

`db.py` exposes a SQLite-style API (`query`, `execute`, `post_journal`,
`add_stock_move`, `add_milk_move`) backed by a small SQL translator that
converts the legacy SQLite syntax used across the pages into PostgreSQL:
- `?` placeholder → `%s` (with literal `%` properly escaped first)
- `julianday('now')` → `CURRENT_DATE`; `julianday(x)` → `(x)::date`
- `DATE('now','+N days')` → `(CURRENT_DATE + INTERVAL 'N days')`
- `INSERT OR REPLACE INTO milk_records` → `ON CONFLICT (animal_id,
  record_date, shift) DO UPDATE`
- INSERTs auto-receive `RETURNING *` so `execute()` returns the new PK

Page queries were also updated for PostgreSQL strict mode:
- `ROUND(<double>, n)` calls cast to `::numeric`
- `HAVING` clauses use aggregate expressions, not SELECT aliases
- `GROUP BY` includes every non-aggregated SELECT column

## Structure
- `zuni_erp/app.py` — Dashboard (KPIs, charts, financial summary, alerts)
- `zuni_erp/db.py` — PostgreSQL schema + helpers + SQL translator
- `zuni_erp/utils.py` — Shared utilities (Excel export, etc.)
- `zuni_erp/pages/` — Streamlit multipage app:
  1. Livestock (master, status, movements)
  2. RFID (simulated scans, binding)
  3. Milk (3 shifts; daily + animal-wise)
  4. Calving (single/twins; auto-creates calf records, mother linkage)
  5. Pens (master, weights per pen)
  6. Weights (history, latest, growth chart)
  7. Feed (recipes, allocation; auto stock OUT + journal)
  8. Treatments (medical history; auto cost + stock OUT + journal)
  9. Inventory (5 stores, items, stock IN/OUT, balance)
  10. Sales & Purchase (parties; auto journal + stock)
  11. Accounting (Chart of Accounts, journal, expenses, P&L, BS, TB)
  12. Employees (master, salary payments → journal)
  13. Reports (animal history, milk, feed, stock, treatments, ledgers; Excel)
  14. Breeding (AI/services, protocols, costs)
  15. Vaccinations (schedules, due/overdue tracking)
  16. Admin Edit / Delete (admin-only; edit or delete any record across
      17 core tables; all changes captured in `admin_audit_log` with
      before/after JSON snapshots)

## Deployment
- The Streamlit service is registered in
  `artifacts/api-server/.replit-artifact/artifact.toml` as a `[[services]]`
  entry on path `/` port 5000 with the headless production run command.
- Persistence comes from PostgreSQL (not the filesystem), so the app is
  safe under autoscale and survives restarts/redeploys.

## Notes
- All transactions auto-update inventory + accounting where applicable.
- Multi-farm via `farms` table.
- Excel export available across all reports/lists.
- Backup of the original SQLite file is preserved at
  `zuni_erp/zuni_erp.db.backup_before_publish` (was empty of transactional
  data at migration time).
