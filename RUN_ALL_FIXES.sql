-- =====================================================
-- COMPLETE FIX SCRIPT - RUN THIS IN AZURE SQL QUERY EDITOR
-- =====================================================
-- This script will:
-- 1. Verify table structure fixes were applied
-- 2. Update all three stored procedures
-- 3. Test each procedure
-- 4. Provide verification queries
-- =====================================================

PRINT '======================================================';
PRINT 'STEP 1: Verify Table Structure Fixes';
PRINT '======================================================';

-- Check if identity columns exist
IF EXISTS (
    SELECT 1 FROM sys.columns 
    WHERE object_id = OBJECT_ID('dbo.gold_ev_charger_performance') 
      AND name = 'performance_id' 
      AND is_identity = 1
)
    PRINT '✅ gold_ev_charger_performance.performance_id (IDENTITY) exists';
ELSE
    PRINT '❌ ERROR: performance_id not found! Run FIX_PRIMARY_KEY_ISSUES.sql first';

IF EXISTS (
    SELECT 1 FROM sys.columns 
    WHERE object_id = OBJECT_ID('dbo.gold_ev_revenue_by_source') 
      AND name = 'revenue_id' 
      AND is_identity = 1
)
    PRINT '✅ gold_ev_revenue_by_source.revenue_id (IDENTITY) exists';
ELSE
    PRINT '❌ ERROR: revenue_id not found! Run FIX_PRIMARY_KEY_ISSUES.sql first';

PRINT '';
PRINT '======================================================';
PRINT 'STEP 2: Drop Old Stored Procedures';
PRINT '======================================================';

DROP PROCEDURE IF EXISTS dbo.usp_Load_Silver_EV_Operations;
PRINT '✅ Dropped dbo.usp_Load_Silver_EV_Operations';

DROP PROCEDURE IF EXISTS dbo.usp_Load_Gold_EV_KPIs;
PRINT '✅ Dropped dbo.usp_Load_Gold_EV_KPIs';

PRINT '';
PRINT '======================================================';
PRINT 'STEP 3: Create Fixed Stored Procedures';
PRINT '======================================================';
PRINT 'Now copy and paste the content of these files in order:';
PRINT '1. usp_Load_Silver_EV_Operations_FIXED.sql';
PRINT '2. usp_Load_Gold_EV_KPIs_FIXED.sql';
PRINT '';
PRINT 'After pasting each file, you should see:';
PRINT '  "Commands completed successfully."';
PRINT '';
PRINT 'Press any key when ready to continue to testing...';
PRINT '======================================================';

GO

-- =====================================================
-- PAUSE HERE AND PASTE THE TWO STORED PROCEDURE FILES
-- =====================================================

PRINT '';
PRINT '======================================================';
PRINT 'STEP 4: Verify Stored Procedures Were Created';
PRINT '======================================================';

IF OBJECT_ID('dbo.usp_Load_Silver_EV_Operations', 'P') IS NOT NULL
    PRINT '✅ usp_Load_Silver_EV_Operations created successfully';
ELSE
    PRINT '❌ ERROR: usp_Load_Silver_EV_Operations not found!';

IF OBJECT_ID('dbo.usp_Load_Gold_EV_KPIs', 'P') IS NOT NULL
    PRINT '✅ usp_Load_Gold_EV_KPIs created successfully';
ELSE
    PRINT '❌ ERROR: usp_Load_Gold_EV_KPIs not found!';

IF OBJECT_ID('dbo.usp_Load_Gold_EV_Exceptions', 'P') IS NOT NULL
    PRINT '✅ usp_Load_Gold_EV_Exceptions exists (no changes needed)';
ELSE
    PRINT '⚠️  WARNING: usp_Load_Gold_EV_Exceptions not found!';

PRINT '';
PRINT '======================================================';
PRINT 'STEP 5: Test Stored Procedures';
PRINT '======================================================';
PRINT 'Run the tests below one by one...';
PRINT '';

-- Test variables
DECLARE @TestDate DATE = '2026-06-01';

PRINT '--- TEST 1: Silver Layer ---';
PRINT 'Running: EXEC dbo.usp_Load_Silver_EV_Operations @pipeline_date = ''' + CAST(@TestDate AS VARCHAR(10)) + ''';';

EXEC dbo.usp_Load_Silver_EV_Operations @pipeline_date = @TestDate;

PRINT '';
PRINT 'Verifying Silver Data Quality...';
SELECT 
    COUNT(*) AS TotalRows,
    SUM(CASE WHEN charger_id IS NULL THEN 1 ELSE 0 END) AS NullChargerIds,
    SUM(CASE WHEN LEN(RTRIM(charger_id)) = 0 THEN 1 ELSE 0 END) AS EmptyChargerIds,
    SUM(CASE WHEN charger_id = '' THEN 1 ELSE 0 END) AS BlankChargerIds
FROM dbo.silver_ev_operations
WHERE CAST(timestamp AS DATE) = @TestDate;
-- Expected: 0 for NullChargerIds, EmptyChargerIds, and BlankChargerIds

PRINT '';
PRINT '--- TEST 2: Gold KPI Layer ---';
PRINT 'Running: EXEC dbo.usp_Load_Gold_EV_KPIs @pipeline_date = ''' + CAST(@TestDate AS VARCHAR(10)) + ''';';

EXEC dbo.usp_Load_Gold_EV_KPIs @pipeline_date = @TestDate;

PRINT '';
PRINT 'Checking for duplicates in gold_ev_charger_performance...';
SELECT 
    charger_id, 
    COUNT(*) AS DuplicateCount
FROM dbo.gold_ev_charger_performance
GROUP BY charger_id
HAVING COUNT(*) > 1;
-- Expected: 0 rows

PRINT '';
PRINT 'Checking for duplicates in gold_ev_revenue_by_source...';
SELECT 
    year_month, 
    revenue_source, 
    COUNT(*) AS DuplicateCount
FROM dbo.gold_ev_revenue_by_source
GROUP BY year_month, revenue_source
HAVING COUNT(*) > 1;
-- Expected: 0 rows

PRINT '';
PRINT '--- TEST 3: Gold KPI Tables Row Counts ---';
SELECT 
    'gold_ev_daily_summary' AS TableName, 
    COUNT(*) AS RowCount,
    MIN(data_date) AS MinDate,
    MAX(data_date) AS MaxDate
FROM dbo.gold_ev_daily_summary
WHERE data_date = @TestDate
UNION ALL
SELECT 
    'gold_ev_revenue_by_source', 
    COUNT(*),
    CAST(year_month + '-01' AS DATE),
    CAST(year_month + '-01' AS DATE)
FROM dbo.gold_ev_revenue_by_source
WHERE year_month = FORMAT(@TestDate, 'yyyy-MM')
UNION ALL
SELECT 
    'gold_ev_hourly_diagnostics', 
    COUNT(*),
    MIN(data_date),
    MAX(data_date)
FROM dbo.gold_ev_hourly_diagnostics
WHERE data_date = @TestDate
UNION ALL
SELECT 
    'gold_ev_charger_30day_trend', 
    COUNT(*),
    MIN(data_date),
    MAX(data_date)
FROM dbo.gold_ev_charger_30day_trend
WHERE data_date = @TestDate
UNION ALL
SELECT 
    'gold_ev_charger_performance', 
    COUNT(*),
    NULL,
    NULL
FROM dbo.gold_ev_charger_performance;

PRINT '';
PRINT '======================================================';
PRINT 'STEP 6: Test Idempotency (Re-run Same Date)';
PRINT '======================================================';
PRINT 'Running procedures again for the same date...';

-- Store counts before re-run
DECLARE @CountBefore_ChargerPerf INT;
DECLARE @CountBefore_RevenueSource INT;

SELECT @CountBefore_ChargerPerf = COUNT(*) 
FROM dbo.gold_ev_charger_performance;

SELECT @CountBefore_RevenueSource = COUNT(*) 
FROM dbo.gold_ev_revenue_by_source
WHERE year_month = FORMAT(@TestDate, 'yyyy-MM');

PRINT 'Counts before re-run:';
PRINT '  gold_ev_charger_performance: ' + CAST(@CountBefore_ChargerPerf AS VARCHAR(10));
PRINT '  gold_ev_revenue_by_source: ' + CAST(@CountBefore_RevenueSource AS VARCHAR(10));

-- Re-run
EXEC dbo.usp_Load_Silver_EV_Operations @pipeline_date = @TestDate;
EXEC dbo.usp_Load_Gold_EV_KPIs @pipeline_date = @TestDate;

-- Check counts after re-run
DECLARE @CountAfter_ChargerPerf INT;
DECLARE @CountAfter_RevenueSource INT;

SELECT @CountAfter_ChargerPerf = COUNT(*) 
FROM dbo.gold_ev_charger_performance;

SELECT @CountAfter_RevenueSource = COUNT(*) 
FROM dbo.gold_ev_revenue_by_source
WHERE year_month = FORMAT(@TestDate, 'yyyy-MM');

PRINT '';
PRINT 'Counts after re-run:';
PRINT '  gold_ev_charger_performance: ' + CAST(@CountAfter_ChargerPerf AS VARCHAR(10));
PRINT '  gold_ev_revenue_by_source: ' + CAST(@CountAfter_RevenueSource AS VARCHAR(10));

IF @CountAfter_ChargerPerf = @CountBefore_ChargerPerf 
   AND @CountAfter_RevenueSource = @CountBefore_RevenueSource
    PRINT '✅ Idempotency test PASSED - counts remained the same';
ELSE
    PRINT '❌ Idempotency test FAILED - counts changed!';

PRINT '';
PRINT '======================================================';
PRINT 'STEP 7: Summary';
PRINT '======================================================';
PRINT 'If all tests passed:';
PRINT '  ✅ Silver layer is filtering bad data';
PRINT '  ✅ Gold KPI layer has no duplicates';
PRINT '  ✅ Stored procedures are idempotent';
PRINT '';
PRINT 'Next steps:';
PRINT '  1. Go to Azure Data Factory';
PRINT '  2. Run Pipeline PL_07_Silver_To_Gold_KPIs';
PRINT '  3. Monitor for success';
PRINT '';
PRINT 'If pipeline still fails, check:';
PRINT '  - Pipeline parameter: pipeline_date';
PRINT '  - Linked service connection';
PRINT '  - Stored procedure permissions';
PRINT '======================================================';
