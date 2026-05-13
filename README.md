# Global Macro Intelligence Dashboard

A learning-oriented dashboard for developing institutional-grade macro thinking. Track real-time market data, analyze cross-asset relationships, identify dominant variables, study historical event impacts, and track how surprise drives repricing.

## Features

- **Asset Monitor** — Real-time prices and interactive candlestick/line charts for US 10Y, 2Y, DXY, Oil, Gold, S&P 500, VIX, BTC
- **Cross-Asset Relationships** — Correlation matrix heatmap, normalized price overlays, correlation shift detection
- **Dominant Variable** — System-calculated factor ranking, manual recording, historical timeline
- **Event Analysis** — Historical macro event impact on cross-asset pricing, event comparison
- **Expectations** — Consensus vs actual tracking, surprise magnitude, asset reaction windows

## Tech Stack

| Layer | Technology |
|-------|-----------|
| UI Framework | Streamlit |
| Financial Charts | streamlit-lightweight-charts (TradingView) |
| Correlation/Overlay Charts | Plotly |
| Market Data | yfinance, FRED API, Twelve Data |
| Database | Supabase (PostgreSQL) |
| Language | Python 3.10+ |

## Quick Start

### 1. Clone and set up virtual environment

```bash
git clone https://github.com/your-username/Global-Macro-Intelligence-Dashboard.git
cd Global-Macro-Intelligence-Dashboard

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure API keys

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Edit `.streamlit/secrets.toml` with your credentials:

```toml
[fred]
api_key = "your_fred_api_key"

[twelve_data]
api_key = "your_twelve_data_api_key"

[supabase]
url = "https://your-project-id.supabase.co"
key = "eyJhbGciOiJIUzI1NiIs..."  # anon public key (JWT, starts with eyJ)
```

**Where to get keys:**

| Service | URL | Notes |
|---------|-----|-------|
| FRED | https://fred.stlouisfed.org/docs/api/api_key.html | Free, instant signup |
| Twelve Data | https://twelvedata.com/account/api-keys | Free tier: 800 req/day |
| Supabase | https://supabase.com/dashboard | Free tier: 500MB storage |

**Supabase key:** Go to Settings → API → Project API keys → copy the `anon` `public` key (the long JWT starting with `eyJ...`).

### 3. Set up Supabase database

1. Create a new project at [supabase.com](https://supabase.com)
2. Go to SQL Editor in your project dashboard
3. Paste the contents of `schema.sql` and run it

This creates the tables: `macro_events`, `dominant_variables`, `expectations`, `custom_assets`.

### 4. Run the app

```bash
source .venv/bin/activate
streamlit run app.py
```

The app opens at `http://localhost:8501`.

## Running Without External Services

The app works in degraded mode without any API keys:

- **Without Supabase** — App runs in read-only mode. Events, journal entries, and expectations won't persist.
- **Without FRED** — US 10Y and 2Y yield data won't load. All other assets still work via yfinance.
- **Without Twelve Data** — Some intraday intervals may not be available. yfinance handles most data.
- **yfinance** — No API key needed. May rate-limit if you refresh too frequently.

## Deploy to Streamlit Community Cloud

### 1. Push to GitHub

```bash
git add .
git commit -m "Initial dashboard implementation"
git push origin main
```

Make sure `.streamlit/secrets.toml` is in `.gitignore` (it is by default).

### 2. Deploy on Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Connect your GitHub repo
3. Set main file path to `app.py`
4. Add secrets in the Streamlit Cloud dashboard (Settings → Secrets):

```toml
[fred]
api_key = "your_fred_api_key"

[twelve_data]
api_key = "your_twelve_data_api_key"

[supabase]
url = "https://your-project-id.supabase.co"
key = "your_supabase_anon_key"
```

## GitHub Actions (Optional)

You can set up a scheduled workflow to pre-cache historical data, reducing cold-start times.

### Setup

Create `.github/workflows/data-cache.yml`:

```yaml
name: Pre-cache Market Data

on:
  schedule:
    # Run daily at 6:00 UTC (before US market open)
    - cron: '0 6 * * 1-5'
  workflow_dispatch:  # Allow manual trigger

jobs:
  cache-data:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: pip install yfinance fredapi pandas

      - name: Fetch and cache data
        env:
          FRED_API_KEY: ${{ secrets.FRED_API_KEY }}
        run: python scripts/prefetch_data.py
```

### GitHub Secrets

Add these in your repo → Settings → Secrets and variables → Actions:

| Secret Name | Value |
|-------------|-------|
| `FRED_API_KEY` | Your FRED API key |
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_KEY` | Your Supabase anon key |

### Pre-fetch Script

Create `scripts/prefetch_data.py` if you want to implement data pre-caching:

```python
"""Pre-fetch and cache historical market data via GitHub Actions."""
import os
import yfinance as yf
from fredapi import Fred

# This script can be expanded to:
# 1. Fetch historical data for all tracked assets
# 2. Store snapshots in Supabase for faster dashboard loading
# 3. Update macro event databases with scheduled releases

SYMBOLS = ["DX-Y.NYB", "CL=F", "GC=F", "^GSPC", "^VIX", "BTC-USD"]
FRED_SERIES = ["DGS10", "DGS2"]

def main():
    # Fetch yfinance data
    for symbol in SYMBOLS:
        data = yf.download(symbol, period="1y", interval="1d")
        print(f"{symbol}: {len(data)} rows")

    # Fetch FRED data
    fred_key = os.environ.get("FRED_API_KEY")
    if fred_key:
        fred = Fred(api_key=fred_key)
        for series in FRED_SERIES:
            data = fred.get_series(series)
            print(f"FRED {series}: {len(data)} rows")

if __name__ == "__main__":
    main()
```

## Project Structure

```
app.py                          # Main entry point & landing page
pages/
  1_📊_Asset_Monitor.py         # Real-time prices, candlestick/line charts
  2_🔗_Cross_Asset.py           # Correlation matrix, overlays, shift detection
  3_🎯_Dominant_Variable.py     # Factor ranking, manual recording, timeline
  4_📅_Event_Analysis.py        # Event impact, cross-event comparison
  5_📈_Expectations.py          # Surprise magnitude, asset reactions, patterns
lib/
  models.py                     # Data models, enums, DEFAULT_ASSETS, INTERVALS
  data_fetcher.py               # yfinance/FRED/Twelve Data with caching
  calculations.py               # Correlations, normalization, dominant variable
  db.py                         # Supabase persistence with validation
schema.sql                      # Database schema (apply in Supabase SQL Editor)
tests/
  unit/                         # Unit tests (pytest)
.streamlit/
  secrets.toml.example          # Template for API keys
```

## Running Tests

```bash
source .venv/bin/activate
pytest tests/ -v
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError` | Make sure you activated the venv: `source .venv/bin/activate` |
| yfinance rate limited | Wait 1-2 minutes, the cache will prevent repeat hits |
| Supabase "Invalid API key" | Use the `anon public` JWT key (starts with `eyJ...`), not the project password |
| Supabase "table not found" | Apply `schema.sql` in your Supabase SQL Editor |
| FRED "not configured" | Add your FRED API key to `.streamlit/secrets.toml` under `[fred]` |
| Charts not rendering | Ensure `streamlit-lightweight-charts` is installed (`pip install -r requirements.txt`) |

## License

MIT
