# Markedsdashboard

BTC, Nasdaq Composite, VIX og CNN Fear & Greed – genbygges automatisk hver time med GitHub Actions og vises via GitHub Pages.

- `scripts/build.py` henter data (Yahoo Finance, CNN), beregner trendkanal ±1σ/±2σ, MA200, RSI(14) og Bollinger Bands og bygger siden i `site/`.
- `web/index.html` er selve dashboardet.
- Kør manuelt: fanen **Actions → Opdater dashboard → Run workflow**.
- Lokal test med syntetiske data: `python scripts/build.py --demo`.
