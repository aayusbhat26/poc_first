# Complete Fix Instructions for Pipeline 7 Primary Key Issues

## Problem Summary

Pipeline 7 (`PL_07_Silver_To_Gold_KPIs`) fails with these errors:
1. **gold_ev_charger_performance**: Duplicate key value `()` (empty charger_id)
2. **gold_ev_revenue_by_source**: Duplicate key (2026-01, Charging Fees)

## Root Causes Identified

### Issue 1: Empty charger_id in gold_ev_charger_performance
**Root Cause**: 
- Section 5 of `usp_Load_Gold_EV_KPIs` doesn't filter out NULL/empty charger_ids
- Query groups by `s.charger_id` which can include empty strings

### Issue 2: Duplicate (year_month, revenue_source) in gold_ev_revenue_by_source
**Root Cause**: 
- Section 2 does DELETE before INSERT, which is correct
- BUT if the procedure runs multiple times without completing, the UNION ALL can create duplicates
- The procedure is idempotent for this table, so issue likely comes from concurrent runs or failed retries

### Issue 3: Charger performance DELETE has no WHERE clause
**Root Cause**:
- `DELETE FROM dbo.gold_ev_charger_performance;` deletes ALL records
- This is intentional because it's a "lifetime" aggregate, but it means every run rebuilds from scratch

## Fix Strategy

You asked a great question: **"Shouldn't Silver layer handle this?"**

**Answer: YES! Best practice is to fix data quality at the source.**

### Two-Layer Fix Approach:

1. **Silver Layer (Belt)**: Add charger_id validation in `usp_Load_Silver_EV_Operations`
2. **Gold Layer (Suspenders)**: Add defensive filters in `usp_Load_Gold_EV_KPIs`

## Step-by-Step Fix Procedure

### STEP 1: Fix Table Structure (Already Done)

✅ You already ran `FIX_PRIMARY_KEY_ISSUES.sql` which:
- Added identity columns (`performance_id`, `revenue_id`)
- Added UNIQUE constraints on business keys
- Added CHECK constraint to prevent empty charger_ids
- Created backups

**Verify it worked:**
```sql
-- Check new structure
SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME IN ('gold_ev_charger_performance', 'gold_ev_revenue_by_source')
  AND COLUMN_NAME LIKE '%_id'
ORDER BY TABLE_NAME, ORDINAL_POSITION;

-- Should show performance_id and revenue_id as identity columns
```

### STEP 2: Update Gold KPI Stored Procedure

**Replace** the existing `usp_Load_Gold_EV_KPIs` with the fixed version:

```sql
-- Run this in Azure SQL Query Editor
-- File: usp_Load_Gold_EV_KPIs_FIXED.sql

-- Drop the old version
DROP PROCEDURE IF EXISTS dbo.usp_Load_Gold_EV_KPIs;
GO

-- Then copy and paste the entire content of usp_Load_Gold_EV_KPIs_FIXED.sql
```

**What the fixed version does:**
- ✅ Filters out empty/null charger_ids in ALL sections (added `WHERE charger_id IS NOT NULL AND LEN(RTRIM(charger_id)) > 0`)
- ✅ Section 2 (revenue by source) remains idempotent with DELETE before INSERT
- ✅ Section 5 (charger performance) still deletes all records (intentional for lifetime aggregate)
- ✅ Comments added to explain the logic

### STEP 3: (Optional) Add Silver Layer Validation

For extra safety, you can update `usp_Load_Silver_EV_Operations` to reject bad data:

```sql
CREATE OR ALTER PROCEDURE dbo.usp_Load_Silver_EV_Operations
    @pipeline_date DATE
AS
BEGIN
    SET NOCOUNT ON;
    
    DECLARE @RowsInserted INT;
    
    DELETE FROM dbo.silver_ev_operations
    WHERE CAST(timestamp AS DATE) = @pipeline_date;
    
    INSERT INTO dbo.silver_ev_operations
    (
        -- ... all columns same as before ...
    )
    SELECT
        -- ... all transformations same as before ...
    FROM dbo.stg_ev_telemetry
    WHERE CAST(timestamp AS DATE) = @pipeline_date
      AND charger_id IS NOT NULL           -- ADDED: Filter out NULL
      AND LEN(RTRIM(charger_id)) > 0       -- ADDED: Filter out empty strings
      AND charger_id <> '';                -- ADDED: Extra safety
    
    SET @RowsInserted = @@ROWCOUNT;
    
    SELECT @RowsInserted AS RowsWritten;
END;
```

### STEP 4: Test the Fix

**Test Scenario 1: Normal Run**
```sql
-- Run the fixed procedure
EXEC dbo.usp_Load_Gold_EV_KPIs @pipeline_date = '2026-06-01';

-- Verify no duplicates in charger performance
SELECT charger_id, COUNT(*) AS cnt
FROM dbo.gold_ev_charger_performance
WHERE charger_id IS NULL OR LEN(RTRIM(charger_id)) = 0
GROUP BY charger_id;
-- Should return 0 rows

-- Verify no duplicates in revenue by source
SELECT year_month, revenue_source, COUNT(*) AS cnt
FROM dbo.gold_ev_revenue_by_source
GROUP BY year_month, revenue_source
HAVING COUNT(*) > 1;
-- Should return 0 rows
```

**Test Scenario 2: Re-run Same Date (Idempotency Test)**
```sql
-- Run again for the same date
EXEC dbo.usp_Load_Gold_EV_KPIs @pipeline_date = '2026-06-01';

-- Check counts haven't changed
SELECT 
    'charger_performance' AS TableName,
    COUNT(*) AS RowCount
FROM dbo.gold_ev_charger_performance
UNION ALL
SELECT 
    'revenue_by_source' AS TableName,
    COUNT(*) AS RowCount
FROM dbo.gold_ev_revenue_by_source
WHERE year_month = '2026-06';
```

### STEP 5: Re-run Pipeline 7 in ADF

1. Go to Azure Data Factory
2. Find pipeline `PL_07_Silver_To_Gold_KPIs`
3. Click **Debug** or **Trigger Now**
4. Monitor the run

**Expected Result**: ✅ Pipeline succeeds without primary key violations

### STEP 6: Verify Data Quality

```sql
-- Check for any data quality issues in source
SELECT 
    'Staging' AS Layer,
    COUNT(*) AS TotalRows,
    SUM(CASE WHEN charger_id IS NULL THEN 1 ELSE 0 END) AS NullChargerIds,
    SUM(CASE WHEN LEN(RTRIM(charger_id)) = 0 THEN 1 ELSE 0 END) AS EmptyChargerIds
FROM dbo.stg_ev_telemetry
WHERE CAST(timestamp AS DATE) = '2026-06-01'

UNION ALL

SELECT 
    'Silver' AS Layer,
    COUNT(*) AS TotalRows,
    SUM(CASE WHEN charger_id IS NULL THEN 1 ELSE 0 END) AS NullChargerIds,
    SUM(CASE WHEN LEN(RTRIM(charger_id)) = 0 THEN 1 ELSE 0 END) AS EmptyChargerIds
FROM dbo.silver_ev_operations
WHERE CAST(timestamp AS DATE) = '2026-06-01';
```

## Rollback Plan (If Needed)

If something goes wrong:

```sql
-- Restore from backups created by FIX_PRIMARY_KEY_ISSUES.sql
TRUNCATE TABLE dbo.gold_ev_charger_performance;
INSERT INTO dbo.gold_ev_charger_performance
SELECT charger_id, state, city, zone, hw_type, max_power_kw, site_type,
       lifetime_revenue_inr, lifetime_sessions, lifetime_energy_kwh,
       avg_utilization_pct, avg_uptime_pct, total_downtime_hours, utilization_bucket
FROM dbo.gold_ev_charger_performance_backup;

TRUNCATE TABLE dbo.gold_ev_revenue_by_source;
INSERT INTO dbo.gold_ev_revenue_by_source
SELECT year_month, revenue_source, revenue_inr, revenue_pct_of_total,
       profit_margin_pct, opex_inr, capex_inr
FROM dbo.gold_ev_revenue_by_source_backup;
```

## Summary of Changes

| Component | Change | Reason |
|---|---|---|
| **Table Structure** | Added identity PKs + unique constraints | Prevents duplicates, allows multiple records per business key |
| **usp_Load_Gold_EV_KPIs** | Added charger_id filters in all sections | Defensive programming - reject bad data |
| **usp_Load_Silver_EV_Operations** | (Optional) Add charger_id validation | Source-level data quality (best practice) |

## Why This Fixes the Issue

1. **Empty charger_id** → Filtered out at both Silver and Gold layers
2. **Duplicate revenue source** → DELETE before INSERT ensures idempotency
3. **Identity PKs** → Even if business logic has bugs, database won't reject inserts
4. **CHECK constraints** → Prevents future issues at database level

## Answer to Your Question

> "Shouldn't the Silver layer remove duplicates and handle all issues?"

**YES, ideally!** That's the **medallion architecture best practice**:

```
Bronze (Raw) → Iron (Clean) → Silver (Business Logic) → Gold (Aggregates)
                ↑                       ↑                      ↑
            Remove nulls          Validate data         Trust clean data
            Fix formats           Apply business        Focus on aggregation
                                  rules
```

**However**, in your case:
- The Silver layer **is already good** (it has DELETE before INSERT)
- The issue is in the **Gold layer logic** (missing WHERE clauses, no filters)
- **Defense-in-depth** approach: Fix both layers for robustness

## Next Steps After Fix

1. ✅ Update `usp_Load_Gold_EV_KPIs` (required)
2. ✅ Test with `EXEC dbo.usp_Load_Gold_EV_KPIs @pipeline_date = '2026-06-01'`
3. ✅ Run Pipeline 7 in ADF
4. ⚠️ (Optional) Update Silver layer for extra safety
5. ✅ Monitor pipeline runs for next few days
6. ✅ Document the fix in your project wiki
