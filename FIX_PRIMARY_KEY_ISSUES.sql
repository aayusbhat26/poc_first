-- =====================================================
-- FIX PRIMARY KEY ISSUES - Gold Tables
-- Tables: gold_ev_charger_performance, gold_ev_revenue_by_source
-- =====================================================
-- IMPORTANT: Backup your data before running this script!
-- Run this in Azure SQL Query Editor
-- =====================================================

-- =====================================================
-- STEP 1: Extract stored procedure for review
-- =====================================================
SELECT OBJECT_DEFINITION(OBJECT_ID('dbo.usp_Load_Gold_EV_KPIs')) AS StoredProcedureCode;

-- =====================================================
-- STEP 2: Check for bad data in source tables
-- =====================================================

PRINT '--- Checking for empty charger_ids in silver_ev_operations ---';
SELECT 
    COUNT(*) AS TotalRows,
    SUM(CASE WHEN charger_id IS NULL THEN 1 ELSE 0 END) AS NullChargerIds,
    SUM(CASE WHEN LEN(RTRIM(charger_id)) = 0 THEN 1 ELSE 0 END) AS EmptyStringChargerIds,
    SUM(CASE WHEN charger_id = '' THEN 1 ELSE 0 END) AS BlankChargerIds
FROM dbo.silver_ev_operations;

PRINT '--- Checking current duplicates in gold_ev_charger_performance ---';
SELECT 
    charger_id,
    COUNT(*) AS DuplicateCount
FROM dbo.gold_ev_charger_performance
GROUP BY charger_id
HAVING COUNT(*) > 1;

PRINT '--- Checking current duplicates in gold_ev_revenue_by_source ---';
SELECT 
    year_month,
    revenue_source,
    COUNT(*) AS DuplicateCount
FROM dbo.gold_ev_revenue_by_source
GROUP BY year_month, revenue_source
HAVING COUNT(*) > 1;

-- =====================================================
-- STEP 3: FIX gold_ev_charger_performance
-- =====================================================

PRINT '--- Fixing gold_ev_charger_performance ---';

-- 3.1: Backup existing data
IF OBJECT_ID('dbo.gold_ev_charger_performance_backup', 'U') IS NOT NULL
    DROP TABLE dbo.gold_ev_charger_performance_backup;

SELECT * 
INTO dbo.gold_ev_charger_performance_backup
FROM dbo.gold_ev_charger_performance;

PRINT 'Backup created: gold_ev_charger_performance_backup';

-- 3.2: Check current primary key name
DECLARE @PKName_Performance NVARCHAR(255);
SELECT @PKName_Performance = name
FROM sys.key_constraints
WHERE type = 'PK' 
  AND parent_object_id = OBJECT_ID('dbo.gold_ev_charger_performance');

PRINT 'Current PK Name: ' + ISNULL(@PKName_Performance, 'No PK found');

-- 3.3: Remove duplicate and bad data
DELETE FROM dbo.gold_ev_charger_performance
WHERE charger_id IS NULL 
   OR LEN(RTRIM(charger_id)) = 0 
   OR charger_id = '';

PRINT 'Deleted rows with empty/null charger_id';

-- Keep only the first occurrence of each charger_id
;WITH CTE_Duplicates AS (
    SELECT 
        charger_id,
        ROW_NUMBER() OVER (PARTITION BY charger_id ORDER BY lifetime_revenue_inr DESC) AS RowNum
    FROM dbo.gold_ev_charger_performance
)
DELETE FROM CTE_Duplicates WHERE RowNum > 1;

PRINT 'Removed duplicate charger_ids (kept highest revenue record)';

-- 3.4: Drop existing primary key
IF @PKName_Performance IS NOT NULL
BEGIN
    DECLARE @DropPK_Performance NVARCHAR(500);
    SET @DropPK_Performance = 'ALTER TABLE dbo.gold_ev_charger_performance DROP CONSTRAINT ' + @PKName_Performance;
    EXEC sp_executesql @DropPK_Performance;
    PRINT 'Dropped existing PK: ' + @PKName_Performance;
END;

-- 3.5: Add identity column
IF NOT EXISTS (
    SELECT 1 FROM sys.columns 
    WHERE object_id = OBJECT_ID('dbo.gold_ev_charger_performance') 
      AND name = 'performance_id'
)
BEGIN
    ALTER TABLE dbo.gold_ev_charger_performance
    ADD performance_id INT IDENTITY(1,1) NOT NULL;
    PRINT 'Added performance_id IDENTITY column';
END;

-- 3.6: Add new primary key on identity column
ALTER TABLE dbo.gold_ev_charger_performance
ADD CONSTRAINT PK_gold_ev_charger_performance 
PRIMARY KEY CLUSTERED (performance_id);

PRINT 'Added new PK on performance_id';

-- 3.7: Add unique constraint on charger_id
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes 
    WHERE object_id = OBJECT_ID('dbo.gold_ev_charger_performance') 
      AND name = 'UQ_gold_ev_charger_performance_charger_id'
)
BEGIN
    ALTER TABLE dbo.gold_ev_charger_performance
    ADD CONSTRAINT UQ_gold_ev_charger_performance_charger_id 
    UNIQUE NONCLUSTERED (charger_id);
    PRINT 'Added UNIQUE constraint on charger_id';
END;

-- 3.8: Add check constraint to prevent empty charger_id
IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints 
    WHERE object_id = OBJECT_ID('dbo.CHK_charger_performance_charger_id_not_empty')
)
BEGIN
    ALTER TABLE dbo.gold_ev_charger_performance
    ADD CONSTRAINT CHK_charger_performance_charger_id_not_empty 
    CHECK (LEN(RTRIM(charger_id)) > 0);
    PRINT 'Added CHECK constraint to prevent empty charger_id';
END;

-- =====================================================
-- STEP 4: FIX gold_ev_revenue_by_source
-- =====================================================

PRINT '--- Fixing gold_ev_revenue_by_source ---';

-- 4.1: Backup existing data
IF OBJECT_ID('dbo.gold_ev_revenue_by_source_backup', 'U') IS NOT NULL
    DROP TABLE dbo.gold_ev_revenue_by_source_backup;

SELECT * 
INTO dbo.gold_ev_revenue_by_source_backup
FROM dbo.gold_ev_revenue_by_source;

PRINT 'Backup created: gold_ev_revenue_by_source_backup';

-- 4.2: Check current primary key name
DECLARE @PKName_Revenue NVARCHAR(255);
SELECT @PKName_Revenue = name
FROM sys.key_constraints
WHERE type = 'PK' 
  AND parent_object_id = OBJECT_ID('dbo.gold_ev_revenue_by_source');

PRINT 'Current PK Name: ' + ISNULL(@PKName_Revenue, 'No PK found');

-- 4.3: Remove duplicates (keep highest revenue)
;WITH CTE_RevenueDuplicates AS (
    SELECT 
        year_month,
        revenue_source,
        revenue_inr,
        ROW_NUMBER() OVER (
            PARTITION BY year_month, revenue_source 
            ORDER BY revenue_inr DESC
        ) AS RowNum
    FROM dbo.gold_ev_revenue_by_source
)
DELETE FROM CTE_RevenueDuplicates WHERE RowNum > 1;

PRINT 'Removed duplicate (year_month, revenue_source) combinations';

-- 4.4: Drop existing primary key
IF @PKName_Revenue IS NOT NULL
BEGIN
    DECLARE @DropPK_Revenue NVARCHAR(500);
    SET @DropPK_Revenue = 'ALTER TABLE dbo.gold_ev_revenue_by_source DROP CONSTRAINT ' + @PKName_Revenue;
    EXEC sp_executesql @DropPK_Revenue;
    PRINT 'Dropped existing PK: ' + @PKName_Revenue;
END;

-- 4.5: Add identity column
IF NOT EXISTS (
    SELECT 1 FROM sys.columns 
    WHERE object_id = OBJECT_ID('dbo.gold_ev_revenue_by_source') 
      AND name = 'revenue_id'
)
BEGIN
    ALTER TABLE dbo.gold_ev_revenue_by_source
    ADD revenue_id INT IDENTITY(1,1) NOT NULL;
    PRINT 'Added revenue_id IDENTITY column';
END;

-- 4.6: Add new primary key on identity column
ALTER TABLE dbo.gold_ev_revenue_by_source
ADD CONSTRAINT PK_gold_ev_revenue_by_source 
PRIMARY KEY CLUSTERED (revenue_id);

PRINT 'Added new PK on revenue_id';

-- 4.7: Add unique constraint on business key
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes 
    WHERE object_id = OBJECT_ID('dbo.gold_ev_revenue_by_source') 
      AND name = 'UQ_gold_ev_revenue_by_source_business_key'
)
BEGIN
    ALTER TABLE dbo.gold_ev_revenue_by_source
    ADD CONSTRAINT UQ_gold_ev_revenue_by_source_business_key 
    UNIQUE NONCLUSTERED (year_month, revenue_source);
    PRINT 'Added UNIQUE constraint on (year_month, revenue_source)';
END;

-- =====================================================
-- STEP 5: Verify the fixes
-- =====================================================

PRINT '--- Verification ---';

-- Check new structure for gold_ev_charger_performance
SELECT 
    'gold_ev_charger_performance' AS TableName,
    c.name AS ColumnName,
    TYPE_NAME(c.user_type_id) AS DataType,
    c.is_nullable AS IsNullable,
    c.is_identity AS IsIdentity,
    CASE WHEN pk.column_id IS NOT NULL THEN 'YES' ELSE 'NO' END AS IsPrimaryKey
FROM sys.columns c
LEFT JOIN sys.index_columns pk ON c.object_id = pk.object_id 
    AND c.column_id = pk.column_id
    AND pk.index_id = (
        SELECT index_id FROM sys.indexes 
        WHERE object_id = OBJECT_ID('dbo.gold_ev_charger_performance') 
          AND is_primary_key = 1
    )
WHERE c.object_id = OBJECT_ID('dbo.gold_ev_charger_performance')
ORDER BY c.column_id;

-- Check new structure for gold_ev_revenue_by_source
SELECT 
    'gold_ev_revenue_by_source' AS TableName,
    c.name AS ColumnName,
    TYPE_NAME(c.user_type_id) AS DataType,
    c.is_nullable AS IsNullable,
    c.is_identity AS IsIdentity,
    CASE WHEN pk.column_id IS NOT NULL THEN 'YES' ELSE 'NO' END AS IsPrimaryKey
FROM sys.columns c
LEFT JOIN sys.index_columns pk ON c.object_id = pk.object_id 
    AND c.column_id = pk.column_id
    AND pk.index_id = (
        SELECT index_id FROM sys.indexes 
        WHERE object_id = OBJECT_ID('dbo.gold_ev_revenue_by_source') 
          AND is_primary_key = 1
    )
WHERE c.object_id = OBJECT_ID('dbo.gold_ev_revenue_by_source')
ORDER BY c.column_id;

-- Check row counts
SELECT 
    'gold_ev_charger_performance' AS TableName,
    COUNT(*) AS CurrentRows,
    (SELECT COUNT(*) FROM dbo.gold_ev_charger_performance_backup) AS BackupRows
FROM dbo.gold_ev_charger_performance
UNION ALL
SELECT 
    'gold_ev_revenue_by_source' AS TableName,
    COUNT(*) AS CurrentRows,
    (SELECT COUNT(*) FROM dbo.gold_ev_revenue_by_source_backup) AS BackupRows
FROM dbo.gold_ev_revenue_by_source;

PRINT '--- Fix completed! ---';
PRINT 'Next step: Review and update the stored procedure usp_Load_Gold_EV_KPIs';
PRINT 'to use MERGE or DELETE+INSERT pattern for idempotent loads.';
