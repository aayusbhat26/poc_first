CREATE OR ALTER PROCEDURE dbo.usp_Load_Gold_EV_Exceptions
(
    @pipeline_date DATE
)
AS
BEGIN
    SET NOCOUNT ON;

    DELETE FROM dbo.gold_ev_exceptions
    WHERE CAST(timestamp AS DATE) = @pipeline_date;

    DELETE FROM dbo.gold_ev_fault_timeline
    WHERE data_date = @pipeline_date;

    DELETE FROM dbo.gold_ev_packet_drop_gaps
    WHERE data_date = @pipeline_date;

    DELETE FROM dbo.gold_ev_exception_summary
    WHERE data_date = @pipeline_date;

    DELETE FROM dbo.gold_ev_charger_exception_profile
    WHERE data_date = @pipeline_date;

    INSERT INTO dbo.gold_ev_exceptions
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
        utilisation_pct,
        time_of_day_band,
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
        ExceptionReason,
        ingestion_timestamp,
        exception_category,
        exception_type,
        exception_severity
    )
    SELECT
        s.charger_id,
        s.timestamp,
        s.state,
        s.city,
        s.zone,
        s.site_type,
        s.hw_type,
        s.charger_type_category,
        s.max_power_kw,
        s.status,
        s.is_online,
        s.uptime_pct,
        s.user_id,
        s.session_duration_mins,
        s.session_dur_bucket,
        s.utilisation_pct,
        s.time_of_day_band,
        s.total_active_power_kw,
        s.voltage_phase_a_v,
        s.voltage_phase_b_v,
        s.voltage_phase_c_v,
        s.current_phase_a_a,
        s.current_phase_b_a,
        s.current_phase_c_a,
        s.connector_temp_c,
        s.ambient_temp_c,
        s.energy_delivered_kwh,
        s.session_revenue_inr,
        s.electricity_cost_inr,
        s.maintenance_cost_inr,
        s.connectivity_cost_inr,
        s.staff_cost_inr,
        s.net_margin_inr,
        s.lost_revenue_inr,
        s.initial_soc_pct,
        s.current_soc_pct,
        s.target_soc_pct,
        s.error_code,
        s.fault_severity,
        s.is_faulted,
        s.repeat_fault,
        s.mttr_estimate_mins,
        s.downtime_mins_today,
        s.customers_lost,
        s.fault_lost_revenue_inr,
        s.zone_score,
        s.peak_hour,
        x.ExceptionReason,
        GETUTCDATE(),
        x.exception_category,
        x.exception_type,
        x.exception_severity
    FROM dbo.silver_ev_operations s
    CROSS APPLY
    (
        VALUES
            (CASE WHEN s.electricity_cost_inr IS NULL THEN 'Billing cost missing' END, 'NULL_INJECTION', 'BILLING_NULL', 'High'),
            (CASE WHEN s.connector_temp_c IS NULL AND s.electricity_cost_inr IS NOT NULL THEN 'Connector temperature missing' END, 'NULL_INJECTION', 'THERMAL_SENSOR_NULL', 'Low'),
            (CASE WHEN s.ambient_temp_c IS NULL AND s.connector_temp_c IS NOT NULL AND s.electricity_cost_inr IS NOT NULL THEN 'Ambient temperature missing' END, 'NULL_INJECTION', 'AMBIENT_SENSOR_NULL', 'Low'),
            (CASE WHEN (s.current_phase_a_a IS NULL OR s.current_phase_b_a IS NULL OR s.current_phase_c_a IS NULL) AND s.electricity_cost_inr IS NOT NULL THEN 'Current sensor phase missing' END, 'NULL_INJECTION', 'CURRENT_SENSOR_NULL', 'High'),
            (CASE WHEN s.voltage_phase_a_v IS NULL AND s.voltage_phase_b_v IS NULL AND s.voltage_phase_c_v IS NULL THEN 'All phase voltages missing' END, 'NULL_INJECTION', 'VOLTAGE_SENSOR_NULL', 'High'),
            (CASE WHEN s.status = 'Charging' AND s.user_id IS NULL THEN 'User ID missing while charging' END, 'NULL_INJECTION', 'USER_ID_MISSING', 'High'),
            (CASE WHEN s.current_soc_pct IS NULL AND s.user_id IS NOT NULL THEN 'SOC missing with identified user' END, 'NULL_INJECTION', 'BMS_COMM_NULL', 'High'),
            (CASE WHEN s.is_faulted = 1 AND s.mttr_estimate_mins = 0 THEN 'MTTR estimate unavailable' END, 'NULL_INJECTION', 'MTTR_LOOKUP_NULL', 'Low'),
            (CASE WHEN s.status = 'Charging' AND s.energy_delivered_kwh = 0 THEN 'Charging session with zero energy' END, 'BUSINESS_RULE', 'ZERO_ENERGY_CHARGING', 'High'),
            (CASE WHEN s.is_faulted = 1 AND s.repeat_fault = 1 THEN 'Repeat fault occurrence' END, 'FAULT_STATE', 'REPEAT_FAULT', CASE WHEN s.fault_severity IN ('Critical', 'High') THEN 'High' ELSE 'Medium' END),
            (CASE WHEN s.is_faulted = 1 AND s.peak_hour = 1 THEN 'Fault during peak hour' END, 'FAULT_STATE', 'PEAK_HOUR_FAULT', CASE WHEN s.fault_severity = 'Critical' THEN 'Critical' ELSE 'High' END),
            (CASE WHEN s.is_faulted = 1 AND s.error_code IS NOT NULL AND s.error_code <> 'None' THEN CONCAT('Fault detected: ', s.error_code) END, 'FAULT_STATE', ISNULL(s.error_code, 'UNKNOWN_FAULT'), CASE WHEN s.fault_severity = 'Critical' THEN 'Critical' WHEN s.fault_severity = 'High' THEN 'High' ELSE 'Low' END)
    ) x(ExceptionReason, exception_category, exception_type, exception_severity)
    WHERE CAST(s.timestamp AS DATE) = @pipeline_date
      AND x.ExceptionReason IS NOT NULL;

    INSERT INTO dbo.gold_ev_fault_timeline
    (
        data_date,
        charger_id,
        fault_timestamp,
        error_code,
        fault_severity,
        is_repeat_fault,
        mttr_estimate_mins,
        downtime_mins_today,
        connector_temp_c,
        peak_hour,
        lost_revenue_inr,
        fault_lost_revenue_inr,
        customers_lost,
        zone,
        city,
        state,
        site_type,
        hw_type,
        ingestion_timestamp
    )
    SELECT
        CAST(timestamp AS DATE),
        charger_id,
        timestamp,
        error_code,
        fault_severity,
        ISNULL(repeat_fault, 0),
        mttr_estimate_mins,
        downtime_mins_today,
        connector_temp_c,
        ISNULL(peak_hour, 0),
        ISNULL(lost_revenue_inr, 0),
        ISNULL(fault_lost_revenue_inr, 0),
        ISNULL(customers_lost, 0),
        zone,
        city,
        state,
        site_type,
        hw_type,
        GETUTCDATE()
    FROM dbo.silver_ev_operations
    WHERE CAST(timestamp AS DATE) = @pipeline_date
      AND is_faulted = 1
      AND error_code IS NOT NULL
      AND error_code <> 'None';

    ;WITH gaps AS
    (
        SELECT
            s.charger_id,
            s.timestamp AS next_timestamp,
            LAG(s.timestamp) OVER (PARTITION BY s.charger_id ORDER BY s.timestamp) AS prev_timestamp,
            DATEDIFF(MINUTE, LAG(s.timestamp) OVER (PARTITION BY s.charger_id ORDER BY s.timestamp), s.timestamp) AS gap_duration_mins,
            s.session_revenue_inr,
            s.session_duration_mins,
            s.zone,
            s.city,
            s.state
        FROM dbo.silver_ev_operations s
        WHERE CAST(s.timestamp AS DATE) = @pipeline_date
    )
    INSERT INTO dbo.gold_ev_packet_drop_gaps
    (
        data_date,
        charger_id,
        expected_timestamp,
        prev_timestamp,
        next_timestamp,
        gap_duration_mins,
        estimated_lost_revenue,
        zone,
        city,
        state,
        ingestion_timestamp
    )
    SELECT
        @pipeline_date,
        charger_id,
        DATEADD(MINUTE, 15, prev_timestamp),
        prev_timestamp,
        next_timestamp,
        gap_duration_mins,
        CASE
            WHEN ISNULL(session_duration_mins, 0) > 0
            THEN ROUND((ISNULL(session_revenue_inr, 0) / session_duration_mins) * gap_duration_mins, 2)
            ELSE 0
        END,
        zone,
        city,
        state,
        GETUTCDATE()
    FROM gaps
    WHERE prev_timestamp IS NOT NULL
      AND gap_duration_mins > 15;

    DECLARE @daily_rows DECIMAL(18,4);

    SELECT @daily_rows = COUNT(*)
    FROM dbo.silver_ev_operations
    WHERE CAST(timestamp AS DATE) = @pipeline_date;

    INSERT INTO dbo.gold_ev_exception_summary
    (
        data_date,
        exception_category,
        exception_type,
        exception_severity,
        charger_count,
        exception_row_count,
        total_lost_revenue_inr,
        total_customers_lost,
        total_downtime_mins,
        pct_of_daily_rows,
        ingestion_timestamp
    )
    SELECT
        @pipeline_date,
        exception_category,
        exception_type,
        exception_severity,
        COUNT(DISTINCT charger_id),
        COUNT(*),
        SUM(ISNULL(lost_revenue_inr, 0) + ISNULL(fault_lost_revenue_inr, 0)),
        SUM(ISNULL(customers_lost, 0)),
        SUM(ISNULL(downtime_mins_today, 0)),
        CASE WHEN ISNULL(@daily_rows, 0) > 0 THEN ROUND((COUNT(*) * 100.0) / @daily_rows, 2) ELSE 0 END,
        GETUTCDATE()
    FROM dbo.gold_ev_exceptions
    WHERE CAST(timestamp AS DATE) = @pipeline_date
    GROUP BY exception_category, exception_type, exception_severity;

    INSERT INTO dbo.gold_ev_charger_exception_profile
    (
        data_date,
        charger_id,
        state,
        city,
        zone,
        hw_type,
        site_type,
        total_exceptions,
        critical_exceptions,
        high_exceptions,
        low_exceptions,
        fault_count,
        repeat_fault_count,
        billing_null_count,
        sensor_null_count,
        bms_null_count,
        user_id_null_count,
        packet_drop_count,
        total_lost_revenue_inr,
        total_downtime_mins,
        total_customers_lost,
        exception_rate_pct,
        is_high_risk,
        ingestion_timestamp
    )
    SELECT
        @pipeline_date,
        e.charger_id,
        MAX(e.state),
        MAX(e.city),
        MAX(e.zone),
        MAX(e.hw_type),
        MAX(e.site_type),
        COUNT(*) AS total_exceptions,
        SUM(CASE WHEN e.exception_severity = 'Critical' THEN 1 ELSE 0 END) AS critical_exceptions,
        SUM(CASE WHEN e.exception_severity = 'High' THEN 1 ELSE 0 END) AS high_exceptions,
        SUM(CASE WHEN e.exception_severity = 'Low' THEN 1 ELSE 0 END) AS low_exceptions,
        SUM(CASE WHEN e.exception_category = 'FAULT_STATE' THEN 1 ELSE 0 END) AS fault_count,
        SUM(CASE WHEN e.exception_type = 'REPEAT_FAULT' THEN 1 ELSE 0 END) AS repeat_fault_count,
        SUM(CASE WHEN e.exception_type = 'BILLING_NULL' THEN 1 ELSE 0 END) AS billing_null_count,
        SUM(CASE WHEN e.exception_type IN ('THERMAL_SENSOR_NULL', 'AMBIENT_SENSOR_NULL', 'CURRENT_SENSOR_NULL', 'VOLTAGE_SENSOR_NULL') THEN 1 ELSE 0 END) AS sensor_null_count,
        SUM(CASE WHEN e.exception_type IN ('BMS_COMM_NULL', 'MTTR_LOOKUP_NULL') THEN 1 ELSE 0 END) AS bms_null_count,
        SUM(CASE WHEN e.exception_type = 'USER_ID_MISSING' THEN 1 ELSE 0 END) AS user_id_null_count,
        ISNULL(pd.packet_drop_count, 0) AS packet_drop_count,
        SUM(ISNULL(e.lost_revenue_inr, 0) + ISNULL(e.fault_lost_revenue_inr, 0)) AS total_lost_revenue_inr,
        SUM(ISNULL(e.downtime_mins_today, 0)) AS total_downtime_mins,
        SUM(ISNULL(e.customers_lost, 0)) AS total_customers_lost,
        CASE WHEN ISNULL(sr.silver_rows, 0) > 0 THEN ROUND((COUNT(*) * 100.0) / sr.silver_rows, 2) ELSE 0 END AS exception_rate_pct,
        CASE
            WHEN SUM(CASE WHEN e.exception_severity IN ('Critical', 'High') THEN 1 ELSE 0 END) >= 5
              OR SUM(ISNULL(e.lost_revenue_inr, 0) + ISNULL(e.fault_lost_revenue_inr, 0)) >= 5000
            THEN 1 ELSE 0
        END AS is_high_risk,
        GETUTCDATE()
    FROM dbo.gold_ev_exceptions e
    LEFT JOIN
    (
        SELECT charger_id, COUNT(*) AS packet_drop_count
        FROM dbo.gold_ev_packet_drop_gaps
        WHERE data_date = @pipeline_date
        GROUP BY charger_id
    ) pd
        ON e.charger_id = pd.charger_id
    LEFT JOIN
    (
        SELECT charger_id, COUNT(*) AS silver_rows
        FROM dbo.silver_ev_operations
        WHERE CAST(timestamp AS DATE) = @pipeline_date
        GROUP BY charger_id
    ) sr
        ON e.charger_id = sr.charger_id
    WHERE CAST(e.timestamp AS DATE) = @pipeline_date
    GROUP BY e.charger_id, pd.packet_drop_count, sr.silver_rows;

    DECLARE @ExceptionRows INT;
    DECLARE @FaultRows INT;
    DECLARE @PacketDropRows INT;
    DECLARE @SummaryRows INT;
    DECLARE @ProfileRows INT;

    SELECT @ExceptionRows = COUNT(*)
    FROM dbo.gold_ev_exceptions
    WHERE CAST(timestamp AS DATE) = @pipeline_date;

    SELECT @FaultRows = COUNT(*)
    FROM dbo.gold_ev_fault_timeline
    WHERE data_date = @pipeline_date;

    SELECT @PacketDropRows = COUNT(*)
    FROM dbo.gold_ev_packet_drop_gaps
    WHERE data_date = @pipeline_date;

    SELECT @SummaryRows = COUNT(*)
    FROM dbo.gold_ev_exception_summary
    WHERE data_date = @pipeline_date;

    SELECT @ProfileRows = COUNT(*)
    FROM dbo.gold_ev_charger_exception_profile
    WHERE data_date = @pipeline_date;

    SELECT
        @ExceptionRows AS ExceptionRows,
        @FaultRows AS FaultRows,
        @PacketDropRows AS PacketDropRows,
        @SummaryRows AS SummaryRows,
        @ProfileRows AS ProfileRows;
END;
