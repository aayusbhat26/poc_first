-- =====================================================
-- DIRECT FIX - Run this entire script in Azure SQL Query Editor
-- This will fix all stored procedures in one go
-- =====================================================

-- Step 1: Drop old procedures
DROP PROCEDURE IF EXISTS dbo.usp_Load_Silver_EV_Operations;
DROP PROCEDURE IF EXISTS dbo.usp_Load_Gold_EV_KPIs;
GO

-- =====================================================
-- Step 2: Create Fixed Silver Layer Procedure
-- =====================================================
CREATE PROCEDURE dbo.usp_Load_Silver_EV_Operations
    @pipeline_date DATE
AS
BEGIN
    SET NOCOUNT ON;
    
    DECLARE @RowsInserted INT;
    
    -- Delete existing records for this date (idempotent)
    DELETE FROM dbo.silver_ev_operations
    WHERE CAST(timestamp AS DATE) = @pipeline_date;
    
    -- Insert with data quality filters
    INSERT INTO dbo.silver_ev_operations
    (
        charger_id, timestamp, state, city, zone, site_type, hw_type, charger_type_category,
        max_power_kw, status, is_online, uptime_pct, user_id, session_duration_mins,
        session_dur_bucket, time_of_day_band, utilisation_pct, total_active_power_kw,
        voltage_phase_a_v, voltage_phase_b_v, voltage_phase_c_v, current_phase_a_a,
        current_phase_b_a, current_phase_c_a, connector_temp_c, ambient_temp_c,
        energy_delivered_kwh, session_revenue_inr, electricity_cost_inr, maintenance_cost_inr,
        connectivity_cost_inr, staff_cost_inr, net_margin_inr, lost_revenue_inr,
        initial_soc_pct, current_soc_pct, target_soc_pct, error_code, fault_severity,
        is_faulted, repeat_fault, mttr_estimate_mins, downtime_mins_today, customers_lost,
        fault_lost_revenue_inr, zone_score, peak_hour, IsCriticalFault, ChargeEfficiency,
        RevenueCategory, FaultCategory, HealthScore, ingestion_timestamp, TotalCostINR,
        ProfitMarginPct, RevenuePerKwh, CostPerKwh, SoCDelta, IsHighUtilisation,
        IsOverheating, CustomerImpactScore
    )
    SELECT
        charger_id, timestamp, state, city, zone, site_type, hw_type, charger_type_category,
        max_power_kw, status, is_online, ISNULL(uptime_pct, 100), user_id,
        ISNULL(session_duration_mins, 0), session_dur_bucket, time_of_day_band,
        ISNULL(utilisation_pct, 0), ISNULL(total_active_power_kw, 0), voltage_phase_a_v,
        voltage_phase_b_v, voltage_phase_c_v, current_phase_a_a, current_phase_b_a,
        current_phase_c_a, connector_temp_c, ambient_temp_c, ISNULL(energy_delivered_kwh, 0),
        ISNULL(session_revenue_inr, 0), electricity_cost_inr, maintenance_cost_inr,
        connectivity_cost_inr, staff_cost_inr, net_margin_inr, ISNULL(lost_revenue_inr, 0),
        initial_soc_pct, current_soc_pct, target_soc_pct, error_code, fault_severity,
        is_faulted, repeat_fault, ISNULL(mttr_estimate_mins, 0), ISNULL(downtime_mins_today, 0),
        ISNULL(customers_lost, 0), ISNULL(fault_lost_revenue_inr, 0), ISNULL(zone_score, 0),
        peak_hour,
        CASE WHEN fault_severity IN ('Critical', 'High') THEN 1 ELSE 0 END,
        CASE WHEN ISNULL(session_duration_mins, 0) > 0 THEN
            CASE WHEN (ISNULL(energy_delivered_kwh, 0) / (session_duration_mins / 60.0)) * 100 > 100 THEN 100
                 ELSE ROUND((ISNULL(energy_delivered_kwh, 0) / (session_duration_mins / 60.0)) * 100, 2)
            END ELSE 0 END,
        CASE WHEN ISNULL(session_revenue_inr, 0) >= 500 THEN 'High'
             WHEN ISNULL(session_revenue_inr, 0) >= 200 THEN 'Medium' ELSE 'Low' END,
        CASE WHEN error_code IS NULL OR error_code = 'None' THEN 'No Fault'
             WHEN fault_severity = 'Critical' THEN 'Critical Fault'
             WHEN fault_severity = 'High' THEN 'Major Fault' ELSE 'Minor Fault' END,
        CASE WHEN ISNULL(uptime_pct, 100) > 0 THEN ISNULL(uptime_pct, 100) - (ISNULL(downtime_mins_today, 0) / 14.4) ELSE 0 END,
        GETUTCDATE(),
        ISNULL(electricity_cost_inr, 0) + ISNULL(maintenance_cost_inr, 0) + ISNULL(connectivity_cost_inr, 0) + ISNULL(staff_cost_inr, 0),
        CASE WHEN ISNULL(session_revenue_inr, 0) > 0 THEN (ISNULL(net_margin_inr, 0) / session_revenue_inr) * 100 ELSE 0 END,
        CASE WHEN ISNULL(energy_delivered_kwh, 0) > 0 THEN ISNULL(session_revenue_inr, 0) / energy_delivered_kwh ELSE 0 END,
        CASE WHEN ISNULL(energy_delivered_kwh, 0) > 0 THEN (ISNULL(electricity_cost_inr, 0) + ISNULL(maintenance_cost_inr, 0) + ISNULL(connectivity_cost_inr, 0) + ISNULL(staff_cost_inr, 0)) / energy_delivered_kwh ELSE 0 END,
        ISNULL(current_soc_pct, 0) - ISNULL(initial_soc_pct, 0),
        CASE WHEN ISNULL(utilisation_pct, 0) >= 80 THEN 1 ELSE 0 END,
        CASE WHEN connector_temp_c > 80 OR ambient_temp_c > 45 THEN 1 ELSE 0 END,
        ISNULL(customers_lost, 0) * ISNULL(fault_lost_revenue_inr, 0)
    FROM dbo.stg_ev_telemetry
    WHERE CAST(timestamp AS DATE) = @pipeline_date
      AND charger_id IS NOT NULL 
      AND LEN(RTRIM(charger_id)) > 0
      AND charger_id <> '';
    
    SET @RowsInserted = @@ROWCOUNT;
    SELECT @RowsInserted AS RowsWritten;
END;
GO

-- =====================================================
-- Step 3: Create Fixed Gold KPI Procedure
-- =====================================================
CREATE PROCEDURE dbo.usp_Load_Gold_EV_KPIs
    @pipeline_date DATE
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @YearMonth VARCHAR(7) = FORMAT(@pipeline_date, 'yyyy-MM');
    
    IF OBJECT_ID('tempdb..#DailyChargerAgg') IS NOT NULL DROP TABLE #DailyChargerAgg;
    
    SELECT charger_id, state, city, zone, hw_type, site_type, max_power_kw, data_date,
        ISNULL(SUM(session_revenue), 0) AS daily_revenue,
        ISNULL(SUM(session_energy), 0) AS daily_energy,
        ISNULL(SUM(session_total_opex), 0) AS daily_opex,
        COUNT(user_id) AS daily_sessions
    INTO #DailyChargerAgg
    FROM (
        SELECT charger_id, state, city, zone, hw_type, site_type, max_power_kw,
            CAST(timestamp AS DATE) AS data_date, user_id,
            MAX(session_revenue_inr) AS session_revenue,
            MAX(energy_delivered_kwh) AS session_energy,
            MAX(ISNULL(electricity_cost_inr,0) + ISNULL(maintenance_cost_inr,0) + ISNULL(connectivity_cost_inr,0) + ISNULL(staff_cost_inr,0)) AS session_total_opex
        FROM dbo.silver_ev_operations
        WHERE user_id IS NOT NULL AND CAST(timestamp AS DATE) = @pipeline_date
          AND charger_id IS NOT NULL AND LEN(RTRIM(charger_id)) > 0
        GROUP BY charger_id, state, city, zone, hw_type, site_type, max_power_kw, CAST(timestamp AS DATE), user_id
    ) SessionAgg
    GROUP BY charger_id, state, city, zone, hw_type, site_type, max_power_kw, data_date;
    
    DELETE FROM dbo.gold_ev_daily_summary WHERE data_date = @pipeline_date;
    INSERT INTO dbo.gold_ev_daily_summary
    SELECT d.data_date, d.state, d.city, SUM(d.daily_revenue), SUM(d.daily_energy), SUM(d.daily_sessions),
        ISNULL((SELECT AVG(uptime_pct) FROM dbo.silver_ev_operations WHERE CAST(timestamp AS DATE) = @pipeline_date AND state = d.state AND city = d.city), 0),
        SUM(d.daily_opex), SUM(d.daily_revenue) - SUM(d.daily_opex),
        CASE WHEN SUM(d.daily_revenue) > 0 THEN ((SUM(d.daily_revenue) - SUM(d.daily_opex)) / SUM(d.daily_revenue)) * 100 ELSE 0 END
    FROM #DailyChargerAgg d
    GROUP BY d.data_date, d.state, d.city;
    
    DELETE FROM dbo.gold_ev_revenue_by_source WHERE year_month = @YearMonth;
    WITH MonthlyRev AS (
        SELECT ISNULL(SUM(session_revenue), 0) AS TotalRev, ISNULL(SUM(session_total_opex), 0) AS TotalOpex
        FROM (
            SELECT MAX(session_revenue_inr) AS session_revenue, 
                MAX(ISNULL(electricity_cost_inr,0) + ISNULL(maintenance_cost_inr,0) + ISNULL(connectivity_cost_inr,0) + ISNULL(staff_cost_inr,0)) AS session_total_opex
            FROM dbo.silver_ev_operations 
            WHERE FORMAT(timestamp, 'yyyy-MM') = @YearMonth AND user_id IS NOT NULL
              AND charger_id IS NOT NULL AND LEN(RTRIM(charger_id)) > 0
            GROUP BY charger_id, CAST(timestamp AS DATE), user_id
        ) m
    )
    INSERT INTO dbo.gold_ev_revenue_by_source (year_month, revenue_source, revenue_inr, revenue_pct_of_total, profit_margin_pct, opex_inr, capex_inr)
    SELECT @YearMonth, 'Charging Fees', TotalRev * 0.75, 75.00, CASE WHEN TotalRev > 0 THEN ((TotalRev*0.75 - TotalOpex)/NULLIF(TotalRev*0.75,0))*100 ELSE 0 END, TotalOpex, 150000 FROM MonthlyRev 
    UNION ALL SELECT @YearMonth, 'Subscription', TotalRev * 0.15, 15.00, 95.00, 0, 0 FROM MonthlyRev 
    UNION ALL SELECT @YearMonth, 'Parking Fees', TotalRev * 0.08, 8.00, 90.00, 0, 50000 FROM MonthlyRev 
    UNION ALL SELECT @YearMonth, 'Other', TotalRev * 0.02, 2.00, 50.00, 0, 0 FROM MonthlyRev;
    
    DELETE FROM dbo.gold_ev_hourly_diagnostics WHERE data_date = @pipeline_date;
    INSERT INTO dbo.gold_ev_hourly_diagnostics
    SELECT charger_id, CAST(timestamp AS DATE), DATEPART(HOUR, timestamp),
        ISNULL(AVG(total_active_power_kw), 0), ISNULL(MAX(connector_temp_c), 0), COUNT(DISTINCT user_id),
        SUM(CASE WHEN is_online = 1 THEN 1 ELSE 0 END), SUM(CASE WHEN is_faulted = 1 THEN 1 ELSE 0 END)
    FROM dbo.silver_ev_operations
    WHERE CAST(timestamp AS DATE) = @pipeline_date AND charger_id IS NOT NULL AND LEN(RTRIM(charger_id)) > 0
    GROUP BY charger_id, CAST(timestamp AS DATE), DATEPART(HOUR, timestamp);
    
    DELETE FROM dbo.gold_ev_charger_30day_trend WHERE data_date = @pipeline_date;
    INSERT INTO dbo.gold_ev_charger_30day_trend
    SELECT d.charger_id, d.data_date, 'D' + RIGHT('0' + CAST(DAY(d.data_date) AS VARCHAR(2)), 2),
        ISNULL((SELECT AVG(utilisation_pct) FROM dbo.silver_ev_operations WHERE charger_id = d.charger_id AND CAST(timestamp AS DATE) = d.data_date), 0),
        ISNULL((SELECT AVG(uptime_pct) FROM dbo.silver_ev_operations WHERE charger_id = d.charger_id AND CAST(timestamp AS DATE) = d.data_date), 0),
        ISNULL((SELECT SUM(CASE WHEN is_faulted = 1 THEN 1 ELSE 0 END) FROM dbo.silver_ev_operations WHERE charger_id = d.charger_id AND CAST(timestamp AS DATE) = d.data_date), 0),
        d.daily_revenue
    FROM #DailyChargerAgg d;
    
    DELETE FROM dbo.gold_ev_charger_performance;
    WITH LifetimeAgg AS (
        SELECT charger_id, SUM(session_revenue) AS life_rev, SUM(session_energy) AS life_energy, COUNT(user_id) AS life_sessions
        FROM (
            SELECT charger_id, user_id, MAX(session_revenue_inr) AS session_revenue, MAX(energy_delivered_kwh) AS session_energy 
            FROM dbo.silver_ev_operations 
            WHERE user_id IS NOT NULL AND charger_id IS NOT NULL AND LEN(RTRIM(charger_id)) > 0
            GROUP BY charger_id, CAST(timestamp AS DATE), user_id
        ) a 
        GROUP BY charger_id
    )
    INSERT INTO dbo.gold_ev_charger_performance
    SELECT s.charger_id, MAX(s.state), MAX(s.city), MAX(s.zone), MAX(s.hw_type), MAX(s.max_power_kw), MAX(s.site_type),
        ISNULL(MAX(l.life_rev), 0), ISNULL(MAX(l.life_sessions), 0), ISNULL(MAX(l.life_energy), 0),
        ISNULL(AVG(s.utilisation_pct), 0), ISNULL(AVG(s.uptime_pct), 0),
        ISNULL(SUM(CASE WHEN s.is_faulted = 1 THEN 1 ELSE 0 END) / 60.0, 0),
        CASE WHEN AVG(s.utilisation_pct) <= 20 THEN '0-20%' WHEN AVG(s.utilisation_pct) <= 40 THEN '21-40%' 
             WHEN AVG(s.utilisation_pct) <= 60 THEN '41-60%' WHEN AVG(s.utilisation_pct) <= 80 THEN '61-80%' ELSE '81-100%' END
    FROM dbo.silver_ev_operations s
    LEFT JOIN LifetimeAgg l ON s.charger_id = l.charger_id
    WHERE s.charger_id IS NOT NULL AND LEN(RTRIM(s.charger_id)) > 0
    GROUP BY s.charger_id;
    
    DROP TABLE #DailyChargerAgg;
END;
GO

-- Done! Now test it
SELECT 'Procedures created successfully' AS Status;
