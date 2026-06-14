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

# ── Fundamentals snapshot (Finviz quote ticker_fundament) ────────────────────
# Frozen field list (the 90 Finviz fields minus the junk 'Trades'). Captured
# point-in-time per candidate — some fields (Short Float, Inst Own, Recom,
# Perf*) are NOT reconstructable later.
FINVIZ_FUNDAMENT_FIELDS = [
    "Company", "Sector", "Industry", "Country", "Exchange", "Index",
    "P/E", "EPS (ttm)", "Insider Own", "Shs Outstand", "Perf Week", "Market Cap",
    "Forward P/E", "EPS next Y", "Insider Trans", "Shs Float", "Perf Month",
    "Enterprise Value", "PEG", "EPS next Q", "Inst Own", "Short Float",
    "Perf Quarter", "Income", "P/S", "EPS this Y", "Inst Trans", "Short Ratio",
    "Perf Half Y", "Sales", "P/B", "EPS next Y Percentage", "ROA",
    "Short Interest", "Perf YTD", "Book/sh", "P/C", "EPS next 5Y", "ROE",
    "52W High", "Perf Year", "Cash/sh", "P/FCF", "EPS past 3/5Y", "ROIC",
    "52W Low", "Perf 3Y", "Dividend Est.", "EV/EBITDA", "Sales past 3/5Y",
    "Gross Margin", "Volatility W", "Volatility M", "Perf 5Y", "Dividend TTM",
    "EV/Sales", "EPS Y/Y TTM", "Oper. Margin", "ATR (14)", "Perf 10Y",
    "Dividend Ex-Date", "Quick Ratio", "Sales Y/Y TTM", "Profit Margin",
    "RSI (14)", "Recom", "Dividend Gr. 3/5Y", "Current Ratio", "EPS Q/Q",
    "SMA20", "Beta", "Target Price", "Payout", "Debt/Eq", "Sales Q/Q", "SMA50",
    "Rel Volume", "Prev Close", "Employees", "LT Debt/Eq", "Earnings", "SMA200",
    "Avg Volume", "Price", "IPO", "Option/Short", "EPS/Sales Surpr.", "Volume",
    "Change",
]

# Field tiers for M4 (documentation only — NO scoring here).
FUND_PRIMARY = [   # hypothesised candidate predictors
    "RSI (14)", "ATR (14)", "Beta", "Volatility W", "Volatility M",
    "52W High", "52W Low", "Rel Volume", "Avg Volume",
    "Short Float", "Short Ratio", "Short Interest",
    "Profit Margin", "Oper. Margin", "Gross Margin", "ROE", "ROA", "ROIC",
    "EPS this Y", "EPS next Y", "EPS next 5Y", "EPS Q/Q", "EPS Y/Y TTM",
    "EPS past 3/5Y", "Perf Week", "Perf Month", "Perf Quarter", "Perf Half Y",
    "Perf Year", "Inst Own", "Insider Own", "Recom",
]
FUND_PERIPHERAL = [   # exploratory / wide net
    "P/E", "Forward P/E", "PEG", "P/S", "P/B", "P/FCF", "EV/EBITDA", "EV/Sales",
    "Sales past 3/5Y", "Sales Y/Y TTM", "Sales Q/Q", "Dividend TTM",
    "Dividend Est.", "Shs Outstand", "Shs Float", "Income", "Sales",
    "Book/sh", "Cash/sh",
]
# Single-value numeric fields to parse into a clean *_num column (raw kept too).
# Compound fields (52W High/Low, EPS/Sales past 3-5Y, Option/Short, EPS/Sales
# Surpr., Dividend Gr.) are kept RAW only; 52W distance handled specially.
FUND_NUMERIC = [
    "P/E", "EPS (ttm)", "Insider Own", "Shs Outstand", "Perf Week", "Market Cap",
    "Forward P/E", "EPS next Y", "Insider Trans", "Shs Float", "Perf Month",
    "Enterprise Value", "PEG", "EPS next Q", "Inst Own", "Short Float",
    "Perf Quarter", "Income", "P/S", "EPS this Y", "Inst Trans", "Short Ratio",
    "Perf Half Y", "Sales", "P/B", "EPS next Y Percentage", "ROA",
    "Short Interest", "Perf YTD", "Book/sh", "P/C", "EPS next 5Y", "ROE",
    "Perf Year", "Cash/sh", "P/FCF", "ROIC", "Perf 3Y", "Gross Margin",
    "Volatility W", "Volatility M", "Perf 5Y", "Dividend TTM", "EV/Sales",
    "EPS Y/Y TTM", "Oper. Margin", "ATR (14)", "Quick Ratio", "Sales Y/Y TTM",
    "Profit Margin", "RSI (14)", "Recom", "Current Ratio", "EPS Q/Q", "SMA20",
    "Beta", "Target Price", "Payout", "Debt/Eq", "Sales Q/Q", "SMA50",
    "Rel Volume", "Prev Close", "Employees", "LT Debt/Eq", "Avg Volume",
    "Price", "Change",
]
TAB_FUNDAMENTALS = "fundamentals_snapshot"

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
