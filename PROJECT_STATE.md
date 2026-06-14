# ReboundPro — PROJECT STATE

**עודכן:** 2026-06-13 · **שלב:** Skeleton (טרם Phase 0)

## איפה אנחנו
- ✅ מסמך-אב: `~/Downloads/ReboundPro_MasterPlan_2026-06-13_v0.1.md`
- ✅ build spec מאושר: `docs/ReboundPro_BuildSpec_v0.1.md`
- ✅ שלד repo נוצר (עץ תיקיות + stubs + docs). אין קוד לוגי. לא בוצע commit/push.
- ⬜ Phase 0 — harness לבדיקת יתרון (הצעד הבא)
- ⬜ Phase 0.5 — מסנן קטליסט
- ⬜ Phase 1 — בנייה מלאה (מותנה ביתרון)

## החלטות שאושרו (2026-06-13)
- שם: ReboundPro · יקום: NASDAQ+NYSE · סף: 10% (grid 7/10/15)
- ספק: Polygon (intraday) + FMP (fundamentals/news); yfinance/EODHD fallback היסטורי
- חלון החזקה: נגזר מ-Phase 0

## תלויות פתוחות לפני Phase 0
- ⬜ מפתח Polygon API
- ⬜ מפתח FMP API
- ⬜ הרשאת קריאה ל-Sheet של DropsLab (`1M-ofmSmUHAb7o8J_pZFKYHh4N1aZVOXVWngFzTYxjZQ`)
- ⬜ Google service-account credentials (לאחסון ReboundPro)

## לקחים שמיובאים מ-RidingHigh / DropsLab
- מדד חסר קורלציה לא נכנס לניקוד (Score r≈-0.07).
- יישור עמודות ב-Sheets — מקור באגים; data_integrity agent.
- כל הזמנים Peru UTC-5, ללא DST.
- survivorship: לספור halts/delistings כתוצאה, לא להשמיט.
