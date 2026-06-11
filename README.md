# 🌍 Global Macro Intelligence Dashboard

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://global-macro-intelligence-dashboard-hsubvvqbv9zhoyaqfsqgwz.streamlit.app/)

A single-page Streamlit dashboard tracking 7 key macro instruments with daily/weekly percentage changes, volatility-adjusted dominant variable identification, AI-powered cross-asset narratives, and scraped Edward Jones market reports.

## What It Does

- **7 Macro Instruments** — US10Y, US2Y, DXY, Oil, SPY, QQQ, VIX with daily/weekly % changes color-coded (green/red)
- **Dominant Variable** — Identifies which instrument is moving the most *relative to its own normal volatility* (z-score based, not raw %)
- **AI Cross-Asset Narrative** — Gemini-powered 2-3 sentence explanation of what's driving markets and how it's transmitting across assets
- **Market Report TL;DRs** — AI-generated 3-4 bullet summaries of Edward Jones daily/weekly reports
- **Smart Caching** — One yfinance batch call per day, cached locally. No rate limit issues.
- **Mauritius Timezone Aware** — Resolves the latest completed US market day from UTC+4

## Tech Stack

- **UI**: Streamlit
- **Market Data**: yfinance (single batch `yf.download()` call for all 7 instruments)
- **Reports**: BeautifulSoup scraping Edward Jones daily/weekly recaps
- **AI**: Google Gemini 2.0 Flash (free tier, falls back to heuristic when unavailable)
- **Caching**: File-based JSON cache (`.cache/` directory)

## Local Development

```bash
# Clone
git clone https://github.com/YOUR_USERNAME/Global-Macro-Intelligence-Dashboard.git
cd Global-Macro-Intelligence-Dashboard

# Setup
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure secrets
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Edit .streamlit/secrets.toml with your Gemini API key

# Run
streamlit run app.py
```

## Deployment on Streamlit Cloud

No GitHub Actions needed. No environment variables on GitHub. Just:

1. Push to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your GitHub repo
4. Set main file to `app.py`
5. Add secrets in Streamlit Cloud dashboard (Settings → Secrets):

```toml
[gemini]
key = "your_gemini_api_key_here"
```

That's it. Streamlit Cloud handles the rest.

## Project Structure

```
├── app.py                  # Single-page Streamlit dashboard
├── lib/
│   ├── market_day.py       # US market day resolution (timezone, holidays)
│   ├── calculations.py     # Daily/weekly % change, dominant variable logic
│   ├── data_fetcher.py     # yfinance batch fetcher (7 instruments)
│   ├── scraper.py          # Edward Jones report scraper
│   ├── cache.py            # File-based JSON cache
│   └── ai_summary.py       # Gemini AI narratives + TL;DRs
├── tests/
│   ├── unit/               # Unit tests
│   └── properties/         # Hypothesis property-based tests
├── .streamlit/
│   ├── secrets.toml        # Your API keys (gitignored)
│   └── secrets.toml.example
├── requirements.txt
└── pyproject.toml
```

## Running Tests

```bash
pytest tests/ -v
```

61 tests covering calculations, market day resolution, caching, and 9 Hypothesis property tests.
