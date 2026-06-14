# ReboundPro

מערכת מחקר עצמאית לזיהוי מניות אמריקאיות (NASDAQ+NYSE) שצנחו ≥10% ביום, וניסיון לתפוס את ההתאוששות שלהן כלפי מעלה (long). ההפך הסימטרי של RidingHigh Pro (short). **סימולציה בלבד — אין כסף אמיתי.**

> סטטוס: **שלד** (skeleton). אין עדיין קוד לוגי. הצעד הראשון הוא **Phase 0** — בדיקת קיום יתרון נטו-אחרי-עלויות על נתונים היסטוריים. אם אין יתרון — לא בונים.

## עקרונות יסוד

- **קודם מודדים, אחר כך בונים.** שום מדד לא נכנס לניקוד לפני שהוכח סטטיסטית שהוא מנבא חזרה (הלקח מ-RidingHigh: Score r≈-0.07).
- **נטו אחרי עלויות תמיד.** commission + spread + slippage נכנסים למודל מהיום הראשון (`costs.py`).
- **הטיה קשיחה לנזילות.** היתרון חייב לשרוד בדלי mid+large, לא רק ב-micro.
- **רזה.** ברירת מחדל = פונקציות דטרמיניסטיות. LLM רק לסיווג קטליסט (news-vs-no-news, Chan 2003).
- **point-in-time.** מניעת look-ahead ו-survivorship bias.

## מסמכים

- `docs/ReboundPro_BuildSpec_v0.1.md` — מפרט הבנייה המאושר (מקור אמת לתכנון).
- `docs/ReboundPro_PK_v1.md` — Project Knowledge חי (ימולא בהמשך).

## רצף ביצוע

1. **Phase 0** — `research/phase0/`: harness על היסטוריית DropsLab + backfill. שער go/no-go.
2. **Phase 0.5** — אב-טיפוס מסנן הקטליסט (news-vs-no-news) לבד.
3. **Phase 1** — שלד מקצה-לקצה רק אם זוהה יתרון נטו.

## הגדרות שאושרו

| פרמטר | ערך |
|-------|-----|
| יקום | NASDAQ + NYSE |
| סף ירידה | 10% (grid בדיקה: 7/10/15) |
| ספק נתונים | Polygon (intraday) + FMP (fundamentals/news), yfinance/EODHD fallback היסטורי |
| חלון החזקה | נגזר מ-Phase 0 (כל החלונות נמדדים) |
| timezone | Peru, UTC-5, ללא DST |
