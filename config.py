"""config.py — ReboundPro M1 (minimal live collector).

Single source of truth for the M1 scanner + post-analysis collector.
All values are hypotheses to be calibrated from data later (see BuildSpec).
"""
import os

# ── .env loader (no external dep) ────────────────────────────────────────────
def _load_dotenv():
    path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(path):
        return
    for line in open(path):
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()

# ── Universe & drop trigger ──────────────────────────────────────────────────
EXCHANGES = ["NASDAQ", "NYSE"]
DROP_THRESHOLD_FROM_OPEN = 10.0      # % ; candidate if intraday low ≤ -this from open
# Finviz server-side pre-filter (prev-close based). Looser than the from-open rule
# so we don't miss gap-up-then-crash names; exact rule re-applied via yfinance.
# NOTE: Finviz "Change" is vs prev close, not vs open — documented limitation.
FINVIZ_CHANGE_PREFILTER = "Down 7%"
FINVIZ_CHANGE_FALLBACK = "Down 5%"   # used if the primary filter value is rejected

# ── Hard liquidity floor (no nano/micro) ─────────────────────────────────────
MIN_PRICE = 5.0                       # USD
MIN_ADV_DOLLAR = 5_000_000           # 20-day avg $ volume
MIN_MARKET_CAP = 300_000_000         # above "Micro" (Micro = 50M–300M); Small+ only

# ── Post-analysis ────────────────────────────────────────────────────────────
POST_ANALYSIS_HORIZON = 5            # collect D1..D+N
TOUCH_UP_PCT = 5.0                   # "did it touch +X% from scan close"
TOUCH_DOWN_PCT = 8.0                 # "did it touch -Y% from scan close"

# ── Storage ──────────────────────────────────────────────────────────────────
# SA cannot create sheets (Drive quota). User creates + shares the sheet with the
# service account, then sets the ID here or via env REBOUND_SHEET_ID.
SHEET_ID = os.environ.get("REBOUND_SHEET_ID", "")
TAB_WATCHLIST = "watchlist_live"
TAB_POST = "post_analysis"
CREDS_PATH = os.path.join(os.path.dirname(__file__), "google_credentials.json")

# ── Regime (market/sector context) ───────────────────────────────────────────
MARKET_PROXY = "SPY"
SECTOR_ETF = {
    "Technology": "XLK", "Financial Services": "XLF", "Financial": "XLF",
    "Healthcare": "XLV", "Consumer Cyclical": "XLY", "Consumer Defensive": "XLP",
    "Energy": "XLE", "Industrials": "XLI", "Basic Materials": "XLB",
    "Utilities": "XLU", "Real Estate": "XLRE", "Communication Services": "XLC",
}
RISK_OFF_SPY_PCT = -1.0              # SPY day move ≤ this → "risk_off" regime

# ── Misc ─────────────────────────────────────────────────────────────────────
RATE_LIMIT_SLEEP = 0.30             # seconds between per-ticker yfinance calls
HISTORY_DAYS_FETCH = 90             # calendar days pulled per candidate (ADV/RSI)


def classify_market_cap(mc):
    """Nano/Micro/Small/Mid/Large/Mega — matches DropsLab thresholds."""
    try:
        mc = float(mc)
    except (TypeError, ValueError):
        return "Unknown"
    if mc != mc:  # NaN
        return "Unknown"
    if mc >= 200e9: return "Mega"
    if mc >= 10e9:  return "Large"
    if mc >= 2e9:   return "Mid"
    if mc >= 300e6: return "Small"
    if mc >= 50e6:  return "Micro"
    return "Nano"
