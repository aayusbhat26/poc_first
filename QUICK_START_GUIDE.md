# Quick Start Guide - Fix Pipeline 7 Primary Key Issues

## What You Have

✅ **5 files created in your workspace:**

1. **`FIX_PRIMARY_KEY_ISSUES.sql`** - Table structure fixes (ALREADY RUN ✅)
2. **`usp_Load_Silver_EV_Operations_FIXED.sql`** - Fixed Silver layer procedure
3. **`usp_Load_Gold_EV_KPIs_FIXED.sql`** - Fixed Gold KPI layer procedure
4. **`RUN_ALL_FIXES.sql`** - Complete test script
5. **`STEP_BY_STEP_FIX_GUIDE.md`** - Detailed instructions

## 5-Minute Fix (Do This Now)

### Step 1: Open Azure SQL Query Editor
1. Go to Azure Portal → Your SQL Database
2. Click **Query editor** in the left menu
3. Sign in

### Step 2: Run RUN_ALL_FIXES.sql
1. Open file: `RUN_ALL_FIXES.sql`
2. Copy the entire content
3. Paste into Azure SQL Query Editor
4. Click **Run** (or press F5)
5. Wait for: `STEP 3: Create Fixed Stored Procedures`

### Step 3: Paste Fixed Stored Procedures

**When you see the message:**
```
STEP 3: Create Fixed Stored Procedures
Now copy and paste the content of these files in order:
1. usp_Load_Silver_EV_Operations_FIXED.sql
2. usp_Load_Gold_EV_KPIs_FIXED.sql
```

**Do this:**

1. **Open** `usp_Load_Silver_EV_Operations_FIXED.sql`
2. **Copy** the entire content
3. **Paste** into a NEW query window in Azure SQL Query Editor
4. **Run** it
5. Wait for: `Commands completed successfully`

6. **Open** `usp_Load_Gold_EV_KPIs_FIXED.sql`
7. **Copy** the entire content
8. **Paste** into a NEW query window
9. **Run** it
10. Wait for: `Commands completed successfully`

### Step 4: Continue RUN_ALL_FIXES.sql
1. Go back to the `RUN_ALL_FIXES.sql` query window
2. Click **Run** again (or F5)
3. Watch the test results

### Step 5: Verify Success
Look for these messages:
```
✅ usp_Load_Silver_EV_Operations created successfully
✅ usp_Load_Gold_EV_KPIs created successfully
✅ Idempotency test PASSED - counts remained the same
```

### Step 6: Test Pipeline in ADF
1. Go to **Azure Data Factory**
2. Find pipeline: **`PL_07_Silver_To_Gold_KPIs`**
3. Click **Debug** or **Trigger Now**
4. Set parameter: `pipeline_date = 2026-06-02`
5. Click **OK**
6. Monitor → Should show **✅ Succeeded**

---

## What Each File Does

| File | What It Fixes | Status |
|---|---|---|
| `FIX_PRIMARY_KEY_ISSUES.sql` | Adds identity PKs, unique constraints, CHECK constraints | Already run ✅ |
| `usp_Load_Silver_EV_Operations_FIXED.sql` | Filters out empty charger_ids at source (Silver layer) | Run in Step 3 |
| `usp_Load_Gold_EV_KPIs_FIXED.sql` | Adds defensive filters, fixes section 5 DELETE | Run in Step 3 |
| `RUN_ALL_FIXES.sql` | Tests everything automatically | Run in Step 2 & 4 |

---

## Quick Troubleshooting

### ❌ "Procedure not found" Error
**Fix**: Make sure you pasted the stored procedure files in Step 3

### ❌ "Primary key violation" Still Happening
**Fix**: Run this to check if identity columns exist:
```sql
SELECT COLUMN_NAME, IS_NULLABLE, COLUMN_DEFAULT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME IN ('gold_ev_charger_performance', 'gold_ev_revenue_by_source')
  AND COLUMN_NAME LIKE '%_id';
```
Should show `performance_id` and `revenue_id` with IDENTITY

### ❌ "Bad data still in Silver"
**Fix**: Run this to check:
```sql
SELECT COUNT(*) AS BadRows
FROM dbo.silver_ev_operations
WHERE charger_id IS NULL OR LEN(RTRIM(charger_id)) = 0;
```
Should return 0

### ❌ "Pipeline still fails in ADF"
**Check**:
1. Does pipeline parameter `pipeline_date` have a value?
2. Is linked service `LS_AzureSQL` connected?
3. Does the stored procedure have correct permissions?

Run this in SQL to check permissions:
```sql
-- Check stored procedure exists
SELECT name, type_desc 
FROM sys.objects 
WHERE type = 'P' 
  AND name LIKE 'usp_Load_Gold_EV_KPIs';
```

---

## What the Fix Does

### Before Fix:
```
Staging → Silver → Gold (FAILS with duplicate key errors)
                    ↑
                    |- Empty charger_ids get through
                    |- No filters in queries
                    |- Primary key rejects duplicates
```

### After Fix:
```
Staging → Silver (FILTERS bad data) → Gold (DEFENSIVE filters) → ✅ Success
           ↑                            ↑
           |- Rejects empty             |- Double-checks charger_ids
              charger_ids               |- Identity PKs allow flexibility
```

---

## Expected Results

### Silver Layer Test:
```
TotalRows: 432,000
NullChargerIds: 0      ← Should be 0
EmptyChargerIds: 0     ← Should be 0
BlankChargerIds: 0     ← Should be 0
```

### Gold KPI Tables Test:
```
gold_ev_daily_summary: 30 rows (per state/city)
gold_ev_revenue_by_source: 4 rows (4 revenue sources)
gold_ev_hourly_diagnostics: 9,000 rows (375 chargers × 24 hours)
gold_ev_charger_30day_trend: 375 rows (one per charger per day)
gold_ev_charger_performance: 375 rows (lifetime per charger)
```

### Duplicate Check:
```
Duplicates in gold_ev_charger_performance: 0 rows ← Should be 0
Duplicates in gold_ev_revenue_by_source: 0 rows   ← Should be 0
```

---

## Timeline

| Step | Time | Action |
|---|---|---|
| 1 | 1 min | Open Azure SQL Query Editor |
| 2 | 1 min | Run RUN_ALL_FIXES.sql (first part) |
| 3 | 2 min | Paste two stored procedure files |
| 4 | 2 min | Run RUN_ALL_FIXES.sql (tests) |
| 5 | 2 min | Test pipeline in ADF |
| **Total** | **8 min** | Complete fix and verification |

---

## Need Help?

### Check the detailed guide:
📄 **`STEP_BY_STEP_FIX_GUIDE.md`** - Full explanations

### Check the analysis:
📄 **`ANALYSIS_PRIMARY_KEY_ISSUES.md`** - Why the issues happened

### Check the instructions:
📄 **`COMPLETE_FIX_INSTRUCTIONS.md`** - All fix details

---

## Success Criteria

✅ **RUN_ALL_FIXES.sql** shows all green checkmarks  
✅ **Silver layer** has 0 bad charger_ids  
✅ **Gold tables** have 0 duplicates  
✅ **Re-run test** shows same counts (idempotent)  
✅ **ADF Pipeline 7** succeeds  

---

## What's Next?

After Pipeline 7 succeeds:

1. ✅ Run your full pipeline sequence (PL_01 → PL_02 → PL_05 → PL_07)
2. ✅ Monitor for a few days to ensure stability
3. ✅ Document the fix in your project wiki
4. ✅ Consider adding data quality alerts for future issues

---

## Summary

**You're fixing 3 things:**
1. **Table structure** - Added identity PKs (already done ✅)
2. **Silver layer** - Filter bad data at source
3. **Gold layer** - Defensive queries + proper deletes

**Total time**: ~8 minutes  
**Files to run**: 3 SQL scripts  
**Expected result**: Pipeline 7 succeeds ✅  

**Ready? Start with Step 1!**
