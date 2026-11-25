# WareWise AI — Smart Warehouse Management & Intelligence

A Python + Streamlit warehouse operations prototype with inventory management, stock movement tracking, natural-language warehouse queries, shelf lookup, demand estimation, replenishment suggestions, purchase-order workflow and reports.

## Features
- Executive inventory overview and stock/expiry alerts
- Warehouse AI assistant for SKU lookup, stock levels, expiry, reorder and forecast questions
- Product management, filtering, CSV import/export
- Stock-in and stock-out transactions with audit ledger
- Warehouse aisle/shelf locator and barcode text lookup
- Moving-average demand forecast and reorder suggestions
- Draft purchase orders and goods receiving
- Reports and CSV/database exports

## Run locally
```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
streamlit run app.py
```
Open http://localhost:8501.

## Deploy on Streamlit Community Cloud
1. Visit https://share.streamlit.io and sign in with GitHub.
2. Select **Create app**.
3. Repository: `Sunita-001/WareWise-AI`
4. Branch: `main`
5. Main file path: `app.py`
6. Deploy, then copy the generated HTTPS URL.

## Data persistence warning
The application uses SQLite on its local filesystem. Streamlit Community Cloud does not guarantee persistence of local files across restarts/redeployments. The app creates demo records if no database exists. Do not use this cloud SQLite deployment for important or real inventory records. For persistent cloud use, migrate to a managed PostgreSQL/Supabase database.

## Limitations
- Assistant is intent/keyword-based, not a generative LLM.
- Forecasting is a simple moving-average baseline.
- Barcode lookup accepts keyboard-wedge scanner input; camera decoding is not implemented.
- No authentication, role-based access, ERP integration or production-grade multi-user controls.

## Stack
Python, Streamlit, SQLite, Pandas, Plotly.
