# EV Telemetry POC — Remaining Pipeline Build Plan
**Author:** Aayush Bhat  
**Date:** May 23, 2026  
**Platform:** Azure Data Factory  

---

## Architecture Decision: Parent-Child Pipeline Pattern

In Azure Data Factory, the **Execute Pipeline Activity** is used to call a child pipeline from a parent. This keeps each pipeline **independent** (can be tested and run in isolation) while the parent orchestrates the full sequence.

```
PL_09_Master_Orchestration   ← PARENT (you trigger this one)
    │
    ├── Execute → PL_01_Raw_Ingestion          ✅ Already built
    ├── Execute → PL_02_Raw_To_Staging         ✅ Already built
    ├── Execute → PL_05_Staging_To_Silver      ← Build next
    ├── Execute → PL_06_KPI_Gold_Load          ← Build next
    └── Execute → PL_07_Dashboard_Refresh      ← Build next

PL_08_Incremental_Load                         ← Separate scheduled pipeline (not in master)
```

> **Why keep PL_08 outside the master?**  
> PL_08 runs on a different schedule (e.g., every 6 hours for delta loads). Including it in the daily master would cause conflicts. It runs independently and feeds directly into PL_02 onwards.

---

## Current Status

| Pipeline | Status | Physical Location |
|---|---|---|
| PL_01_Raw_Ingestion | ✅ Complete | Standalone pipeline |
| PL_02_Raw_To_Staging | ✅ Complete | Includes PL_03 DQ + PL_04 Exceptions + PL_10 Monitoring |
| PL_05_Staging_To_Silver | ❌ To Build | Standalone child pipeline |
| PL_06_KPI_Gold_Load | ❌ To Build | Standalone child pipeline |
| PL_07_Dashboard_Refresh | ❌ To Build | Standalone child pipeline |
| PL_08_Incremental_Load | ❌ To Build | Standalone scheduled pipeline |
| PL_09_Master_Orchestration | ❌ To Build | Parent pipeline (build last) |

---

## STEP 1 — SQL Setup (Run before building any pipeline)

Open your **Azure SQL Query Editor** and run these scripts first.
All pipelines depend on these tables existing before the Data Flows are built.

### 1A. Silver Table
```sql
-- Drop and recreate silver table
DROP TABLE IF EXISTS dbo.silver_ev_telemetry;

SELECT TOP 0 * INTO dbo.silver_ev_telemetry FROM dbo.stg_ev_telemetry;

ALTER TABLE dbo.silver_ev_telemetry ADD
    is_critical_fault       BIT,
    charge_efficiency_pct   DECIMAL(10,2),
    revenue_category        VARCHAR(50),
    cost_per_kwh            DECIMAL(10,4),
    profit_margin_pct       DECIMAL(10,2),
    load_timestamp          DATETIME DEFAULT GETUTCDATE();
```

### 1B. Gold KPI Table
```sql
DROP TABLE IF EXISTS dbo.gold_ev_kpi;

CREATE TABLE dbo.gold_ev_kpi (
    kpi_date                DATE,
    charger_id              VARCHAR(100),
    state                   VARCHAR(100),
    city                    VARCHAR(100),
    zone                    VARCHAR(100),
    charger_type_category   VARCHAR(100),
    total_sessions          INT,
    total_energy_kwh        DECIMAL(18,4),
    total_revenue_inr       DECIMAL(18,4),
    total_cost_inr          DECIMAL(18,4),
    net_margin_inr          DECIMAL(18,4),
    avg_charge_efficiency   DECIMAL(10,2),
    avg_uptime_pct          DECIMAL(10,2),
    fault_count             INT,
    critical_fault_count    INT,
    total_downtime_mins     INT,
    total_lost_revenue_inr  DECIMAL(18,4),
    load_timestamp          DATETIME DEFAULT GETUTCDATE(),
    CONSTRAINT PK_gold_ev_kpi PRIMARY KEY (kpi_date, charger_id)
);
```

### 1C. Watermark Table (for PL_08)
```sql
DROP TABLE IF EXISTS dbo.watermark_table;

CREATE TABLE dbo.watermark_table (
    table_name          VARCHAR(100) PRIMARY KEY,
    last_loaded_date    DATE NOT NULL
);

-- Seed with initial value
INSERT INTO dbo.watermark_table (table_name, last_loaded_date)
VALUES ('raw_ev_telemetry', '2025-01-01');
```

---

## STEP 2 — Build PL_05_Staging_To_Silver

**Purpose:** Read clean data from `stg_ev_telemetry`, apply business logic, write to `silver_ev_telemetry`.

### 2A. Create Datasets
In ADF → Datasets, create:
- **DS_Staging_EV_SQL** → Linked Service: `LS_AzureSQL` → Table: `dbo.stg_ev_telemetry`
- **DS_Silver_EV_SQL** → Linked Service: `LS_AzureSQL` → Table: `dbo.silver_ev_telemetry`

### 2B. Create Data Flow: DF_Staging_To_Silver
In ADF → Data Flows → New:

| Step | Transformation | Config |
|---|---|---|
| 1 | **Source** — name: `SourceStaging` | Dataset: `DS_Staging_EV_SQL` |
| 2 | **Derived Column** — name: `AddBusinessColumns` | See expressions below |
| 3 | **Sink** — name: `SinkSilver` | Dataset: `DS_Silver_EV_SQL`, Write: Truncate |

**Derived Column Expressions (AddBusinessColumns):**

| Column Name | Expression |
|---|---|
| `is_critical_fault` | `fault_severity == 'Critical'` |
| `charge_efficiency_pct` | `iif(isNull(energy_delivered_kwh) || isNull(session_duration_mins) || session_duration_mins == 0, toDecimal(null()), toDecimal(energy_delivered_kwh / (session_duration_mins / 60.0) / max_power_kw * 100, 10, 2))` |
| `revenue_category` | `iif(session_revenue_inr >= 500, 'High', iif(session_revenue_inr >= 200, 'Medium', 'Low'))` |
| `cost_per_kwh` | `iif(isNull(energy_delivered_kwh) || energy_delivered_kwh == 0, toDecimal(null()), toDecimal((electricity_cost_inr + maintenance_cost_inr) / energy_delivered_kwh, 10, 4))` |
| `profit_margin_pct` | `iif(isNull(session_revenue_inr) || session_revenue_inr == 0, toDecimal(null()), toDecimal(net_margin_inr / session_revenue_inr * 100, 10, 2))` |
| `load_timestamp` | `currentTimestamp()` |

> Set **Auto mapping ON** for the Sink. It will pass through all 46 original columns plus the 5 new ones.

### 2C. Create Pipeline: PL_05_Staging_To_Silver
In ADF → Pipelines → New → name: `PL_05_Staging_To_Silver`

Add these activities in order:

**Activity 1 — Execute Data Flow**
- Name: `DF_Staging_To_Silver`
- Type: Execute Data Flow
- Data Flow: `DF_Staging_To_Silver`
- Compute: 8 cores, General

**Activity 2 — Script (On Success of Activity 1)**
- Name: `success_log`
- Linked Service: `LS_AzureSQL`
- Script Type: Query
```sql
INSERT INTO dbo.pipeline_execution_logs
(PipelineName, RunID, EventStatus, Message, ExecutionTime, DataDate, RowsWritten, SourceTable, TargetTable, PipelineStage)
VALUES (
    '@{pipeline().Pipeline}',
    '@{pipeline().RunId}',
    'Success',
    'Silver load successful.',
    GETUTCDATE(),
    CAST('@{formatDateTime(adddays(utcnow(), -1), 'yyyy-MM-dd')}' AS DATE),
    @{activity('DF_Staging_To_Silver').output.runStatus.metrics.SinkSilver.rowsWritten},
    'stg_ev_telemetry',
    'silver_ev_telemetry',
    'Silver'
);
```

**Activity 3 — Script (On Failure of Activity 1)**
- Name: `failure_log`
- Linked Service: `LS_AzureSQL`
- Script Type: Query
```sql
INSERT INTO dbo.pipeline_execution_logs
(PipelineName, RunID, EventStatus, Message, ExecutionTime, DataDate, RowsWritten, SourceTable, TargetTable, PipelineStage)
VALUES (
    '@{pipeline().Pipeline}',
    '@{pipeline().RunId}',
    'Failed',
    'PL_05 failed. Check ADF Monitor for Data Flow errors.',
    GETUTCDATE(),
    CAST('@{formatDateTime(adddays(utcnow(), -1), 'yyyy-MM-dd')}' AS DATE),
    0,
    'stg_ev_telemetry',
    'silver_ev_telemetry',
    'Silver'
);
```

---

## STEP 3 — Build PL_06_KPI_Gold_Load

**Purpose:** Aggregate silver data by date and charger into daily KPI rows in `gold_ev_kpi`.

### 3A. Create Dataset
- **DS_Gold_EV_SQL** → Linked Service: `LS_AzureSQL` → Table: `dbo.gold_ev_kpi`

### 3B. Create Stored Procedure in SQL
Run this in your SQL Query Editor:

```sql
CREATE OR ALTER PROCEDURE dbo.usp_Load_Gold_KPI
    @data_date DATE
AS
BEGIN
    SET NOCOUNT ON;

    -- Remove existing records for this date (idempotent reload)
    DELETE FROM dbo.gold_ev_kpi WHERE kpi_date = @data_date;

    -- Insert aggregated KPIs
    INSERT INTO dbo.gold_ev_kpi (
        kpi_date, charger_id, state, city, zone, charger_type_category,
        total_sessions, total_energy_kwh, total_revenue_inr, total_cost_inr,
        net_margin_inr, avg_charge_efficiency, avg_uptime_pct,
        fault_count, critical_fault_count, total_downtime_mins,
        total_lost_revenue_inr, load_timestamp
    )
    SELECT
        CAST(timestamp AS DATE)             AS kpi_date,
        charger_id,
        state,
        city,
        zone,
        charger_type_category,
        COUNT(*)                            AS total_sessions,
        SUM(ISNULL(energy_delivered_kwh,0)) AS total_energy_kwh,
        SUM(ISNULL(session_revenue_inr,0))  AS total_revenue_inr,
        SUM(ISNULL(electricity_cost_inr,0)
          + ISNULL(maintenance_cost_inr,0)
          + ISNULL(connectivity_cost_inr,0)
          + ISNULL(staff_cost_inr,0))       AS total_cost_inr,
        SUM(ISNULL(net_margin_inr,0))       AS net_margin_inr,
        AVG(charge_efficiency_pct)          AS avg_charge_efficiency,
        AVG(CAST(uptime_pct AS DECIMAL(10,2))) AS avg_uptime_pct,
        SUM(CASE WHEN is_faulted = 1 THEN 1 ELSE 0 END)         AS fault_count,
        SUM(CASE WHEN is_critical_fault = 1 THEN 1 ELSE 0 END)  AS critical_fault_count,
        SUM(ISNULL(downtime_mins_today,0))  AS total_downtime_mins,
        SUM(ISNULL(fault_lost_revenue_inr,0)) AS total_lost_revenue_inr,
        GETUTCDATE()
    FROM dbo.silver_ev_telemetry
    WHERE CAST(timestamp AS DATE) = @data_date
    GROUP BY
        CAST(timestamp AS DATE), charger_id, state, city, zone, charger_type_category;
END;
```

### 3C. Create Pipeline: PL_06_KPI_Gold_Load
In ADF → Pipelines → New → name: `PL_06_KPI_Gold_Load`

**Activity 1 — Stored Procedure**
- Name: `SP_Load_Gold_KPI`
- Type: Stored Procedure
- Linked Service: `LS_AzureSQL`
- Stored Procedure Name: `dbo.usp_Load_Gold_KPI`
- Parameters:
  - Name: `data_date`
  - Type: `String`
  - Value: `@{formatDateTime(adddays(utcnow(), -1), 'yyyy-MM-dd')}`

**Activity 2 — Script (On Success)**
- Name: `success_log`
```sql
INSERT INTO dbo.pipeline_execution_logs
(PipelineName, RunID, EventStatus, Message, ExecutionTime, DataDate, RowsWritten, SourceTable, TargetTable, PipelineStage)
VALUES (
    '@{pipeline().Pipeline}',
    '@{pipeline().RunId}',
    'Success',
    'Gold KPI aggregation successful.',
    GETUTCDATE(),
    CAST('@{formatDateTime(adddays(utcnow(), -1), 'yyyy-MM-dd')}' AS DATE),
    0,
    'silver_ev_telemetry',
    'gold_ev_kpi',
    'Gold'
);
```

**Activity 3 — Script (On Failure)**
- Name: `failure_log`
```sql
INSERT INTO dbo.pipeline_execution_logs
(PipelineName, RunID, EventStatus, Message, ExecutionTime, DataDate, RowsWritten, SourceTable, TargetTable, PipelineStage)
VALUES (
    '@{pipeline().Pipeline}',
    '@{pipeline().RunId}',
    'Failed',
    'PL_06 failed. Check ADF Monitor for Stored Procedure errors.',
    GETUTCDATE(),
    CAST('@{formatDateTime(adddays(utcnow(), -1), 'yyyy-MM-dd')}' AS DATE),
    0,
    'silver_ev_telemetry',
    'gold_ev_kpi',
    'Gold'
);
```

---

## STEP 4 — Build PL_07_Dashboard_Refresh

**Purpose:** Trigger Power BI dataset refresh via REST API after Gold data is ready.

### 4A. Pre-requisites (Power BI Setup)
Before building this pipeline, collect these values from Power BI Service:
1. Go to Power BI Service → Your Workspace → Your Dataset → Settings → API
2. Note your **Workspace ID** (GUID in the URL)
3. Note your **Dataset ID** (GUID in the URL)
4. In ADF → Manage → Linked Services → create a new **Web** linked service named `LS_PowerBI_API` with Base URL: `https://api.powerbi.com`
5. Authentication: Service Principal (register an App in Azure AD with Power BI API permissions)

### 4B. Create Pipeline: PL_07_Dashboard_Refresh
In ADF → Pipelines → New → name: `PL_07_Dashboard_Refresh`

**Activity 1 — Web Activity**
- Name: `Trigger_PBI_Refresh`
- Type: Web
- URL: `https://api.powerbi.com/v1.0/myorg/groups/{YOUR_WORKSPACE_ID}/datasets/{YOUR_DATASET_ID}/refreshes`
- Method: `POST`
- Body: `{}`
- Authentication: MSI or Service Principal

**Activity 2 — Script (On Success)**
- Name: `success_log`
```sql
INSERT INTO dbo.pipeline_execution_logs
(PipelineName, RunID, EventStatus, Message, ExecutionTime, DataDate, RowsWritten, SourceTable, TargetTable, PipelineStage)
VALUES (
    '@{pipeline().Pipeline}',
    '@{pipeline().RunId}',
    'Success',
    'Power BI dataset refresh triggered successfully.',
    GETUTCDATE(),
    CAST('@{formatDateTime(adddays(utcnow(), -1), 'yyyy-MM-dd')}' AS DATE),
    0,
    'gold_ev_kpi',
    'PowerBI_Dataset',
    'Reporting'
);
```

**Activity 3 — Script (On Failure)**
- Name: `failure_log`
```sql
INSERT INTO dbo.pipeline_execution_logs
(PipelineName, RunID, EventStatus, Message, ExecutionTime, DataDate, RowsWritten, SourceTable, TargetTable, PipelineStage)
VALUES (
    '@{pipeline().Pipeline}',
    '@{pipeline().RunId}',
    'Failed',
    'PL_07 failed. Power BI refresh API call failed.',
    GETUTCDATE(),
    CAST('@{formatDateTime(adddays(utcnow(), -1), 'yyyy-MM-dd')}' AS DATE),
    0,
    'gold_ev_kpi',
    'PowerBI_Dataset',
    'Reporting'
);
```

---

## STEP 5 — Build PL_08_Incremental_Load

**Purpose:** Load only the delta (new records since last run) instead of regenerating all data. Runs on its own schedule — NOT triggered by PL_09.

### 5A. How it differs from PL_01
| | PL_01 (Full Daily) | PL_08 (Incremental Delta) |
|---|---|---|
| Trigger | Daily via PL_09 | Separate schedule (every 6 hrs) |
| What it generates | Yesterday's full dataset | Only new rows since watermark |
| Watermark | Checks if date already loaded | Reads + updates watermark_table |
| Databricks notebook | `data_generation_previous_day` | New notebook: `data_generation_delta` |

### 5B. Create Databricks Notebook: data_generation_delta
In Databricks, create a new notebook at `/Users/work.aayush.bhat@gmail.com/data_generation_delta`

This notebook should:
1. Accept a parameter `last_loaded_date`
2. Generate only records with `timestamp > last_loaded_date`
3. Write to a subfolder in ADLS: `/delta/ev_telemetry_{timestamp}/`

### 5C. Create Pipeline: PL_08_Incremental_Load

**Activity 1 — Lookup Watermark**
- Name: `Lookup_Watermark`
- Type: Lookup
- Dataset: `DS_Sink_EV_SQL`
- Query:
```sql
SELECT last_loaded_date FROM dbo.watermark_table
WHERE table_name = 'raw_ev_telemetry';
```

**Activity 2 — Databricks Notebook (On Success of Activity 1)**
- Name: `Generate_Delta_EV_Telemetry`
- Type: DatabricksNotebook
- Notebook Path: `/Users/work.aayush.bhat@gmail.com/data_generation_delta`
- Base Parameters:
  - `last_loaded_date`: `@{activity('Lookup_Watermark').output.firstRow.last_loaded_date}`

**Activity 3 — Copy Activity (On Success of Activity 2)**
- Name: `CP_ACT_DELTA_TO_RAW`
- Source: `DS_Source_EV_JSON` (pointing to `/delta/` folder in ADLS)
- Sink: `DS_Sink_EV_SQL` (raw_ev_telemetry, writeBehavior: insert, NO pre-copy delete)

**Activity 4 — Script: Update Watermark (On Success of Activity 3)**
- Name: `Update_Watermark`
```sql
UPDATE dbo.watermark_table
SET last_loaded_date = CAST(GETUTCDATE() AS DATE)
WHERE table_name = 'raw_ev_telemetry';

INSERT INTO dbo.pipeline_execution_logs
(PipelineName, RunID, EventStatus, Message, ExecutionTime, DataDate, RowsWritten, SourceTable, TargetTable, PipelineStage)
VALUES (
    '@{pipeline().Pipeline}',
    '@{pipeline().RunId}',
    'Success',
    'Incremental delta load successful.',
    GETUTCDATE(),
    CAST(GETUTCDATE() AS DATE),
    @{activity('CP_ACT_DELTA_TO_RAW').output.rowsCopied},
    'ADLS_Delta',
    'raw_ev_telemetry',
    'Raw_Delta'
);
```

**Activity 5 — Script: Log Failure (On Failure of Activity 3)**
- Name: `failure_log`
```sql
INSERT INTO dbo.pipeline_execution_logs
(PipelineName, RunID, EventStatus, Message, ExecutionTime, DataDate, RowsWritten, SourceTable, TargetTable, PipelineStage)
VALUES (
    '@{pipeline().Pipeline}',
    '@{pipeline().RunId}',
    'Failed',
    'PL_08 incremental load failed.',
    GETUTCDATE(),
    CAST(GETUTCDATE() AS DATE),
    0,
    'ADLS_Delta',
    'raw_ev_telemetry',
    'Raw_Delta'
);
```

### 5D. Add Trigger to PL_08
- Go to PL_08 → Add Trigger → New/Edit
- Type: **Schedule**
- Recurrence: Every **6 hours**
- Start time: `06:00 UTC`

---

## STEP 6 — Build PL_09_Master_Orchestration (Parent Pipeline)

**Purpose:** Single pipeline that triggers PL_01 → PL_02 → PL_05 → PL_06 → PL_07 in sequence. This is the only pipeline you need to trigger manually or schedule daily.

### 6A. Create Pipeline: PL_09_Master_Orchestration
In ADF → Pipelines → New → name: `PL_09_Master_Orchestration`

Add **5 Execute Pipeline activities** chained with **On Success** dependencies:

| Activity Name | Type | Child Pipeline | Wait for Completion |
|---|---|---|---|
| `Run_PL01_Raw_Ingestion` | Execute Pipeline | `PL_01_Raw_Ingestion` | ✅ Yes |
| `Run_PL02_Raw_To_Staging` | Execute Pipeline | `PL_02_Raw_To_Staging` | ✅ Yes |
| `Run_PL05_Staging_To_Silver` | Execute Pipeline | `PL_05_Staging_To_Silver` | ✅ Yes |
| `Run_PL06_KPI_Gold_Load` | Execute Pipeline | `PL_06_KPI_Gold_Load` | ✅ Yes |
| `Run_PL07_Dashboard_Refresh` | Execute Pipeline | `PL_07_Dashboard_Refresh` | ✅ Yes |

**Dependency chain:**
```
Run_PL01 --[On Success]--> Run_PL02 --[On Success]--> Run_PL05 --[On Success]--> Run_PL06 --[On Success]--> Run_PL07
```

### 6B. Add Daily Trigger to PL_09
- Go to PL_09 → Add Trigger → New/Edit
- Type: **Schedule**
- Recurrence: Every **1 day**
- Start time: `02:00 UTC` (runs after midnight so yesterday's data is fully available)

---

## Build Order Summary

Follow this exact sequence to avoid dependency errors:

```
1.  Run all SQL scripts (Step 1A, 1B, 1C)
2.  Create Datasets: DS_Staging_EV_SQL, DS_Silver_EV_SQL, DS_Gold_EV_SQL
3.  Build DF_Staging_To_Silver (Data Flow)
4.  Build PL_05_Staging_To_Silver
5.  Build PL_06_KPI_Gold_Load (needs stored procedure first)
6.  Build PL_07_Dashboard_Refresh
7.  Build PL_08_Incremental_Load (independent, add its own trigger)
8.  Build PL_09_Master_Orchestration (build last — references all others)
9.  Add daily trigger to PL_09
10. Publish All
```

---

## Testing Plan

After each pipeline is built, test it **individually** before wiring it into PL_09:

| Pipeline | Test Method | Verification Query |
|---|---|---|
| PL_05 | Trigger Now | `SELECT COUNT(*) FROM dbo.silver_ev_telemetry` |
| PL_06 | Trigger Now | `SELECT COUNT(*) FROM dbo.gold_ev_kpi` |
| PL_07 | Trigger Now | Check Power BI Service → Dataset → Refresh History |
| PL_08 | Trigger Now | `SELECT * FROM dbo.watermark_table` |
| PL_09 | Trigger Now | `SELECT * FROM dbo.pipeline_execution_logs ORDER BY ExecutionTime DESC` |

---

## Final Architecture (Post-Build)

```
                    ┌─────────────────────────────┐
                    │   PL_09_Master_Orchestration  │  ← Daily trigger @ 02:00 UTC
                    └──────────────┬──────────────┘
                                   │
              ┌────────────────────▼────────────────────┐
              │         Execute Pipeline (child)          │
              │                                           │
              │  PL_01 → PL_02 → PL_05 → PL_06 → PL_07  │
              └───────────────────────────────────────────┘

                    ┌─────────────────────────────┐
                    │   PL_08_Incremental_Load      │  ← Independent trigger every 6 hrs
                    └─────────────────────────────┘

Data Flow:
Databricks → ADLS Gen2 → raw_ev_telemetry → stg_ev_telemetry
          → silver_ev_telemetry → gold_ev_kpi → Power BI Dashboard
```
