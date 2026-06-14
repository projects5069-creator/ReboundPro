# ReboundPro — Build Spec v0.1

> **תאריך:** 2026-06-13 · **סטטוס:** מאושר · **בסיס:** `~/Downloads/ReboundPro_MasterPlan_2026-06-13_v0.1.md`
> מסמך זה הוא מקור-האמת לתכנון הבנייה. כל מדד/סף/יעד הוא השערה שתיבחן מול נתונים לפני שימוש.

## Context — למה ולמה עכשיו

ReboundPro היא מערכת מחקר חדשה, **עצמאית לחלוטין**, שמזהה מניות אמריקאיות שצנחו במהלך היום ובוחנת אם הצניחה היא הזדמנות לתפוס חזרה כלפי מעלה (long). היא ההפך הסימטרי של RidingHigh Pro (short).

**הבעיה שהתוכנית פותרת:** ביקורת מול מחקר אקדמי קבעה שחזרה תמימה ("קנה כל יורדת") אינה רווחית אחרי עלויות — היתרון יושב במיקרו-קאפ שבהן עלויות המסחר בולעות אותו, ובהבחנה בין צניחה ללא חדשות (תגובת יתר → חוזרת, Chan 2003) לבין צניחה על חדשות רעות (סכין נופלת). לכן **לא בונים מערכת לפני שמוכיחים יתרון נטו-אחרי-עלויות על נתונים היסטוריים** (Phase 0).

**התוצאה הרצויה:** harness שמכריע אם קיים יתרון אמיתי; ורק אם כן — שלד מערכת רזה (דטרמיניסטי כברירת מחדל, LLM רק לקטליסט/נימוק) שאוסף, מסמלץ (paper בלבד), ומודד.

**החלטות שאושרו (2026-06-13):** שם = **ReboundPro** · יקום = **NASDAQ+NYSE** · סף ירידה = **10%** (בדיקת grid 7/10/15) · ספק = **Polygon (intraday) + FMP (fundamentals)**, yfinance/EODHD כ-fallback היסטורי ל-Phase 0 · חלון החזקה = **Phase 0 מחשב את כל החלונות, ההחלטה תיגזר מהנתונים**.

**נכס מפתח שזוהה:** DropsLab (`Ambroseius/DropsLab`, sheet `1M-ofmSmUHAb7o8J_pZFKYHh4N1aZVOXVWngFzTYxjZQ`, tab `DropsLab-Data`) כבר סורק NASDAQ+NYSE לירידות 10%+ עם 38 מדדים. זה בדיוק הדאטה-סט שצריך ל-Phase 0 — אבל "accumulating, not yet analyzed", כך שעומק ההיסטוריה מוגבל וידרוש backfill מ-Polygon/EODHD.

**עיקרון מנחה:** אסטרטגיה ש"נשברת הכי פחות", לא ש"מרוויחה הכי הרבה על הנייר". 20% מהזמן ליצירת רעיון, 80% לניסיון לשבור אותו. כל בדיקה נטו-אחרי-עלויות. נתוני point-in-time בלבד.

---

## א. Phase 0 — Edge-Existence Harness (לפני הכול)

**שאלת המחקר (משפט אחד):** "מתוך מניות NASDAQ+NYSE שצנחו ≥10% ביום, איזה אחוז חזר כלפי מעלה, בכמה, באיזה חלון כניסה/יציאה — ואחרי הורדת עלויות, האם נשאר יתרון נטו בדלי הנזילות הגדול/בינוני?"

פרויקט-משנה נפרד (`research/phase0/`) שרץ פעם אחת על היסטוריה. **אם אין כאן אות חזרה נטו ברור — חוזרים ללוח השרטוט לפני בנייה.**

### קלט נתונים
1. **DropsLab history** — רשימת המניות שצנחו 10%+ בכל יום + 38 המדדים שנרשמו *באותו רגע* (point-in-time מובנה — המדדים לא מתוקנים בדיעבד).
2. **Backfill OHLC קדימה** מ-Polygon (daily + intraday bars): D0 (intraday), D+1..D+20. ל-Phase 0 אפשר EODHD/yfinance כ-fallback זול להיסטוריה רחוקה.
3. **חדשות point-in-time** מ-FMP/Finnhub news API לחלון [D-1, D0] — לפיצול קטליסט (Phase 0.5).

### מטריצת חלונות (entry × exit) — ליבת constraint timing
לכל מועמדת מחשבים תשואה קדימה עבור **כל שילוב**:
- **חלונות כניסה:** (a) D0 close · (b) D+1 open · (c) intraday reversal-confirmed (כניסה רק אחרי נר היפוך/סגירת בר גבוהה — מונע "תפיסת סכין").
- **חלונות מדידה/יציאה:** intraday same-day · overnight (D0 close→D+1 open) · D+1 · D+3 · D+5 · D+10 · D+20.

פלט לכל תא: % שחזר, תשואה חציונית/ממוצעת, MAE/MFE, Profit Factor, win-rate.

### מודל עלויות (מהיום הראשון) — `costs.py`
מנוכה מכל תשואה. לכל עסקה: `commission + half_spread + slippage`.
- **commission:** נקודת פתיחה $0 (ברוקר מודרני) + בדיקת רגישות.
- **spread:** מוערך לפי דלי נזילות (ADV/מחיר) — צר ל-large-cap, רחב ל-micro.
- **slippage:** בדיקה ב-1.0x / 1.5x / 2.0x; worst-case fill = buy@ask+tick, sell@bid-tick.
- **stress:** הרצה גם בתרחיש פסימי (slippage 2x + spread רחב) — מה ששורד שם אמין.

### הטיית-נזילות — go/no-go מרכזי
פילוח כל התוצאות ל**דליי נזילות** (לפי ADV וגם שווי שוק): micro / small / mid / large. הדרישה: יתרון נטו חייב לשרוד **בדלי mid+large**, לא רק ב-micro. אם היתרון יושב רק ב-micro — נדחה.

### Phase 0.5 — אב-טיפוס מסנן הקטליסט (הרכיב המנבא ביותר)
בונים ומודדים **לבד**, לפני שאר המנוע, את ההבחנה news-vs-no-news:
- דטרמיניסטי: האם קיימת כותרת חדשות בחלון [D-1, D0]? (FMP/Finnhub).
- LLM: מסווג כותרת קיימת ל-taxonomy → {no-news, sympathy/sector, systemic, temporary-bad} מול {earnings-miss, dilution, going-concern, binary-failure}.
- מודדים bounce-rate נטו **בכל קטגוריה בנפרד**. אימות Chan: no-news/sympathy חוזרות; earnings-miss/dilution ממשיכות לרדת.

### הגנות מ-bias
- **Look-ahead:** חלון כניסה (c) intraday משתמש רק בברים *עד* רגע ההיפוך — לא ב-OHLC של כל היום. פונדמנטלס/חדשות = רק מה שהיה ידוע ב-D0. אסור מדדים מתוקנים בדיעבד.
- **Survivorship:** DropsLab רשם את המניות *ברגע הצניחה*, כולל כאלה שנמחקו/הושהו → המדגם survivorship-safe by construction. מטפלים מפורשות ב-halts ובמניות שירדו מהמסחר (סופרים כתוצאה, לא משמיטים).
- **Sample size:** מינימום 100+ עסקאות לכל דלי×חלון לפני מסקנה; אם DropsLab דליל → מרחיבים backfill מ-EODHD.
- **Baseline תמים:** "קנה כל ירידה 10%, החזק D+5" — המנוע חייב לנצח אותו נטו.

### Go/No-Go
שימוש ב-`backtest-expert/scripts/evaluate_backtest.py` → verdict Deploy/Refine/Abandon + per-dimension scores + red-flags. **רף מעבר:** יתרון נטו מובהק בדלי mid+large, יציב על grid הספים (7/10/15) ועל 1.5–2x slippage, חוזר על עצמו בין תקופות.

**Phase 0 deliverables:** `research/phase0/` scripts + `research/phase0/REPORT.md` + `verdict.json`. רק אם Deploy/Refine → ממשיכים לשלד.

---

## ב. מבנה Repo ועץ קבצים

```
ReboundPro/
├── README.md
├── CLAUDE.md                      # PK חי — מקור אמת יחיד (חוזה אנטי-drift)
├── PROJECT_STATE.md
├── requirements.txt              # uv-managed
├── pyproject.toml
├── config.py                     # L1: משקלים/ספים/דליי-נזילות — single source of truth
├── formulas.py                   # מדדים טהורים: RSI, ATR, VWAP-dist, candle-reversal, bounce-score
├── costs.py                      # commission + spread + slippage — מנוכה מכל תשואה
├── utils.py                      # timezone (Peru UTC-5), trading-day math, parsers
├── data_provider.py              # PolygonProvider | FMPProvider | YFinanceFallback
├── sheets_manager.py             # Google Sheets I/O + רוטציה חודשית
├── sheets_config.json            # מיפוי tab→ID חודשי
├── scanner.py                    # שכבה 1: סריקה תוך-יומית, סף ירידה
├── post_analysis_collector.py    # שכבה 6: תוצאות D1..D+N
├── backfill_ohlc.py              # מילוי OHLC חסר
├── dashboard.py                  # Streamlit
├── agent/
│   ├── orchestrator.py           # #15 מתזמר (control flow דטרמיניסטי)
│   ├── watchlist.py              # שכבה 2: ניהול מעקב
│   ├── profile.py                # #2 פונדמנטלס+זהות+בעלות
│   ├── market_context.py         # #4 מדדים/ETF סקטוריאלי באותו יום
│   ├── technical.py              # #5 RSI/ATR/VWAP/גאפ/נר היפוך
│   ├── liquidity.py              # #6 ADV/spread/float/halt-risk
│   ├── catalyst/                 # #3 ← רכיב ה-LLM היחיד החובה
│   │   ├── news_fetch.py         #   דטרמיניסטי: שליפת חדשות point-in-time
│   │   └── classify.py           #   LLM: news-vs-no-news taxonomy + confidence
│   ├── sentiment.py              # #7 OSINT/סנטימנט — אופציונלי (שלב 2)
│   ├── debate.py                 # #8 bull/bear — אופציונלי (שלב 2)
│   ├── scoring.py                # #9 מנוע ניקוד סבירות-חזרה
│   ├── risk_targets.py           # #10 יעד+סטופ ATR + position sizing
│   ├── portfolio.py              # #11 סימולציית paper
│   ├── outcome.py                # #12 איסוף D1..D+N, win-rate, PF
│   ├── learning.py               # #13 קורלציה מדד↔תוצאה, פסילת מדדים, משקלים
│   ├── data_integrity.py         # #14 יישור עמודות, חסרים, כפילויות
│   └── utils/
├── research/
│   ├── phase0/                   # ה-harness — REPORT.md + scripts + verdict.json
│   └── catch_all/                # קובץ "תפוס הכול" (כל מדד אפשרי)
├── tests/                        # pytest
├── docs/
│   ├── ReboundPro_PK_v1.md
│   └── ReboundPro_BuildSpec_v0.1.md
├── scripts/
└── .github/workflows/
```

---

## ג. מודולים: דטרמיניסטי מול LLM + מיפוי שכבות→קוד

**עיקרון רזה:** ברירת מחדל = פונקציות דטרמיניסטיות. מתוך 15 הסוכנים — **רק 1 חובה-LLM**, 2 אופציונליים, היתר פונקציות טהורות.

| # | סוכן | סוג | מימוש |
|---|------|-----|-------|
| 1 | Scanner | דטרמיניסטי | `scanner.py` |
| 2 | Profile/Fundamentals | דטרמיניסטי | `agent/profile.py` (FMP) |
| 3 | **News/Catalyst** | **LLM (חובה)** | `agent/catalyst/` — fetch דטרמיניסטי + classify LLM |
| 4 | Market Context | דטרמיניסטי | `agent/market_context.py` |
| 5 | Technical | דטרמיניסטי | `agent/technical.py` |
| 6 | Liquidity | דטרמיניסטי | `agent/liquidity.py` |
| 7 | Sentiment/OSINT | LLM (אופציונלי, שלב 2) | `agent/sentiment.py` |
| 8 | Bull/Bear Debate | LLM (אופציונלי, שלב 2) | `agent/debate.py` |
| 9 | Scoring | דטרמיניסטי | `agent/scoring.py` |
| 10 | Risk & Targets | דטרמיניסטי | `agent/risk_targets.py` |
| 11 | Portfolio/Sim | דטרמיניסטי | `agent/portfolio.py` |
| 12 | Outcome/Post | דטרמיניסטי | `agent/outcome.py` |
| 13 | Learning/Validation | דטרמיניסטי (סטטיסטיקה) | `agent/learning.py` |
| 14 | Data-Integrity | דטרמיניסטי | `agent/data_integrity.py` |
| 15 | Orchestrator | דטרמיניסטי (control flow) | `agent/orchestrator.py` |

**מנהל-אנליסט:** `orchestrator.py` הוא control-flow דטרמיניסטי (לא LLM) שמתזמן את הזרימה. ה-LLM מופעל *נקודתית* מ-`catalyst/classify.py` (ובהמשך sentiment/debate). מונע מלכודת "כל סוכן = LLM".

**ה-LLM call (catalyst):** קלט = כותרות חדשות point-in-time + מטא (סקטור, גודל). פלט מובנה (JSON schema, tool-use): `{label, is_falling_knife: bool, confidence, reasoning}`. דגם: Haiku 4.5 לרוב, Opus למקרי גבול. (לפני מימוש — לקרוא claude-api skill.)

**מיפוי 7 שכבות → קוד:**
1. איסוף → `scanner.py` + `data_provider.py`
2. מעקב → `agent/watchlist.py`
3. ניתוח → `agent/{profile,market_context,technical,liquidity,catalyst,sentiment,debate}.py`
4. ניקוד+החלטה → `agent/{scoring,risk_targets}.py`
5. סימולציה → `agent/portfolio.py`
6. תוצאות+למידה → `post_analysis_collector.py` + `agent/{outcome,learning}.py`
7. תשתית → `sheets_manager.py`, `.github/workflows/`, `agent/data_integrity.py`, `dashboard.py`

---

## ד. נתונים, אחסון, תזמון, Sheets, דשבורד

**שכבת נתונים (`data_provider.py`):** `DataProvider` אבסטרקטי + `PolygonProvider` (intraday bars/quotes), `FMPProvider` (fundamentals/news), `YFinanceFallback` (Phase 0 history). מפתחות ב-`.env` + Actions secrets. נתוני point-in-time.

**אחסון (Google Sheets, רוטציה חודשית):** tabs:
- `watchlist_live` · `analysis` · `catch_all` (כל מדד אפשרי, גם לא-מנוקד) · `decisions` · `paper_portfolio` (PnL נטו) · `post_analysis` (D1..D+N, bounce-hit, MaxRise%, חלון) · `market_context` · `daily_summary` / `validation`.

**תזמון (`.github/workflows/`, זמני Peru UTC-5):**
| workflow | cron (UTC) | תפקיד |
|----------|-----------|-------|
| `scan.yml` | `*/N 13-20 * * 1-5` | סריקה תוך-יומית (N=2–5 דק') |
| `post_analysis.yml` | `5 21 * * 1-5` | תוצאות D1..D+N + backfill |
| `learning_weekly.yml` | `0 23 * * 5` | קורלציות + הצעת משקלים |
| `health_audit.yml` | `0 21 * * *` | data_integrity |

(cron-job.org dispatch אם נדרש דיוק דקתי; אחרת cron רגיל מספיק ל-N=2–5 דק'.)

**דשבורד (`dashboard.py`, Streamlit):** watchlist חי, paper-portfolio + P&L נטו, פילוח bounce-rate לפי קטליסט/דלי-נזילות/חלון, לוח ולידציה (קורלציות). כל P&L = נטו אחרי עלויות.

---

## ה. מתודולוגיית ולידציה (`agent/learning.py`)

1. **איסוף** חודש-חודשיים, paper בלבד, תיעוד מלא ב-`catch_all`.
2. **מדידת תוצאה** לכל מועמדת: חזרה? בכמה? באיזה חלון? (D1..D+N) — נטו.
3. **קורלציה** לכל מדד מול חזרה מוצלחת. מדד חסר קורלציה **נפסל** (לקח: Score r≈-0.07).
4. **Profit Factor + win-rate** על *כל* היקום (anti-survivorship).
5. **כיול ספים** מהנתונים: סף ירידה, רצפת איכות, יעד, סטופ, חלון.
6. **A/B:** כניסה מיידית מול המתנה-לאישור; intraday מול swing.
7. **Walk-forward:** out-of-sample <50% מ-in-sample = דגל אדום.
8. **Baseline תמים** כרף תחתון קבוע — ניצחון נטו = תנאי הכרחי.
9. **כלי הכרעה:** `evaluate_backtest.py` + plateau-check (פרמטרים יציבים בטווח, לא spike).

---

## ו. סיכונים ונקודות כשל

| סיכון | שליטה |
|------|-------|
| **סכין נופלת** | מסנן קטליסט (Phase 0.5) + רצפת איכות כשער קשיח |
| **Survivorship bias** | DropsLab point-in-time כולל נמחקות; סופרים halts/delistings כתוצאה |
| **Look-ahead bias** | point-in-time; כניסת intraday רק עד רגע ההיפוך; אסור מדדים מתוקנים |
| **Overfitting** | walk-forward, plateau-not-peak, מובהקות, grid ספים |
| **נזילות/slippage בולעים יתרון** | מודל עלויות מיום 1, פילוח דליי-נזילות, דרישת יתרון ב-mid+large |
| **Halts** | סטטוס השהיה מטופל ב-`liquidity.py` ובסימולציה |
| **עלות/רעש LLM** | LLM רק לקטליסט (1/15); פלט מובנה; Haiku ברירת מחדל |
| **DropsLab דליל** | backfill EODHD; אחרת מרחיבים חלון איסוף |
| **drift בעובדות** | PK יחיד + סקיל reboundpro-live מצביע-בלבד; data_integrity |
| **בלבול UTC/Peru** | כל הזמנים דרך `utils.py` (Peru UTC-5, ללא DST) |

---

## רצף ביצוע

1. **Phase 0** (`research/phase0/`): harness על DropsLab+backfill → `REPORT.md` + verdict. **שער go/no-go.**
2. **Phase 0.5:** אב-טיפוס מסנן קטליסט, news-vs-no-news לבד.
3. רק אם יתרון נטו אושר → **Phase 1:** config/formulas/costs/data_provider/sheets → scanner → watchlist → analysis → scoring → paper-sim → post-analysis → dashboard → workflows.
4. חודש-חודשיים איסוף paper → סוכן למידה → כיול → החלטת המשך.

## Verification

- **Phase 0:** `evaluate_backtest.py` עם מספרי ה-harness; יציבות על grid ספים (7/10/15) ו-slippage 1.0/1.5/2.0x; יתרון שורד בדלי mid+large; השוואה ל-baseline תמים. הכול נטו.
- **קוד:** `pytest tests/` (uv-managed) — יחידה ל-`formulas.py`, `costs.py`, `scoring.py`, וסימולציית `portfolio.py`.
- **נתונים:** health_audit מאמת עדכון tabs; data_integrity בודק יישור/חסרים.
- **end-to-end:** הרצת scanner ידנית על יום מסחר → watchlist→analysis→decision→paper_portfolio זורם ונכתב ל-Sheets; דשבורד מציג P&L נטו.

---
*v0.1 — מאושר 2026-06-13. יתעדכן עם תוצאות Phase 0.*
