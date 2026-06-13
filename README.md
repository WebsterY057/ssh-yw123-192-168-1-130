# Alpha CEX x DEX Resonance Research

This repository contains a cleaned-up version of the CLO resonance research workspace. It separates reusable code, reference docs, token mappings, and generated backtest artifacts so the repo can stay small while research outputs remain reproducible.

## Structure

```text
.
├── config/
│   ├── alpha_symbol_map.json
│   └── alpha_usdt_symbol_map_compact.json
├── backend/
│   ├── app.py
│   └── requirements.txt
├── docs/
│   └── research/
│       ├── alpha-dex-onchain-fields.md
│       ├── cex-fields.md
│       └── resonance-factor-framework.md
├── frontend/
│   ├── src/
│   ├── index.html
│   └── vite.config.js
├── scripts/
│   ├── backtest_dashboard_data.py
│   └── build_dashboard_cache.py
├── src/
│   ├── clo_execution_compare/
│   │   ├── __init__.py
│   │   ├── backtest.py
│   │   └── build_signal_layers.py
│   └── short_book_resonance_divergence/
│       ├── __init__.py
│       └── backtest.py
└── outputs/
```

`outputs/` is intentionally ignored by Git. Run products, exported CSVs, summary JSON, and browser payloads should all go there.

## Environment

The tracked Python scripts currently depend on:

- `duckdb`
- `numpy`
- `pandas`

They also expect access to the RustFS / S3-compatible raw data bucket. The scripts read credentials from these environment variables:

- `ALPHA_S3_KEY_ID`
- `ALPHA_S3_SECRET`
- `ALPHA_S3_REGION`
- `ALPHA_S3_ENDPOINT`
- `ALPHA_S3_URL_STYLE`
- `ALPHA_S3_USE_SSL`

`ALPHA_S3_KEY_ID` and `ALPHA_S3_SECRET` are required.

## Usage

Run the execution backtest:

```bash
python3 src/clo_execution_compare/backtest.py \
  --date 2026-06-11 \
  --cex-pair-key clousdt \
  --dex-symbol alpha_429usdt
```

Default output:

```text
outputs/clo_20260611_tick3600ms_execution_compare/
```

Build the browser-friendly JS payload from those outputs:

```bash
python3 src/clo_execution_compare/build_signal_layers.py
```

Default output:

```text
outputs/web/clo_20260611_signal_layers.js
```

Rebuild the dashboard cache used by the FastAPI service:

```bash
python3 scripts/build_dashboard_cache.py
```

Start the local dashboard API:

```bash
uvicorn backend.app:app --reload
```

Start the frontend dashboard:

```bash
cd frontend
npm install
npm run dev
```

## Notes

- The repo keeps source code and research notes only.
- Historical generated folders from the original workspace are still on disk but are ignored by `.gitignore`.
- The `backend/` and `scripts/` folders provide a lightweight dashboard API and cache builder around the research outputs.
- `src/short_book_resonance_divergence/` contains another strategy module that is wired in through the dashboard utilities.
- If you want to add more strategies, prefer creating a new module under `src/` and writing outputs into `outputs/<strategy-name>/`.
