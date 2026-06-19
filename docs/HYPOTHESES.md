# ReboundPro — Hypotheses Register

ממשל-מחקר ל-ReboundPro. כל השערה: pre-registration לפני forward, hold-out, in-sample נשרף.

| ID | שם | סטטוס | verdict | מסמך |
|----|----|-------|---------|------|
| HYP-002 | long mean-reversion (oversold-bounce) + VIX regime-gate | DRAFT (in-sample, טרם-forward) | Refine | [HYP-002](HYP-002_long_rebound_thesis.md) |

> *HYP-002 = פריור ספקני. TASK-C.1 (DropsLab∩floor n=591): אין edge נטו יציב בנזיל (long→D5 net +0.27%, CI95 [−2.94,+2.22] כולל 0; לא מנצח SPY). מנגנון משחזר כיוונית (VIX<18 שלילי-מובהק) אך VIX≥20 under-powered. הכרעה=M4 על דאטת-RB-קדימה (§5). מזכר: research/phase0/TASK-C1_liquid_edge_memo.md.*

## עקרונות (§A)
- in-sample נשרף ל-discovery; validation = **forward-only אחרי-רישום**.
- כל מדד נכנס ל-scoring רק עם **קורלציה-מוכחת + שורד OOS/falsification**.
- **net-after-cost בלבד**; liquidity-bucket go/no-go (mid+large).
