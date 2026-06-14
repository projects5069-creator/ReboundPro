# ReboundPro — Project Knowledge Base (placeholder)

*קובץ זה ימולא כ-PK חי במתכונת RidingHigh. כרגע placeholder לשלב השלד.*
*מקור אמת לתכנון: `docs/ReboundPro_BuildSpec_v0.1.md`. מסמך-אב: `~/Downloads/ReboundPro_MasterPlan_2026-06-13_v0.1.md`.*

## מה זה
מערכת מחקר long לתפיסת התאוששות של מניות NASDAQ+NYSE שצנחו ≥10% ביום. סימולציה בלבד. ההפך הסימטרי של RidingHigh Pro.

## עקרונות מחייבים
1. **קודם מודדים, אחר כך בונים** — Phase 0 (יתרון נטו) לפני כל בנייה.
2. **נטו אחרי עלויות תמיד** — commission+spread+slippage מ-`costs.py`, אף פעם לא ברוטו.
3. **הטיה קשיחה לנזילות** — יתרון חייב לשרוד בדלי mid+large.
4. **רזה** — דטרמיניסטי כברירת מחדל; LLM רק לסיווג קטליסט.
5. **point-in-time** — מניעת look-ahead ו-survivorship bias.

## קונבנציות (מיובאות מ-RidingHigh)
- timezone: Peru UTC-5, ללא DST. שעות שוק 08:30–15:00 Peru = 13:30–20:00 UTC.
- מפתחות/סודות ב-`.env` (gitignored) + GitHub Actions secrets. לעולם לא ב-repo.
- Google Sheets רוטציה חודשית; להיזהר מיישור עמודות.
- pandas 2.x: `.map()` לא `.applymap()`.

## סטטוס
שלד. אין קוד לוגי. ראה PROJECT_STATE.md.
