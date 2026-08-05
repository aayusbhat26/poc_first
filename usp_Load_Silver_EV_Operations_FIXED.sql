-- =====================================================
-- FIXED STORED PROCEDURE: usp_Load_Silver_EV_Operations
-- Fixes:
-- 1. Added charger_id validation in WHERE clause
-- 2. Filters out NULL, empty string, and whitespace-only charger_ids
-- 3. Already idempotent (DELETE before INSERT)
-- =====================================================

CREATE OR ALTER PROCEDURE dbo.usp_Load_Silver_EV_Operations
    @pipeline_date DATE
AS
BEGIN
    SET NOCOUNT ON;
    
    DECLARE @RowsInserted INT;
    DECLARE @BadRowsRejected INT;
    
    -- Count bad rows before filtering (for logging)
    SELECT @BadRowsRejected = COUNT(*)
    FROM dbo.stg_ev_telemetry
    WHERE CAST(timestamp AS DATE) = @pipeline_date
      AND (
          charger_id IS NULL 
          OR LEN(RTRIM(charger_id)) = 0 
          OR charger_id = ''
      );
    
    -- Delete existing records for this date (idempotent)
    DELETE FROM dbo.silver_ev_operations
    WHERE CAST(timestamp AS DATE) = @pipeline_date;
    
    -- Insert with data quality filters
    INSERT INTO dbo.silver_ev_operations
    (
        charger_id,
        timestamp,
        state,
        city,
        zone,
        site_type,
        hw_type,
        charger_type_category,
        max_power_kw,
        status,
        is_online,
        uptime_pct,
        user_id,
        session_duration_mins,
        session_dur_bucket,
        time_of_day_band,
        utilisation_pct,
        total_active_power_kw,
        voltage_phase_a_v,
        voltage_phase_b_v,
        voltage_phase_c_v,
        current_phase_a_a,
        current_phase_b_a,
        current_phase_c_a,
        connector_temp_c,
        ambient_temp_c,
        energy_delivered_kwh,
        session_revenue_inr,
        electricity_cost_inr,
        maintenance_cost_inr,
        connectivity_cost_inr,
        staff_cost_inr,
        net_margin_inr,
        lost_revenue_inr,
        initial_soc_pct,
        current_soc_pct,
        target_soc_pct,
        error_code,
        fault_severity,
        is_faulted,
        repeat_fault,
        mttr_estimate_mins,
        downtime_mins_today,
        customers_lost,
        fault_lost_revenue_inr,
        zone_score,
        peak_hour,
        IsCriticalFault,
        ChargeEfficiency,
        RevenueCategory,
        FaultCategory,
        HealthScore,
        ingestion_timestamp,
        TotalCostINR,
        ProfitMarginPct,
        RevenuePerKwh,
        CostPerKwh,
        SoCDelta,
        IsHighUtilisation,
        IsOverheating,
        CustomerImpactScore
    )
    SELECT
        charger_id,
        timestamp,
        state,
        city,
        zone,
        site_type,
        hw_type,
        charger_type_category,
        max_power_kw,
        status,
        is_online,
        ISNULL(uptime_pct, 100),
        user_id,
        ISNULL(session_duration_mins, 0),
        session_dur_bucket,
        time_of_day_band,
        ISNULL(utilisation_pct, 0),
        ISNULL(total_active_power_kw, 0),
        voltage_phase_a_v,
        voltage_phase_b_v,
        voltage_phase_c_v,
        current_phase_a_a,
        current_phase_b_a,
        current_phase_c_a,
        connector_temp_c,
        ambient_temp_c,
        ISNULL(energy_delivered_kwh, 0),
        ISNULL(session_revenue_inr, 0),
        electricity_cost_inr,
        maintenance_cost_inr,
        connectivity_cost_inr,
        staff_cost_inr,
        net_margin_inr,
        ISNULL(lost_revenue_inr, 0),
        initial_soc_pct,
        current_soc_pct,
        target_soc_pct,
        error_code,
        fault_severity,
        is_faulted,
        repeat_fault,
        ISNULL(mttr_estimate_mins, 0),
        ISNULL(downtime_mins_today, 0),
        ISNULL(customers_lost, 0),
        ISNULL(fault_lost_revenue_inr, 0),
        ISNULL(zone_score, 0),
        peak_hour,
        -- IsCriticalFault
        CASE
            WHEN fault_severity IN ('Critical', 'High')
            THEN 1
            ELSE 0
        END,
        -- ChargeEfficiency
        CASE
            WHEN ISNULL(session_duration_mins, 0) > 0
            THEN
                CASE
                    WHEN (
                            ISNULL(energy_delivered_kwh, 0)
                            / (session_duration_mins / 60.0)
                         ) * 100 > 100
                    THEN 100
                    ELSE ROUND(
                            (
                                ISNULL(energy_delivered_kwh, 0)
                                / (session_duration_mins / 60.0)
                            ) * 100,
                            2
                         )
                END
            ELSE 0
        END,
        -- RevenueCategory
        CASE
            WHEN ISNULL(session_revenue_inr, 0) >= 500 THEN 'High'
            WHEN ISNULL(session_revenue_inr, 0) >= 200 THEN 'Medium'
            ELSE 'Low'
        END,
        -- FaultCategory
        CASE
            WHEN error_code IS NULL
                 OR error_code = 'None'
            THEN 'No Fault'
            WHEN fault_severity = 'Critical'
            THEN 'Critical Fault'
            WHEN fault_severity = 'High'
            THEN 'Major Fault'
            ELSE 'Minor Fault'
        END,
        -- HealthScore
        CASE
            WHEN ISNULL(uptime_pct, 100) > 0
            THEN ISNULL(uptime_pct, 100)
                 - (ISNULL(downtime_mins_today, 0) / 14.4)
            ELSE 0
        END,
        -- ingestion_timestamp
        GETUTCDATE(),
        -- TotalCostINR
        ISNULL(electricity_cost_inr, 0)
        + ISNULL(maintenance_cost_inr, 0)
        + ISNULL(connectivity_cost_inr, 0)
        + ISNULL(staff_cost_inr, 0),
        -- ProfitMarginPct
        CASE
            WHEN ISNULL(session_revenue_inr, 0) > 0
            THEN (
                    ISNULL(net_margin_inr, 0)
                    / session_revenue_inr
                 ) * 100
            ELSE 0
        END,
        -- RevenuePerKwh
        CASE
            WHEN ISNULL(energy_delivered_kwh, 0) > 0
            THEN ISNULL(session_revenue_inr, 0)
                 / energy_delivered_kwh
            ELSE 0
        END,
        -- CostPerKwh
        CASE
            WHEN ISNULL(energy_delivered_kwh, 0) > 0
            THEN
                (
                    ISNULL(electricity_cost_inr, 0)
                    + ISNULL(maintenance_cost_inr, 0)
                    + ISNULL(connectivity_cost_inr, 0)
                    + ISNULL(staff_cost_inr, 0)
                ) / energy_delivered_kwh
            ELSE 0
        END,
        -- SoCDelta
        ISNULL(current_soc_pct, 0)
        - ISNULL(initial_soc_pct, 0),
        -- IsHighUtilisation
        CASE
            WHEN ISNULL(utilisation_pct, 0) >= 80
            THEN 1
            ELSE 0
        END,
        -- IsOverheating
        CASE
            WHEN connector_temp_c > 80
                 OR ambient_temp_c > 45
            THEN 1
            ELSE 0
        END,
        -- CustomerImpactScore
        ISNULL(customers_lost, 0)
        * ISNULL(fault_lost_revenue_inr, 0)
    FROM dbo.stg_ev_telemetry
    WHERE CAST(timestamp AS DATE) = @pipeline_date
      -- CRITICAL FIX: Filter out bad charger_ids at source
      AND charger_id IS NOT NULL 
      AND LEN(RTRIM(charger_id)) > 0
      AND charger_id <> '';
    
    SET @RowsInserted = @@ROWCOUNT;
    
    -- Return results with data quality metrics
    SELECT
        @RowsInserted AS RowsWritten,
        @BadRowsRejected AS BadRowsRejected,
        CAST(@pipeline_date AS VARCHAR(10)) AS ProcessedDate,
        GETUTCDATE() AS ProcessedTimestamp;
        
END;
