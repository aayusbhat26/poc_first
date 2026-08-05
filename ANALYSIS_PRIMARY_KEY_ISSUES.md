# Primary Key Analysis - Gold Tables

## Issue Summary

You're getting these errors:
1. **gold_ev_charger_performance**: `Cannot insert duplicate key... The duplicate key value is ()`
2. **gold_ev_revenue_by_source**: `Cannot insert duplicate key... The duplicate key value is (2026-01, Charging Fees)`

## Root Cause Analysis

### 1. gold_ev_charger_performance
**Current Primary Key**: `charger_id` (VARCHAR(50) NOT NULL)

**Problem**: 
- The error shows duplicate key value is `()` which means **charger_id is empty string or NULL**
- Even though the column is marked NOT NULL, empty strings `''` are allowed
- The stored procedure `usp_Load_Gold_EV_KPIs` is inserting rows where `charger_id` is blank

**Data Issues**:
- Multiple records with `charger_id = ''` are being inserted
- This is a **data quality issue** - charger_id should never be blank

### 2. gold_ev_revenue_by_source
**Current Primary Key**: `(year_month, revenue_source)` - composite key
- `year_month` VARCHAR(7) NOT NULL  (format: YYYY-MM like "2026-01")
- `revenue_source` VARCHAR(50) NOT NULL (like "Charging Fees")

**Problem**:
- The stored procedure is trying to insert the same combination `('2026-01', 'Charging Fees')` multiple times
- This suggests the stored procedure:
  - Doesn't have a DELETE before INSERT (not idempotent)
  - OR is aggregating data incorrectly causing duplicate groups
  - OR is being called multiple times in the same pipeline run

## All Gold Tables Primary Keys

| Table Name | Primary Key Columns | PK Type |
|---|---|---|
| gold_dim_date | date_key | Single column |
| gold_ev_charger_30day_trend | charger_id, data_date | Composite |
| gold_ev_charger_exception_profile | profile_id (IDENTITY), data_date, charger_id | Composite with IDENTITY |
| **gold_ev_charger_performance** | **charger_id** | **Single column** ⚠️ |
| gold_ev_daily_summary | data_date, state, city | Composite |
| gold_ev_exception_summary | summary_id (IDENTITY), data_date, exception_category, exception_type, exception_severity | Composite with IDENTITY |
| gold_ev_exceptions | No PK defined | None ⚠️ |
| gold_ev_fault_timeline | fault_id (IDENTITY), data_date, charger_id, fault_timestamp | Composite with IDENTITY |
| gold_ev_hourly_diagnostics | charger_id, data_date, hour_of_day | Composite |
| gold_ev_packet_drop_gaps | gap_id (IDENTITY), data_date, charger_id, expected_timestamp | Composite with IDENTITY |
| **gold_ev_revenue_by_source** | **year_month, revenue_source** | **Composite** ⚠️ |

## Recommended Solutions

### Option 1: Add Identity Column (Recommended)
**Best for**: Tables that need historical tracking or multiple snapshots per day

**gold_ev_charger_performance**:
```sql
ALTER TABLE dbo.gold_ev_charger_performance
ADD performance_id INT IDENTITY(1,1) NOT NULL;

-- Drop existing PK
ALTER TABLE dbo.gold_ev_charger_performance
DROP CONSTRAINT PK__gold_ev__DD57BD459FBB7F2E;

-- Add new composite PK with identity
ALTER TABLE dbo.gold_ev_charger_performance
ADD CONSTRAINT PK_gold_ev_charger_performance 
PRIMARY KEY (performance_id);

-- Add unique constraint on charger_id to prevent duplicates
ALTER TABLE dbo.gold_ev_charger_performance
ADD CONSTRAINT UQ_gold_ev_charger_performance_charger_id 
UNIQUE (charger_id);

-- Add constraint to prevent empty charger_id
ALTER TABLE dbo.gold_ev_charger_performance
ADD CONSTRAINT CHK_charger_performance_charger_id_not_empty 
CHECK (LEN(RTRIM(charger_id)) > 0);
```

**gold_ev_revenue_by_source**:
```sql
ALTER TABLE dbo.gold_ev_revenue_by_source
ADD revenue_id INT IDENTITY(1,1) NOT NULL;

-- Drop existing PK
ALTER TABLE dbo.gold_ev_revenue_by_source
DROP CONSTRAINT PK__gold_ev__B317D7E316EFB806;

-- Add new PK with identity
ALTER TABLE dbo.gold_ev_revenue_by_source
ADD CONSTRAINT PK_gold_ev_revenue_by_source 
PRIMARY KEY (revenue_id);

-- Add unique constraint on the business key
ALTER TABLE dbo.gold_ev_revenue_by_source
ADD CONSTRAINT UQ_gold_ev_revenue_by_source_business_key 
UNIQUE (year_month, revenue_source);
```

### Option 2: Fix the Stored Procedure (Complementary)
The stored procedure `usp_Load_Gold_EV_KPIs` needs to:

1. **Delete existing records BEFORE insert** (make it idempotent):
```sql
-- At the start of the procedure
DELETE FROM dbo.gold_ev_charger_performance;  -- or WHERE condition
DELETE FROM dbo.gold_ev_revenue_by_source WHERE year_month = @year_month_param;
```

2. **Add data quality checks**:
```sql
-- Filter out bad data
WHERE charger_id IS NOT NULL 
  AND LEN(RTRIM(charger_id)) > 0
  AND charger_id <> ''
```

3. **Use MERGE instead of INSERT** for upsert logic:
```sql
MERGE gold_ev_revenue_by_source AS target
USING (SELECT ...) AS source
ON target.year_month = source.year_month 
   AND target.revenue_source = source.revenue_source
WHEN MATCHED THEN UPDATE SET ...
WHEN NOT MATCHED THEN INSERT ...;
```

## Next Steps

1. **Extract the stored procedure** `usp_Load_Gold_EV_KPIs` to see its current logic
2. **Check for empty charger_ids** in source data (silver_ev_operations)
3. **Apply Option 1** to add identity columns and constraints
4. **Update the stored procedure** to be idempotent and filter bad data
5. **Re-run the pipeline** to verify the fix

## SQL to Run Next

Run this to get the stored procedure code:
```sql
SELECT OBJECT_DEFINITION(OBJECT_ID('dbo.usp_Load_Gold_EV_KPIs')) AS StoredProcedureCode;
```

Run this to check for bad data:
```sql
-- Check for empty/null charger_ids in source
SELECT COUNT(*) AS EmptyChargerIds
FROM dbo.silver_ev_operations
WHERE charger_id IS NULL OR LEN(RTRIM(charger_id)) = 0 OR charger_id = '';

-- Check for duplicate revenue combinations
SELECT year_month, revenue_source, COUNT(*) AS DuplicateCount
FROM (
    -- This is a placeholder - we need to see the actual query from the stored procedure
    SELECT 
        FORMAT(timestamp, 'yyyy-MM') AS year_month,
        'Charging Fees' AS revenue_source  -- example
    FROM dbo.silver_ev_operations
) AS subquery
GROUP BY year_month, revenue_source
HAVING COUNT(*) > 1;
```
