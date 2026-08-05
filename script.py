from openpyxl import Workbook
from openpyxl.styles import (
    Font,
    PatternFill,
    Alignment,
    Border,
    Side
)
from openpyxl.utils import get_column_letter

# =============================================================================
# WORKBOOK SETUP
# =============================================================================

wb = Workbook()

# =============================================================================
# COLOR PALETTE
# =============================================================================

DARK_BLUE = "1F3864"
MID_BLUE = "2E5F9E"
LIGHT_BLUE = "BDD7EE"

WHITE = "FFFFFF"

GREY_LIGHT = "F2F2F2"

GREEN_FILL = "E2EFDA"
AMBER_FILL = "FFF2CC"
RED_FILL = "FFE0E0"

# =============================================================================
# COMMON STYLES
# =============================================================================

STATUS_BG = {
    "✅ Done": GREEN_FILL,
    "🔄 In Progress": AMBER_FILL,
    "⏳ Pending": LIGHT_BLUE,
    "⏳ Planned": LIGHT_BLUE
}

ROW_BG = [WHITE, GREY_LIGHT]

SEVERITY_BG = {
    "🔴 Critical": RED_FILL,
    "🟡 Warning": AMBER_FILL
}

PRIORITY_BG = {
    "🔴 High": RED_FILL,
    "🟡 Medium": AMBER_FILL,
    "🟢 Low": GREEN_FILL
}

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def header_cell(
    ws,
    row,
    col,
    value,
    bg=MID_BLUE,
    fg=WHITE,
    bold=True,
    size=10,
    wrap=False,
    halign="center"
):
    cell = ws.cell(row=row, column=col, value=value)

    cell.font = Font(
        name="Arial",
        bold=bold,
        color=fg,
        size=size
    )

    cell.fill = PatternFill(
        fill_type="solid",
        start_color=bg
    )

    cell.alignment = Alignment(
        horizontal=halign,
        vertical="center",
        wrap_text=wrap
    )

    return cell


def data_cell(
    ws,
    row,
    col,
    value,
    bg=None,
    bold=False,
    size=10,
    halign="left",
    wrap=True,
    color="000000"
):
    cell = ws.cell(row=row, column=col, value=value)

    cell.font = Font(
        name="Arial",
        bold=bold,
        color=color,
        size=size
    )

    if bg:
        cell.fill = PatternFill(
            fill_type="solid",
            start_color=bg
        )

    cell.alignment = Alignment(
        horizontal=halign,
        vertical="center",
        wrap_text=wrap
    )

    return cell


def apply_border(ws, min_row, max_row, min_col, max_col):
    side = Side(style="thin", color="BFBFBF")

    border = Border(
        left=side,
        right=side,
        top=side,
        bottom=side
    )

    for row in range(min_row, max_row + 1):
        for col in range(min_col, max_col + 1):
            ws.cell(row=row, column=col).border = border


def create_title(ws, title, subtitle=None):
    ws.merge_cells("A1:J1")

    title_cell = ws["A1"]
    title_cell.value = title

    title_cell.font = Font(
        name="Arial",
        bold=True,
        size=14,
        color=WHITE
    )

    title_cell.fill = PatternFill(
        fill_type="solid",
        start_color=DARK_BLUE
    )

    title_cell.alignment = Alignment(
        horizontal="center",
        vertical="center"
    )

    ws.row_dimensions[1].height = 36

    if subtitle:
        ws.merge_cells("A2:J2")

        subtitle_cell = ws["A2"]
        subtitle_cell.value = subtitle

        subtitle_cell.font = Font(
            name="Arial",
            italic=True,
            size=10,
            color=WHITE
        )

        subtitle_cell.fill = PatternFill(
            fill_type="solid",
            start_color=MID_BLUE
        )

        subtitle_cell.alignment = Alignment(
            horizontal="center",
            vertical="center"
        )

        ws.row_dimensions[2].height = 20


# =============================================================================
# SHEET 1 — PROJECT PROGRESS LOG
# =============================================================================

ws1 = wb.active
ws1.title = "Project Progress Log"

create_title(
    ws1,
    "EV Telemetry Data Engineering POC — Project Progress Tracker",
    "Azure Data Factory | Azure SQL | ADLS Gen2 | Databricks | Power BI"
)

headers = [
    "Date",
    "Day",
    "Phase / Sprint",
    "Activities Completed",
    "Pipelines / Artefacts",
    "Key Decisions & Notes",
    "Status",
    "% Complete\n(Overall)",
    "Blockers /\nRisks",
    "Next Steps"
]

column_widths = [14, 12, 22, 52, 30, 44, 14, 14, 30, 36]

for index, (header, width) in enumerate(zip(headers, column_widths), start=1):
    header_cell(
        ws1,
        row=3,
        col=index,
        value=header,
        wrap=True
    )

    ws1.column_dimensions[get_column_letter(index)].width = width

ws1.row_dimensions[3].height = 36

# =============================================================================
# SAMPLE DATA
# =============================================================================

rows = [
    (
        "13-May-2026",
        "Wednesday",
        "Discovery & Planning",
        "Read and analysed the project requirements PDF. Understood end-to-end EV telemetry data flow. Identified source systems, data schema, and business KPIs. Defined Medallion Architecture layers (Raw → Staging → Silver → Gold).",
        "—",
        "Agreed on Azure stack: ADF, ADLS Gen2, Azure SQL, Databricks, Power BI. Decided on Medallion Architecture pattern.",
        "✅ Done",
        "5%",
        "—",
        "Begin architecture diagram design"
    ),
    (
        "18-May-2026",
        "Monday",
        "Deep Dive — Pipeline Design",
        "Revisited requirements PDF with focus on individual pipeline flows. Mapped each pipeline's source, target, transformation logic, DQ rules, and dependencies. Identified exception scenarios from data_gen.py.",
        "—",
        "Confirmed pipeline execution order: PL_01 → PL_03 → PL_02 → PL_05 → PL_06 → PL_04. Decided on modular pipeline approach — each pipeline single responsibility.",
        "✅ Done",
        "10%",
        "—",
        "Start architecture diagram"
    ),
    (
        "19-May-2026",
        "Tuesday",
        "Architecture Design",
        "Created high-level architecture diagram covering entire pipeline suite. Designed component interaction diagrams for ADLS, ADF, Azure SQL, Databricks. Mapped data flow from ADLS landing zone through to Gold layer.",
        "Architecture Diagrams (HLD)",
        "Architecture reviewed and approved. Confirmed dataset and linked service names: DS_Source_EV_JSON, DS_Sink_EV_SQL, DS_Staging_EV_SQL, LS_AzureSQL.",
        "✅ Done",
        "18%",
        "—",
        "Complete per-pipeline architecture and wireframes"
    ),
    (
        "20-May-2026",
        "Wednesday",
        "Per-Pipeline Architecture\n+ Power BI Wireframing",
        "Built individual architecture diagrams for each pipeline (PL_01 to PL_06). Presented updated Power BI dashboard wireframes covering 6 pages: KPI Overview, Zone Intelligence, Charger Operations, Fault & Revenue Impact, Session Analytics, Charger Diagnostics.",
        "each_pipeline_flow.mermaid\nPower BI Wireframes",
        "Power BI page structure finalised. Confirmed gold table requirements to support all dashboard visuals. Stakeholder sign-off on wireframes received.",
        "✅ Done",
        "25%",
        "—",
        "Begin pipeline development — start with PL_01"
    ),
    (
        "21-May-2026",
        "Thursday",
        "PL_01 — Raw Ingestion",
        "Built PL_01_Raw_Ingestion. Implemented Databricks notebook trigger for EV telemetry generation. Configured Copy Activity (ADLS JSON → raw_ev_telemetry). Added idempotency logic: Check Max Timestamp → If Condition → Check ADLS File Exists. Added success, skip, and failure logging.",
        "PL_01_Raw_Ingestion\n(p_01.json)",
        "46-column JSON schema fully mapped. Resolved preCopyScript limitation — moved to separate Script activity. Added runIf on Databricks to prevent re-generation on retry.",
        "✅ Done",
        "42%",
        "—",
        "Build PL_02 Raw → Staging"
    ),
    (
        "22-May-2026",
        "Friday",
        "PL_02 — Raw to Staging",
        "Built PL_02_Raw_To_Staging. Configured ADF Data Flow (dataflow1) to move data from raw_ev_telemetry to stg_ev_telemetry. Added Validate_Staging_Row_Count Lookup activity. Implemented success and failure logging.",
        "PL_02_Raw_To_Staging\n(p_02.json)",
        "Removed dq_validation_results INSERT from PL_02 — DQ responsibility moved to PL_03. Removed SinkExceptions reference. PL_02 now only handles staging load and logging.",
        "✅ Done",
        "55%",
        "—",
        "Build PL_05 Staging → Silver"
    ),
    (
        "23-May-2026",
        "Saturday",
        "PL_05 — Staging to Silver",
        "Built PL_05_Staging_To_Silver. Wrote usp_Load_Silver_EV_Operations stored procedure with full ISNULL guards and 10 derived columns (IsCriticalFault, ChargeEfficiency, RevenueCategory, FaultCategory, HealthScore, TotalCostINR, ProfitMarginPct, RevenuePerKwh, CostPerKwh, SoCDelta, IsHighUtilisation, IsOverheating, CustomerImpactScore). Ran end-to-end pipeline — silver_ev_operations loaded with 25,204 rows.",
        "PL_05_Staging_To_Silver\n(p_05.json)\nusp_Load_Silver_EV_Operations",
        "Identified Inactive SP_Load_Silver dead code — retained as inactive for reference. Fixed Lookup1 dataset from DS_Staging_EV_SQL → DS_Sink_EV_SQL. SP updated to accept @pipeline_date parameter. NULL handling strategy finalised: safe defaults (0/100) for derived fields, real sensor NULLs preserved for Gold layer detection.",
        "✅ Done",
        "65%",
        "—",
        "Build PL_03 Data Quality"
    ),
    (
        "24-May-2026",
        "Sunday",
        "PL_03 — Data Quality\n+ PL_04 Started",
        "Built PL_03_Data_Quality_Raw with 6 sequential DQ Script activities (row count, NULL checks, range validation, status values, timestamp format, duplicate detection). Each check writes to dq_validation_results. Logic App alert integrated. Started PL_04_Exception_Handling — Lookup, threshold check, breach/success logging, Logic App alert.",
        "PL_03_Data_Quality_Raw\n(p_03.json)\nPL_04_Exception_Handling\n(p_04.json — partial)",
        "DQ checks extracted out of PL_01 and PL_02 — both pipelines cleaned up. Confirmed 70% exception rate threshold for PL_04. Logic App URL configured in both PL_03 and PL_04.",
        "✅ Done",
        "78%",
        "Manager approval pending for PL_03/PL_04 linking",
        "Complete PL_04 with Gold exception tables"
    ),
    (
        "25-May-2026",
        "Monday",
        "PL_04 — Exception Handling\n+ Gold Exception Layer",
        "Completed PL_04. Designed 5-table Gold exception layer. Created gold_ev_exceptions (altered), gold_ev_exception_summary, gold_ev_fault_timeline, gold_ev_charger_exception_profile, gold_ev_packet_drop_gaps. Wrote usp_Load_Gold_EV_Exceptions SP (14 INSERT blocks + 2 rollups). Built PL_06_Silver_To_Gold_Exceptions. Updated PL_00 master chain to include PL_03, PL_06, PL_04. Backfilled exception data for 2026-05-18 and 2026-05-23. Verified: ExceptionRows=34,685, FaultRows=15,700, PacketDropRows=25,055, SummaryRows=12, ProfileRows=177.",
        "PL_04_Exception_Handling\n(p_04.json — final)\nPL_06_Silver_To_Gold_Exceptions\n(p_06.json)\nPL_00_Master_Orchestration\n(p_master.json — updated)\nusp_Load_Gold_EV_Exceptions\n5 Gold exception tables",
        "Root cause found: rollup was filtering on ingestion_timestamp instead of timestamp — fixed to CAST(timestamp AS DATE). MTTR NULL detection changed from IS NULL to = 0 due to Silver SP defaulting NULLs. Full 6-pipeline chain finalised: PL_01 → PL_03 → PL_02 → PL_05 → PL_06 → PL_04.",
        "✅ Done",
        "88%",
        "—",
        "Import all updated JSONs into ADF and publish"
    ),
    (
        "26-May-2026",
        "Tuesday",
        "ADF Import & Publish",
        "Import all updated pipeline JSONs into ADF Studio. Import p_01.json, p_02.json, p_03.json, p_04.json, p_05.json, p_06.json, p_master.json. Publish All. Verify pipeline canvas shows correct dependency chain.",
        "All 7 pipeline JSONs\nADF Studio",
        "Planned: verify PL_06 SP_Load_Gold_Exceptions Lookup activity reads all 5 row counts correctly from SP RETURN SELECT.",
        "⏳ Planned",
        "90%",
        "—",
        "Build PL_07 Power BI Refresh"
    ),
    (
        "27-May-2026",
        "Wednesday",
        "PL_07 — Power BI Refresh",
        "Build PL_07_PowerBI_Refresh pipeline. Configure Web Activity to call Power BI REST API dataset refresh endpoint. Add polling logic to check refresh status. Implement success and failure logging. Link into master orchestration after PL_04.",
        "PL_07_PowerBI_Refresh\n(p_07.json)",
        "Planned: Power BI Premium or PPU workspace required for REST API refresh. Service Principal authentication for ADF → Power BI. Dataset ID and workspace ID to be captured from Power BI portal.",
        "⏳ Planned",
        "92%",
        "Power BI workspace credentials needed",
        "Build PL_08 Incremental Load"
    ),
    (
        "28-May-2026",
        "Thursday",
        "PL_08 — Incremental Load",
        "Build PL_08_Incremental_Load pipeline. Create watermark table in Azure SQL to track last loaded timestamp per source. Configure ADF pipeline to read only new rows since last watermark. Update watermark on successful load. Test with backfill scenario.",
        "PL_08_Incremental_Load\n(p_08.json)\nwatermark_table (SQL)",
        "Planned: watermark approach using MAX(timestamp) per charger_id. Handles late-arriving data and gap fills. Replaces full-date DELETE+INSERT pattern for high-volume scenarios.",
        "⏳ Planned",
        "94%",
        "—",
        "Build PL_09 Pipeline Monitoring"
    ),
    (
        "29-May-2026",
        "Friday",
        "PL_09 — Pipeline Monitoring",
        "Build PL_09_Pipeline_Monitoring pipeline. Create monitoring queries on pipeline_execution_logs to detect stale runs, repeated failures, and long-running pipelines. Configure scheduled trigger (every 6 hours). Add Logic App alert for any pipeline that has not run successfully within 26 hours.",
        "PL_09_Pipeline_Monitoring\n(p_09.json)",
        "Planned: monitoring checks — last successful run per pipeline, consecutive failure count, average run duration vs threshold. Separate from PL_04 exception monitoring (PL_09 monitors the pipelines themselves, not the data).",
        "⏳ Planned",
        "96%",
        "—",
        "Begin end-to-end test runs"
    ),
    (
        "30-May-2026",
        "Saturday",
        "End-to-End Test Run 1",
        "Trigger PL_00_Master_Orchestration for pipeline_date = 2026-05-29. Monitor all child pipelines in ADF Monitor. Verify raw_ev_telemetry, stg_ev_telemetry, silver_ev_operations, all 5 gold exception tables populated correctly. Check pipeline_execution_logs and dq_validation_results.",
        "PL_00 Full Chain\n(All 9 pipelines)",
        "Planned: capture any first-run errors — dataset references, SP parameter mismatches, Logic App trigger validation.",
        "⏳ Planned",
        "97%",
        "Potential first-run config issues",
        "Fix issues found in Run 1, proceed to Run 2"
    ),
    (
        "01-Jun-2026",
        "Monday",
        "End-to-End Test Run 2\n+ Bug Fixes",
        "Re-run PL_00 after fixes from Run 1. Validate idempotency — run same date twice and confirm row counts unchanged. Test PL_01 skip logic. Validate PL_03 DQ alerts. Test PL_04 breach scenario by manually inserting high exception rate into gold_ev_exception_summary.",
        "PL_00 Full Chain\n(All 9 pipelines)",
        "Planned: breach test — manually set pct_of_daily_rows > 30 for one category and verify Logic App email fires with correct breakdown (CriticalCount, FaultCount, NullCount).",
        "⏳ Planned",
        "98%",
        "—",
        "Final clean validation run"
    ),
    (
        "02-Jun-2026",
        "Tuesday",
        "End-to-End Test Run 3\n+ Sign-Off",
        "Final clean run of PL_00 for a fresh pipeline_date. Validate all pipeline_execution_logs show Success. Confirm Power BI data model connects to silver and all 5 gold exception tables. Configure daily scheduled trigger at 02:00 UTC. Prepare demo for stakeholder sign-off.",
        "PL_00 Full Chain\nPower BI Report\nDaily Trigger",
        "Planned: present full data flow from ADLS landing → Power BI dashboard in stakeholder demo. Hand over runbook and architecture documentation.",
        "⏳ Planned",
        "100%",
        "—",
        "Schedule daily trigger, hand over to operations"
    )
]

for idx, row_data in enumerate(rows):
    row_num = idx + 4

    ws1.row_dimensions[row_num].height = 70

    bg = ROW_BG[idx % 2]

    for col_num, value in enumerate(row_data, start=1):

        # Status Column
        if col_num == 7:
            status_cell = ws1.cell(
                row=row_num,
                column=col_num,
                value=value
            )

            status_cell.font = Font(
                name="Arial",
                bold=True,
                size=10
            )

            status_cell.fill = PatternFill(
                fill_type="solid",
                start_color=STATUS_BG.get(value, WHITE)
            )

            status_cell.alignment = Alignment(
                horizontal="center",
                vertical="center",
                wrap_text=True
            )

        else:
            data_cell(
                ws1,
                row=row_num,
                col=col_num,
                value=value,
                bg=bg,
                bold=(col_num in [1, 3]),
                halign="center" if col_num in [1, 2, 3, 8] else "left",
                color=MID_BLUE if col_num == 8 else "000000"
            )

apply_border(ws1, 3, len(rows) + 3, 1, 10)

ws1.freeze_panes = "A4"

# =============================================================================
# SHEET 2 — PIPELINE SUMMARY
# =============================================================================

ws2 = wb.create_sheet("Pipeline Summary")

ws2.merge_cells("A1:G1")

title2 = ws2["A1"]
title2.value = "ADF Pipeline Summary — EV Telemetry POC"

title2.font = Font(
    name="Arial",
    bold=True,
    size=13,
    color=WHITE
)

title2.fill = PatternFill(
    fill_type="solid",
    start_color=DARK_BLUE
)

title2.alignment = Alignment(
    horizontal="center",
    vertical="center"
)

pipeline_headers = [
    "Pipeline",
    "Type",
    "Source → Target",
    "Key Activities",
    "Status",
    "Date Completed",
    "Notes"
]

pipeline_widths = [28, 28, 32, 52, 16, 18, 40]

for index, (header, width) in enumerate(
    zip(pipeline_headers, pipeline_widths),
    start=1
):
    header_cell(ws2, 2, index, header, wrap=True)
    ws2.column_dimensions[get_column_letter(index)].width = width

ws2.row_dimensions[2].height = 36

pipeline_data = [
    (
        "PL_01_Raw_Ingestion",
        "Batch — Raw Ingestion",
        "ADLS Landing → raw_ev_telemetry",
        "Check Max Timestamp → If Condition → Check ADLS File Exists → Generate EV Telemetry (Databricks) → Delete Raw For Date → Copy Activity → Row Count Lookup → Log Success/Skip/Failure",
        "✅ Done",
        "21-May-2026",
        "Idempotent. Skips if data already exists for the date. runIf guards Databricks re-run on retry. 46-column JSON schema."
    ),
    (
        "PL_02_Raw_To_Staging",
        "Batch — Staging Load",
        "raw_ev_telemetry → stg_ev_telemetry",
        "Execute Data Flow (dataflow1) → Validate Staging Row Count → Success Log / Failure Log",
        "✅ Done",
        "22-May-2026",
        "Data Flow handles NULL pass-through. Zero-row THROW guards staging quality. DQ removed — belongs in PL_03."
    ),
    (
        "PL_03_Data_Quality_Raw",
        "DQ Validation",
        "raw_ev_telemetry → dq_validation_results",
        "6 sequential Script activities: Row Count Check, NULL Critical Fields, Voltage Range, Status Values, Timestamp Format, Duplicate Detection → Log Pass/Fail → Send Alert (Logic App) on failure",
        "✅ Done",
        "24-May-2026",
        "Runs after PL_01, before PL_02. Writes pass/fail to dq_validation_results. Logic App email on any DQ failure."
    ),
    (
        "PL_04_Exception_Handling",
        "Monitoring & Alerting",
        "gold_ev_exception_summary → pipeline_execution_logs + Logic App",
        "Lookup Exception Rate (queries gold_ev_exception_summary) → Check Threshold (MaxRate > 70% OR CriticalCount > 0) → Log OK / Log Breach → Send Exception Alert (Logic App)",
        "✅ Done",
        "25-May-2026",
        "Runs after PL_06. Monitors 5-table gold exception layer. Fires Logic App with per-category breakdown: ExceptionCount, CriticalCount, FaultCount, NullCount, TotalLostRevenue."
    ),
    (
        "PL_05_Staging_To_Silver",
        "Batch — Silver Load",
        "stg_ev_telemetry → silver_ev_operations",
        "SP_Load_Silver (Inactive — reference only) → Lookup1 calls usp_Load_Silver_EV_Operations(@pipeline_date) → Success Log / Failure Log",
        "✅ Done",
        "23-May-2026",
        "SP adds 13 derived columns. ISNULL guards on 11 impact fields. Real sensor/billing NULLs preserved for Gold detection. DELETE + INSERT idempotency by pipeline_date."
    ),
    (
        "PL_06_Silver_To_Gold_Exceptions",
        "Batch — Gold Load",
        "silver_ev_operations → 5 Gold Exception Tables",
        "Lookup calls usp_Load_Gold_EV_Exceptions(@pipeline_date) → Success Log / Failure Log. SP performs: 8× NULL_INJECTION, FAULT_STATE, LOGICAL_ANOMALY, PACKET_DROP_GAP inserts + 2 rollup aggregations.",
        "✅ Done",
        "25-May-2026",
        "Populates: gold_ev_exceptions, gold_ev_fault_timeline, gold_ev_packet_drop_gaps, gold_ev_exception_summary, gold_ev_charger_exception_profile. Must run before PL_04."
    ),
    (
        "PL_07_PowerBI_Refresh",
        "API — Power BI Refresh",
        "ADF → Power BI REST API",
        "Web Activity (POST to Power BI dataset refresh endpoint) → Poll refresh status → Success Log / Failure Log",
        "⏳ Planned",
        "27-May-2026",
        "Triggers Power BI dataset refresh after Gold layer is loaded. Requires Service Principal auth and Power BI Premium/PPU workspace."
    ),
    (
        "PL_08_Incremental_Load",
        "Batch — Incremental",
        "raw_ev_telemetry → silver (incremental)",
        "Read watermark table → Filter new rows since last watermark → Load → Update watermark on success → Log",
        "⏳ Planned",
        "28-May-2026",
        "Handles late-arriving data. Uses MAX(timestamp) per charger_id as watermark. Replaces full-date reload for high-volume production scenarios."
    ),
    (
        "PL_09_Pipeline_Monitoring",
        "Monitoring — Self-Monitoring",
        "pipeline_execution_logs → Logic App alerts",
        "Scheduled trigger (every 6 hrs) → Query pipeline_execution_logs for stale/failed runs → Send alert via Logic App if any pipeline overdue",
        "⏳ Planned",
        "29-May-2026",
        "Monitors the pipelines themselves (not the data). Detects: last successful run > 26 hours ago, consecutive failures > 2, avg run time > 2× baseline."
    ),
    (
        "PL_00_Master_Orchestration",
        "Master — Orchestrator",
        "Orchestrates all child pipelines",
        "Set Pipeline Date → PL_01 → PL_03 → PL_02 → PL_05 → PL_06 → PL_04 → PL_07 → Log Master Success / Log Master Failure",
        "✅ Done",
        "25-May-2026",
        "Accepts optional pipeline_date parameter. Defaults to yesterday. Each child pipeline receives v_pipeline_date. Failure log fires if any pipeline in chain fails or is skipped."
    )
]

for idx, row in enumerate(pipeline_data):
    row_num = idx + 3

    ws2.row_dimensions[row_num].height = 80

    bg = ROW_BG[idx % 2]

    for col_num, value in enumerate(row, start=1):

        if col_num == 5:
            status_cell = ws2.cell(
                row=row_num,
                column=col_num,
                value=value
            )

            status_cell.font = Font(
                name="Arial",
                bold=True,
                size=10
            )

            status_cell.fill = PatternFill(
                fill_type="solid",
                start_color=STATUS_BG.get(value, WHITE)
            )

            status_cell.alignment = Alignment(
                horizontal="center",
                vertical="center"
            )

        else:
            data_cell(
                ws2,
                row_num,
                col_num,
                value,
                bg=bg
            )

apply_border(ws2, 2, len(pipeline_data) + 2, 1, 7)

ws2.freeze_panes = "A3"

# =============================================================================
# SAVE FILE
# =============================================================================

output_file = "EV_POC_Project_Tracker.xlsx"

wb.save(output_file)

print(f"Excel file created successfully: {output_file}")