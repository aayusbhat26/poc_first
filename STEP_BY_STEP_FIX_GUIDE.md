# Complete Step-by-Step Guide to Fix All Stored Procedures

## Overview

We'll fix all three stored procedures to ensure clean data flow:
1. **usp_Load_Silver_EV_Operations** - Staging → Silver (add data quality filters)
2. **usp_Load_Gold_EV_KPIs** - Silver → Gold KPI tables (fix primary key issues)
3. **usp_Load_Gold_EV_Exceptions** - Silver → Gold Exception tables (ensure idempotency)

## Architecture Flow

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────────────┐
│  Staging    │────▶│  Silver Layer    │────▶│   Gold Layer            │
│  (Raw Data) │     │  (Clean Data)    │     │   (Aggregated Data)     │
└─────────────┘     └──────────────────┘     └─────────────────────────┘
                           │                            │
                           │                            │
                    usp_Load_Silver_         usp_Load_Gold_EV_KPIs
                    EV_Operations            usp_Load_Gold_EV_Exceptions
```

## Pre-Requisites (Already Done)

✅ You already ran `FIX_PRIMARY_KEY_ISSUES.sql` which:
- Added identity columns to gold_ev_charger_performance and gold_ev_revenue_by_source
- Added unique constraints on business keys
- Created backups

---

## STEP 1: Fix Silver Layer Stored Procedure

### What We're Fixing:
- Add data quality filters to reject NULL/empty charger_ids at the source
- Ensure idempotent deletes before inserts

### Action:
Open Azure SQL Query Editor and run this:

```sql
-- File: usp_Load_Silver_EV_Operations_FIXED.sql
-- This will be provided in the next file
```

**Status**: File will be created separately (see usp_Load_Silver_EV_Operations_FIXED.sql)

---

## STEP 2: Fix Gold KPI Stored Procedure

### What We're Fixing:
- Section 5 (charger_performance): Add charger_id filters
- All sections: Add defensive WHERE clauses
- Section 2 (revenue_by_source): Already idempotent, no changes needed

### Action:
```sql
-- Drop the old version
DROP PROCEDURE IF EXISTS dbo.usp_Load_Gold_EV_KPIs;
GO

-- Run the fixed version from usp_Load_Gold_EV_KPIs_FIXED.sql
-- (Already created in your workspace)
```

**Status**: ✅ Already created (usp_Load_Gold_EV_KPIs_FIXED.sql)

---

## STEP 3: Verify Gold Exceptions Stored Procedure

### What to Check:
The `usp_Load_Gold_EV_Exceptions` procedure looks good, but let's verify:

```sql
-- Check if it has DELETE before INSERT for all 5 tables
-- (It does - we reviewed the code earlier)
```

**Status**: ✅ No changes needed (already idempotent)

---

## STEP 4: Test Each Stored Procedure

### Test 1: Silver Layer
```sql
-- Test the silver load
EXEC dbo.usp_Load_Silver_EV_Operations @pipeline_date = '2026-06-01';

-- Verify no bad data made it through
SELECT 
    COUNT(*) AS TotalRows,
    SUM(CASE WHEN charger_id IS NULL THEN 1 ELSE 0 END) AS NullChargerIds,
    SUM(CASE WHEN LEN(RTRIM(charger_id)) = 0 THEN 1 ELSE 0 END) AS EmptyChargerIds
FROM dbo.silver_ev_operations
WHERE CAST(timestamp AS DATE) = '2026-06-01';
-- Should show 0 for NullChargerIds and EmptyChargerIds
```

### Test 2: Gold KPI Layer
```sql
-- Test the gold KPI load
EXEC dbo.usp_Load_Gold_EV_KPIs @pipeline_date = '2026-06-01';

-- Check for duplicates in charger_performance
SELECT charger_id, COUNT(*) AS cnt
FROM dbo.gold_ev_charger_performance
GROUP BY charger_id
HAVING COUNT(*) > 1;
-- Should return 0 rows

-- Check for duplicates in revenue_by_source
SELECT year_month, revenue_source, COUNT(*) AS cnt
FROM dbo.gold_ev_revenue_by_source
GROUP BY year_month, revenue_source
HAVING COUNT(*) > 1;
-- Should return 0 rows
```

### Test 3: Gold Exceptions Layer
```sql
-- Test the gold exceptions load
EXEC dbo.usp_Load_Gold_EV_Exceptions @pipeline_date = '2026-06-01';

-- Verify all 5 tables were populated
SELECT 
    'gold_ev_exceptions' AS TableName, 
    COUNT(*) AS RowCount 
FROM dbo.gold_ev_exceptions 
WHERE CAST(timestamp AS DATE) = '2026-06-01'
UNION ALL
SELECT 'gold_ev_fault_timeline', COUNT(*) 
FROM dbo.gold_ev_fault_timeline 
WHERE data_date = '2026-06-01'
UNION ALL
SELECT 'gold_ev_packet_drop_gaps', COUNT(*) 
FROM dbo.gold_ev_packet_drop_gaps 
WHERE data_date = '2026-06-01'
UNION ALL
SELECT 'gold_ev_exception_summary', COUNT(*) 
FROM dbo.gold_ev_exception_summary 
WHERE data_date = '2026-06-01'
UNION ALL
SELECT 'gold_ev_charger_exception_profile', COUNT(*) 
FROM dbo.gold_ev_charger_exception_profile 
WHERE data_date = '2026-06-01';
```

---

## STEP 5: Update Azure Data Factory Pipelines

### Pipeline 5: PL_05_Staging_To_Silver
**Status**: ✅ Already correct (uses usp_Load_Silver_EV_Operations)

### Pipeline 7: PL_07_Silver_To_Gold_KPIs
**Update Required**: Make sure it calls the fixed stored procedure

1. Open ADF pipeline `PL_07_Silver_To_Gold_KPIs`
2. Find activity `SP_Load_Gold_KPIs`
3. Verify it points to `[dbo].[usp_Load_Gold_EV_KPIs]` ✅
4. No changes needed (stored procedure name is the same)

### Pipeline 6 (if exists): Gold Exceptions Pipeline
**Status**: ✅ Already correct (uses usp_Load_Gold_EV_Exceptions)

---

## STEP 6: End-to-End Test

Run the full pipeline sequence:

```sql
-- 1. Load Silver
EXEC dbo.usp_Load_Silver_EV_Operations @pipeline_date = '2026-06-02';

-- 2. Load Gold KPIs
EXEC dbo.usp_Load_Gold_EV_KPIs @pipeline_date = '2026-06-02';

-- 3. Load Gold Exceptions
EXEC dbo.usp_Load_Gold_EV_Exceptions @pipeline_date = '2026-06-02';

-- 4. Verify all gold tables
SELECT 
    'gold_ev_daily_summary' AS TableName, 
    COUNT(*) AS RowCount 
FROM dbo.gold_ev_daily_summary 
WHERE data_date = '2026-06-02'
UNION ALL
SELECT 'gold_ev_revenue_by_source', COUNT(*) 
FROM dbo.gold_ev_revenue_by_source 
WHERE year_month = '2026-06'
UNION ALL
SELECT 'gold_ev_hourly_diagnostics', COUNT(*) 
FROM dbo.gold_ev_hourly_diagnostics 
WHERE data_date = '2026-06-02'
UNION ALL
SELECT 'gold_ev_charger_30day_trend', COUNT(*) 
FROM dbo.gold_ev_charger_30day_trend 
WHERE data_date = '2026-06-02'
UNION ALL
SELECT 'gold_ev_charger_performance', COUNT(*) 
FROM dbo.gold_ev_charger_performance;
```

---

## STEP 7: Run Pipelines in Azure Data Factory

### Test Order:
1. **PL_05_Staging_To_Silver** → Loads silver_ev_operations
2. **PL_07_Silver_To_Gold_KPIs** → Loads 5 gold KPI tables
3. **PL_06_Silver_To_Gold_Exceptions** (if exists) → Loads 5 gold exception tables

### How to Run:
1. Go to Azure Data Factory
2. Click on each pipeline
3. Click **Debug** or **Trigger Now**
4. Use date: `2026-06-02` (or any recent date with data)
5. Monitor for success ✅

---

## Troubleshooting

### If Pipeline 7 Still Fails:

**Check 1: Did you update the stored procedure?**
```sql
-- Verify the procedure has the filters
SELECT OBJECT_DEFINITION(OBJECT_ID('dbo.usp_Load_Gold_EV_KPIs'));
-- Search for: "AND LEN(RTRIM(charger_id)) > 0"
-- Should appear 4 times (in sections 2, 3, 4, and 5)
```

**Check 2: Are there still empty charger_ids in silver?**
```sql
SELECT COUNT(*) AS BadRows
FROM dbo.silver_ev_operations
WHERE charger_id IS NULL 
   OR LEN(RTRIM(charger_id)) = 0
   OR charger_id = '';
-- Should return 0
```

**Check 3: Did the table structure update succeed?**
```sql
-- Check for identity columns
SELECT COLUMN_NAME, IS_NULLABLE, COLUMN_DEFAULT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = 'gold_ev_charger_performance'
  AND COLUMN_NAME = 'performance_id';
-- Should show identity column

SELECT COLUMN_NAME, IS_NULLABLE, COLUMN_DEFAULT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = 'gold_ev_revenue_by_source'
  AND COLUMN_NAME = 'revenue_id';
-- Should show identity column
```

---

## Summary Checklist

- [ ] **STEP 1**: Run `usp_Load_Silver_EV_Operations_FIXED.sql` in Azure SQL
- [ ] **STEP 2**: Run `usp_Load_Gold_EV_KPIs_FIXED.sql` in Azure SQL (already created)
- [ ] **STEP 3**: Verify `usp_Load_Gold_EV_Exceptions` (no changes needed)
- [ ] **STEP 4**: Test each stored procedure individually with SQL
- [ ] **STEP 5**: Verify ADF pipelines point to correct stored procedures
- [ ] **STEP 6**: Run end-to-end SQL test
- [ ] **STEP 7**: Trigger pipelines in ADF and verify success
- [ ] **STEP 8**: Monitor next few pipeline runs

---

## Files You Need

1. ✅ `FIX_PRIMARY_KEY_ISSUES.sql` (already run)
2. ✅ `usp_Load_Gold_EV_KPIs_FIXED.sql` (already created)
3. ⏳ `usp_Load_Silver_EV_Operations_FIXED.sql` (creating next)
4. ✅ `COMPLETE_FIX_INSTRUCTIONS.md` (already created)
5. ✅ `ANALYSIS_PRIMARY_KEY_ISSUES.md` (already created)

---

## Next Steps

1. I'll create the fixed Silver layer stored procedure
2. You run all the fixes in order
3. Test and verify
4. Run your pipelines!

Let me create the Silver layer fix now...
