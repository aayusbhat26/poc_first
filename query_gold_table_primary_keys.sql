-- =====================================================
-- Query All Gold Tables Primary Keys
-- Purpose: Identify all gold_ev_* tables and their primary key definitions
-- Run this in Azure SQL Query Editor
-- =====================================================

-- 1. List all gold_ev_* tables with their primary key constraints
SELECT 
    t.name AS TableName,
    pk.name AS PrimaryKeyName,
    STUFF((
        SELECT ', ' + c.name + ' (' + TYPE_NAME(c.user_type_id) + 
               CASE WHEN c.max_length = -1 THEN '(MAX)' 
                    WHEN TYPE_NAME(c.user_type_id) IN ('varchar', 'nvarchar', 'char', 'nchar') 
                    THEN '(' + CAST(c.max_length AS VARCHAR(10)) + ')' 
                    ELSE '' 
               END + ')'
        FROM sys.index_columns ic
        INNER JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
        WHERE ic.object_id = t.object_id AND ic.index_id = pk.index_id
        ORDER BY ic.key_ordinal
        FOR XML PATH('')
    ), 1, 2, '') AS PrimaryKeyColumns,
    pk.is_unique AS IsUnique,
    pk.type_desc AS IndexType
FROM sys.tables t
LEFT JOIN sys.indexes pk ON t.object_id = pk.object_id AND pk.is_primary_key = 1
WHERE t.name LIKE 'gold_ev_%'
ORDER BY t.name;

-- 2. Detailed column information for all gold_ev_* tables
SELECT 
    t.name AS TableName,
    c.column_id AS ColumnOrder,
    c.name AS ColumnName,
    TYPE_NAME(c.user_type_id) AS DataType,
    CASE 
        WHEN c.max_length = -1 THEN 'MAX'
        WHEN TYPE_NAME(c.user_type_id) IN ('varchar', 'nvarchar', 'char', 'nchar') 
        THEN CAST(c.max_length AS VARCHAR(10))
        WHEN TYPE_NAME(c.user_type_id) IN ('decimal', 'numeric')
        THEN CAST(c.precision AS VARCHAR(10)) + ',' + CAST(c.scale AS VARCHAR(10))
        ELSE ''
    END AS Size,
    CASE WHEN c.is_nullable = 1 THEN 'NULL' ELSE 'NOT NULL' END AS Nullable,
    CASE WHEN ic.column_id IS NOT NULL THEN 'PK' ELSE '' END AS IsPrimaryKey,
    CASE WHEN c.is_identity = 1 THEN 'IDENTITY(' + CAST(IDENT_SEED(t.name) AS VARCHAR(10)) + ',' + CAST(IDENT_INCR(t.name) AS VARCHAR(10)) + ')' ELSE '' END AS IdentityInfo
FROM sys.tables t
INNER JOIN sys.columns c ON t.object_id = c.object_id
LEFT JOIN sys.indexes pk ON t.object_id = pk.object_id AND pk.is_primary_key = 1
LEFT JOIN sys.index_columns ic ON pk.object_id = ic.object_id AND pk.index_id = ic.index_id AND c.column_id = ic.column_id
WHERE t.name LIKE 'gold_ev_%'
ORDER BY t.name, c.column_id;

-- 3. Check for duplicate records in gold_ev_charger_performance
IF OBJECT_ID('dbo.gold_ev_charger_performance', 'U') IS NOT NULL
BEGIN
    PRINT '--- Checking gold_ev_charger_performance for duplicates ---';
    
    -- Find the actual primary key columns
    DECLARE @PKColumns NVARCHAR(MAX);
    SELECT @PKColumns = STUFF((
        SELECT ', ' + c.name
        FROM sys.index_columns ic
        INNER JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
        INNER JOIN sys.indexes pk ON ic.object_id = pk.object_id AND ic.index_id = pk.index_id
        WHERE pk.is_primary_key = 1 AND pk.object_id = OBJECT_ID('dbo.gold_ev_charger_performance')
        ORDER BY ic.key_ordinal
        FOR XML PATH('')
    ), 1, 2, '');
    
    PRINT 'Primary Key Columns: ' + ISNULL(@PKColumns, 'No PK defined');
    
    -- Sample data
    SELECT TOP 10 * FROM dbo.gold_ev_charger_performance ORDER BY 1;
END;

-- 4. Check for duplicate records in gold_ev_revenue_by_source
IF OBJECT_ID('dbo.gold_ev_revenue_by_source', 'U') IS NOT NULL
BEGIN
    PRINT '--- Checking gold_ev_revenue_by_source for duplicates ---';
    
    -- Find the actual primary key columns
    DECLARE @PKColumns2 NVARCHAR(MAX);
    SELECT @PKColumns2 = STUFF((
        SELECT ', ' + c.name
        FROM sys.index_columns ic
        INNER JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
        INNER JOIN sys.indexes pk ON ic.object_id = pk.object_id AND ic.index_id = pk.index_id
        WHERE pk.is_primary_key = 1 AND pk.object_id = OBJECT_ID('dbo.gold_ev_revenue_by_source')
        ORDER BY ic.key_ordinal
        FOR XML PATH('')
    ), 1, 2, '');
    
    PRINT 'Primary Key Columns: ' + ISNULL(@PKColumns2, 'No PK defined');
    
    -- Check for duplicate combinations
    SELECT 
        *,
        COUNT(*) AS DuplicateCount
    FROM dbo.gold_ev_revenue_by_source
    GROUP BY 
        CASE WHEN @PKColumns2 LIKE '%month%' THEN month_period ELSE NULL END,
        CASE WHEN @PKColumns2 LIKE '%revenue_source%' THEN revenue_source ELSE NULL END
    HAVING COUNT(*) > 1;
    
    -- Sample data
    SELECT TOP 10 * FROM dbo.gold_ev_revenue_by_source ORDER BY 1;
END;

-- 5. Show stored procedure definition for usp_Load_Gold_EV_KPIs
IF OBJECT_ID('dbo.usp_Load_Gold_EV_KPIs', 'P') IS NOT NULL
BEGIN
    PRINT '--- Stored Procedure: usp_Load_Gold_EV_KPIs ---';
    SELECT 
        OBJECT_DEFINITION(OBJECT_ID('dbo.usp_Load_Gold_EV_KPIs')) AS StoredProcedureCode;
END
ELSE
BEGIN
    PRINT 'Stored procedure usp_Load_Gold_EV_KPIs does not exist.';
END;

-- 6. Count rows in each gold table
SELECT 
    t.name AS TableName,
    SUM(p.rows) AS RowCount
FROM sys.tables t
INNER JOIN sys.partitions p ON t.object_id = p.object_id
WHERE t.name LIKE 'gold_ev_%' AND p.index_id IN (0,1)
GROUP BY t.name
ORDER BY t.name;
