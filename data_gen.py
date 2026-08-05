"""
EV Charging Network — Multi-Year Batch Data Generator  (with intentional 30% corruption)
=========================================================================================
Generates synthetic telemetry for 2026-Jan-01 → 2026-Jun-03.

CORRUPTION LAYER (NEW)
-----------------------
~30% of all records are intentionally degraded so the Power BI pages show
meaningful exceptions, DQ failures, fault analytics and lost-revenue figures.

Corruption categories injected:
 A) FAULT INJECTION (≈10% of records)
    - Chargers forced into GROUND_FAULT, CABLE_FAULT, THERMAL_OVERLOAD, PHASE_IMBALANCE
      at much higher rates than normal operation would produce.
    - Some chargers are "stuck" faulted for an entire day (simulates broken chargers).
    - Repeat-fault flag set deliberately to inflate the "Repeat Failures" KPI.
 B) SENSOR / BILLING NULL STORMS (≈8% of records)
    - Entire billing block wiped to NULL (electricity_cost, maintenance_cost, etc.)
    - All three phase currents simultaneously NULL
    - connector_temp_c and ambient_temp_c both NULL at the same time
    - BMS SOC triplet (initial/current/target) all NULL mid-session
 C) VALUE RANGE VIOLATIONS (≈5% of records)
    - Voltage outside [300V–450V] (e.g. 250V or 480V) → fails DQ_Check_ValueRanges
    - uptime_pct > 100 or < 0
    - Negative session_revenue_inr / energy_delivered_kwh
 D) DUPLICATE RECORDS (≈3% of records)
    - Some (charger_id, timestamp) pairs are emitted twice → fails DQ_Check_Duplicates
 E) IDENTITY / FORMAT VIOLATIONS (≈2% of records)
    - charger_id set to a malformed value (no underscore pattern) → fails DQ_Check_Identity
    - status set to an unknown value like 'Unknown' or 'Offline'
    - state / city set to NULL
 F) BUSINESS RULE VIOLATIONS (≈2% of records)
    - Faulted row with error_code = 'None' or NULL → fails DQ_Check_BusinessRules
    - Charging row with negative energy

The categories add up to ~30% corruption.  Each category is independently
sampled so a single record can carry more than one defect (realistic).

Output structure (unchanged from original):
    output_dir/
    └── ev_telemetry/
        ├── 20260101/
        │   └── ev_telemetry_20260101.jsonl.gz
        ...

Usage
-----
    python ev_data_generator_multiyear.py [--output-dir PATH]
                                          [--start YYYY-MM-DD]
                                          [--end   YYYY-MM-DD]
                                          [--tick-mins N]
                                          [--workers N]

Defaults:
    --output-dir  ./ev_data_output
    --start       2026-01-01
    --end         2026-06-04   (exclusive — last file = 2026-06-03)
    --tick-mins   10
    --workers     4
"""

import argparse
import gzip
import json
import os
import random
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
# CHARGER REGISTRY  (177 chargers across all Indian states)
# ─────────────────────────────────────────────────────────────────────────────
CHARGER_REGISTRY = [
    {"charger_id": "CH_1101_VJA", "state": "Andhra Pradesh",    "city": "Vijayawada",          "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Fast (150kW+)",   "max_power_kw": 150},
    {"charger_id": "CH_1102_VJA", "state": "Andhra Pradesh",    "city": "Vijayawada",          "zone": "Urban",       "site_type": "Urban",       "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_1103_VJA", "state": "Andhra Pradesh",    "city": "Vijayawada",          "zone": "Mall",        "site_type": "Mall",        "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_1104_VSK", "state": "Andhra Pradesh",    "city": "Visakhapatnam",       "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Fast (150kW+)",   "max_power_kw": 150},
    {"charger_id": "CH_1105_VSK", "state": "Andhra Pradesh",    "city": "Visakhapatnam",       "zone": "Industrial",  "site_type": "Industrial",  "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_1106_TPT", "state": "Andhra Pradesh",    "city": "Tirupati",            "zone": "Highway",     "site_type": "Highway",     "hw_type": "AC Slow (7kW)",      "max_power_kw": 7},
    {"charger_id": "CH_1201_ITA", "state": "Arunachal Pradesh", "city": "Itanagar",            "zone": "Urban",       "site_type": "Urban",       "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_1202_ITA", "state": "Arunachal Pradesh", "city": "Itanagar",            "zone": "Highway",     "site_type": "Highway",     "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_1203_ITA", "state": "Arunachal Pradesh", "city": "Itanagar",            "zone": "Residential", "site_type": "Residential", "hw_type": "AC Slow (7kW)",      "max_power_kw": 7},
    {"charger_id": "CH_1204_NAH", "state": "Arunachal Pradesh", "city": "Naharlagun",          "zone": "Urban",       "site_type": "Urban",       "hw_type": "AC Slow (7kW)",      "max_power_kw": 7},
    {"charger_id": "CH_1205_PAS", "state": "Arunachal Pradesh", "city": "Pasighat",            "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_1301_GUW", "state": "Assam",             "city": "Guwahati",            "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Fast (150kW+)",   "max_power_kw": 150},
    {"charger_id": "CH_1302_GUW", "state": "Assam",             "city": "Guwahati",            "zone": "Mall",        "site_type": "Mall",        "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_1303_GUW", "state": "Assam",             "city": "Guwahati",            "zone": "Urban",       "site_type": "Urban",       "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_1304_DIS", "state": "Assam",             "city": "Dibrugarh",           "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_1305_DIS", "state": "Assam",             "city": "Dibrugarh",           "zone": "Urban",       "site_type": "Urban",       "hw_type": "AC Slow (7kW)",      "max_power_kw": 7},
    {"charger_id": "CH_1306_SIL", "state": "Assam",             "city": "Silchar",             "zone": "Highway",     "site_type": "Highway",     "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_1401_PAT", "state": "Bihar",             "city": "Patna",               "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Fast (150kW+)",   "max_power_kw": 150},
    {"charger_id": "CH_1402_PAT", "state": "Bihar",             "city": "Patna",               "zone": "Urban",       "site_type": "Urban",       "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_1403_PAT", "state": "Bihar",             "city": "Patna",               "zone": "Mall",        "site_type": "Mall",        "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_1404_GAY", "state": "Bihar",             "city": "Gaya",                "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_1405_GAY", "state": "Bihar",             "city": "Gaya",                "zone": "Urban",       "site_type": "Urban",       "hw_type": "AC Slow (7kW)",      "max_power_kw": 7},
    {"charger_id": "CH_1406_MUZ", "state": "Bihar",             "city": "Muzaffarpur",         "zone": "Highway",     "site_type": "Highway",     "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_5001_CHD", "state": "Chandigarh",        "city": "Chandigarh",          "zone": "Sector 17",   "site_type": "Urban",       "hw_type": "DC Fast (150kW+)",   "max_power_kw": 150},
    {"charger_id": "CH_5002_CHD", "state": "Chandigarh",        "city": "Chandigarh",          "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_5003_CHD", "state": "Chandigarh",        "city": "Chandigarh",          "zone": "IT Park",     "site_type": "IT Park",     "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_5004_CHD", "state": "Chandigarh",        "city": "Chandigarh",          "zone": "Mall",        "site_type": "Mall",        "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_5005_CHD", "state": "Chandigarh",        "city": "Chandigarh",          "zone": "Residential", "site_type": "Residential", "hw_type": "AC Slow (7kW)",      "max_power_kw": 7},
    {"charger_id": "CH_1501_RAI", "state": "Chhattisgarh",      "city": "Raipur",              "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Fast (150kW+)",   "max_power_kw": 150},
    {"charger_id": "CH_1502_RAI", "state": "Chhattisgarh",      "city": "Raipur",              "zone": "Mall",        "site_type": "Mall",        "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_1503_RAI", "state": "Chhattisgarh",      "city": "Raipur",              "zone": "Urban",       "site_type": "Urban",       "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_1504_BIL", "state": "Chhattisgarh",      "city": "Bilaspur",            "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_1505_BIL", "state": "Chhattisgarh",      "city": "Bilaspur",            "zone": "Industrial",  "site_type": "Industrial",  "hw_type": "DC Fast (150kW+)",   "max_power_kw": 150},
    {"charger_id": "CH_1506_DUR", "state": "Chhattisgarh",      "city": "Durg",                "zone": "Urban",       "site_type": "Urban",       "hw_type": "AC Slow (7kW)",      "max_power_kw": 7},
    {"charger_id": "CH_9921_DEL", "state": "Delhi",             "city": "New Delhi",           "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Fast (150kW+)",   "max_power_kw": 150},
    {"charger_id": "CH_9922_DEL", "state": "Delhi",             "city": "New Delhi",           "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_9923_DEL", "state": "Delhi",             "city": "New Delhi",           "zone": "Urban",       "site_type": "Urban",       "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_9924_DEL", "state": "Delhi",             "city": "New Delhi",           "zone": "Mall",        "site_type": "Mall",        "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_9925_DEL", "state": "Delhi",             "city": "Dwarka",              "zone": "Residential", "site_type": "Residential", "hw_type": "AC Slow (7kW)",      "max_power_kw": 7},
    {"charger_id": "CH_9926_DEL", "state": "Delhi",             "city": "Rohini",              "zone": "Urban",       "site_type": "Urban",       "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_1701_PNJ", "state": "Goa",               "city": "Panaji",              "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Fast (150kW+)",   "max_power_kw": 150},
    {"charger_id": "CH_1702_PNJ", "state": "Goa",               "city": "Panaji",              "zone": "Mall",        "site_type": "Mall",        "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_1703_PNJ", "state": "Goa",               "city": "Panaji",              "zone": "Urban",       "site_type": "Urban",       "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_1704_MRG", "state": "Goa",               "city": "Margao",              "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_1705_MRG", "state": "Goa",               "city": "Margao",              "zone": "Residential", "site_type": "Residential", "hw_type": "AC Slow (7kW)",      "max_power_kw": 7},
    {"charger_id": "CH_1706_VAS", "state": "Goa",               "city": "Vasco",               "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Fast (150kW+)",   "max_power_kw": 150},
    {"charger_id": "CH_1801_AMD", "state": "Gujarat",           "city": "Ahmedabad",           "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Fast (150kW+)",   "max_power_kw": 150},
    {"charger_id": "CH_1802_AMD", "state": "Gujarat",           "city": "Ahmedabad",           "zone": "Mall",        "site_type": "Mall",        "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_1803_AMD", "state": "Gujarat",           "city": "Ahmedabad",           "zone": "IT Park",     "site_type": "IT Park",     "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_1804_SUR", "state": "Gujarat",           "city": "Surat",               "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Fast (150kW+)",   "max_power_kw": 150},
    {"charger_id": "CH_1805_SUR", "state": "Gujarat",           "city": "Surat",               "zone": "Industrial",  "site_type": "Industrial",  "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_1806_VDR", "state": "Gujarat",           "city": "Vadodara",            "zone": "Urban",       "site_type": "Urban",       "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_1901_GGN", "state": "Haryana",           "city": "Gurugram",            "zone": "Cyber City",  "site_type": "IT Park",     "hw_type": "DC Fast (150kW+)",   "max_power_kw": 150},
    {"charger_id": "CH_1902_GGN", "state": "Haryana",           "city": "Gurugram",            "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_1903_GGN", "state": "Haryana",           "city": "Gurugram",            "zone": "Mall",        "site_type": "Mall",        "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_1904_FAR", "state": "Haryana",           "city": "Faridabad",           "zone": "Industrial",  "site_type": "Industrial",  "hw_type": "DC Fast (150kW+)",   "max_power_kw": 150},
    {"charger_id": "CH_1905_FAR", "state": "Haryana",           "city": "Faridabad",           "zone": "Urban",       "site_type": "Urban",       "hw_type": "AC Slow (7kW)",      "max_power_kw": 7},
    {"charger_id": "CH_1906_AMB", "state": "Haryana",           "city": "Ambala",              "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_2001_SML", "state": "Himachal Pradesh",  "city": "Shimla",              "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_2002_SML", "state": "Himachal Pradesh",  "city": "Shimla",              "zone": "Urban",       "site_type": "Urban",       "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_2003_MNL", "state": "Himachal Pradesh",  "city": "Manali",              "zone": "Highway",     "site_type": "Highway",     "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_2004_DRM", "state": "Himachal Pradesh",  "city": "Dharamshala",         "zone": "Urban",       "site_type": "Urban",       "hw_type": "AC Slow (7kW)",      "max_power_kw": 7},
    {"charger_id": "CH_2005_SOL", "state": "Himachal Pradesh",  "city": "Solan",               "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_2006_MND", "state": "Himachal Pradesh",  "city": "Mandi",               "zone": "Urban",       "site_type": "Urban",       "hw_type": "AC Slow (7kW)",      "max_power_kw": 7},
    {"charger_id": "CH_5101_SRG", "state": "Jammu and Kashmir", "city": "Srinagar",            "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_5102_SRG", "state": "Jammu and Kashmir", "city": "Srinagar",            "zone": "Urban",       "site_type": "Urban",       "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_5103_JAM", "state": "Jammu and Kashmir", "city": "Jammu",               "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Fast (150kW+)",   "max_power_kw": 150},
    {"charger_id": "CH_5104_JAM", "state": "Jammu and Kashmir", "city": "Jammu",               "zone": "Mall",        "site_type": "Mall",        "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_5105_LEH", "state": "Jammu and Kashmir", "city": "Leh",                 "zone": "Highway",     "site_type": "Highway",     "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_2101_RAN", "state": "Jharkhand",         "city": "Ranchi",              "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Fast (150kW+)",   "max_power_kw": 150},
    {"charger_id": "CH_2102_RAN", "state": "Jharkhand",         "city": "Ranchi",              "zone": "Mall",        "site_type": "Mall",        "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_2103_RAN", "state": "Jharkhand",         "city": "Ranchi",              "zone": "Urban",       "site_type": "Urban",       "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_2104_JMS", "state": "Jharkhand",         "city": "Jamshedpur",          "zone": "Industrial",  "site_type": "Industrial",  "hw_type": "DC Fast (150kW+)",   "max_power_kw": 150},
    {"charger_id": "CH_2105_JMS", "state": "Jharkhand",         "city": "Jamshedpur",          "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_2106_DHA", "state": "Jharkhand",         "city": "Dhanbad",             "zone": "Industrial",  "site_type": "Industrial",  "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_7742_BLR", "state": "Karnataka",         "city": "Bengaluru",           "zone": "IT Park",     "site_type": "IT Park",     "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_7743_BLR", "state": "Karnataka",         "city": "Bengaluru",           "zone": "Urban",       "site_type": "Urban",       "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_7744_BLR", "state": "Karnataka",         "city": "Bengaluru",           "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Fast (150kW+)",   "max_power_kw": 150},
    {"charger_id": "CH_7745_BLR", "state": "Karnataka",         "city": "Bengaluru",           "zone": "Mall",        "site_type": "Mall",        "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_7746_MYS", "state": "Karnataka",         "city": "Mysuru",              "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Fast (150kW+)",   "max_power_kw": 150},
    {"charger_id": "CH_7747_MYS", "state": "Karnataka",         "city": "Mysuru",              "zone": "Urban",       "site_type": "Urban",       "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_2301_KOC", "state": "Kerala",            "city": "Kochi",               "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Fast (150kW+)",   "max_power_kw": 150},
    {"charger_id": "CH_2302_KOC", "state": "Kerala",            "city": "Kochi",               "zone": "Mall",        "site_type": "Mall",        "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_2303_KOC", "state": "Kerala",            "city": "Kochi",               "zone": "Urban",       "site_type": "Urban",       "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_2304_TVM", "state": "Kerala",            "city": "Thiruvananthapuram",  "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Fast (150kW+)",   "max_power_kw": 150},
    {"charger_id": "CH_2305_TVM", "state": "Kerala",            "city": "Thiruvananthapuram",  "zone": "Urban",       "site_type": "Urban",       "hw_type": "AC Slow (7kW)",      "max_power_kw": 7},
    {"charger_id": "CH_2306_KZD", "state": "Kerala",            "city": "Kozhikode",           "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_2401_BHO", "state": "Madhya Pradesh",    "city": "Bhopal",              "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Fast (150kW+)",   "max_power_kw": 150},
    {"charger_id": "CH_2402_BHO", "state": "Madhya Pradesh",    "city": "Bhopal",              "zone": "Mall",        "site_type": "Mall",        "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_2403_BHO", "state": "Madhya Pradesh",    "city": "Bhopal",              "zone": "Urban",       "site_type": "Urban",       "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_2404_IND", "state": "Madhya Pradesh",    "city": "Indore",              "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Fast (150kW+)",   "max_power_kw": 150},
    {"charger_id": "CH_2405_IND", "state": "Madhya Pradesh",    "city": "Indore",              "zone": "IT Park",     "site_type": "IT Park",     "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_2406_JAB", "state": "Madhya Pradesh",    "city": "Jabalpur",            "zone": "Urban",       "site_type": "Urban",       "hw_type": "AC Slow (7kW)",      "max_power_kw": 7},
    {"charger_id": "CH_8831_MUM", "state": "Maharashtra",       "city": "Mumbai",              "zone": "Mall",        "site_type": "Mall",        "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_8834_MUM", "state": "Maharashtra",       "city": "Mumbai",              "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Fast (150kW+)",   "max_power_kw": 150},
    {"charger_id": "CH_8835_MUM", "state": "Maharashtra",       "city": "Mumbai",              "zone": "Urban",       "site_type": "Urban",       "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_6653_PUN", "state": "Maharashtra",       "city": "Pune",                "zone": "Residential", "site_type": "Residential", "hw_type": "AC Slow (7kW)",      "max_power_kw": 7},
    {"charger_id": "CH_6654_PUN", "state": "Maharashtra",       "city": "Pune",                "zone": "Industrial",  "site_type": "Industrial",  "hw_type": "DC Fast (150kW+)",   "max_power_kw": 150},
    {"charger_id": "CH_6655_PUN", "state": "Maharashtra",       "city": "Pune",                "zone": "IT Park",     "site_type": "IT Park",     "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_2701_IMP", "state": "Manipur",           "city": "Imphal",              "zone": "Urban",       "site_type": "Urban",       "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_2702_IMP", "state": "Manipur",           "city": "Imphal",              "zone": "Highway",     "site_type": "Highway",     "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_2703_IMP", "state": "Manipur",           "city": "Imphal",              "zone": "Residential", "site_type": "Residential", "hw_type": "AC Slow (7kW)",      "max_power_kw": 7},
    {"charger_id": "CH_2704_CHR", "state": "Manipur",           "city": "Churachandpur",       "zone": "Highway",     "site_type": "Highway",     "hw_type": "AC Slow (7kW)",      "max_power_kw": 7},
    {"charger_id": "CH_2705_TBL", "state": "Manipur",           "city": "Thoubal",             "zone": "Urban",       "site_type": "Urban",       "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_2801_SHI", "state": "Meghalaya",         "city": "Shillong",            "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_2802_SHI", "state": "Meghalaya",         "city": "Shillong",            "zone": "Urban",       "site_type": "Urban",       "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_2803_SHI", "state": "Meghalaya",         "city": "Shillong",            "zone": "Mall",        "site_type": "Mall",        "hw_type": "AC Slow (7kW)",      "max_power_kw": 7},
    {"charger_id": "CH_2804_TUR", "state": "Meghalaya",         "city": "Tura",                "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_2805_JOW", "state": "Meghalaya",         "city": "Jowai",               "zone": "Urban",       "site_type": "Urban",       "hw_type": "AC Slow (7kW)",      "max_power_kw": 7},
    {"charger_id": "CH_2901_AIZ", "state": "Mizoram",           "city": "Aizawl",              "zone": "Urban",       "site_type": "Urban",       "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_2902_AIZ", "state": "Mizoram",           "city": "Aizawl",              "zone": "Highway",     "site_type": "Highway",     "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_2903_AIZ", "state": "Mizoram",           "city": "Aizawl",              "zone": "Residential", "site_type": "Residential", "hw_type": "AC Slow (7kW)",      "max_power_kw": 7},
    {"charger_id": "CH_2904_LNG", "state": "Mizoram",           "city": "Lunglei",             "zone": "Highway",     "site_type": "Highway",     "hw_type": "AC Slow (7kW)",      "max_power_kw": 7},
    {"charger_id": "CH_2905_CHM", "state": "Mizoram",           "city": "Champhai",            "zone": "Urban",       "site_type": "Urban",       "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_3001_KOH", "state": "Nagaland",          "city": "Kohima",              "zone": "Urban",       "site_type": "Urban",       "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_3002_KOH", "state": "Nagaland",          "city": "Kohima",              "zone": "Highway",     "site_type": "Highway",     "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_3003_DIM", "state": "Nagaland",          "city": "Dimapur",             "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_3004_DIM", "state": "Nagaland",          "city": "Dimapur",             "zone": "Urban",       "site_type": "Urban",       "hw_type": "AC Slow (7kW)",      "max_power_kw": 7},
    {"charger_id": "CH_3005_MOK", "state": "Nagaland",          "city": "Mokokchung",          "zone": "Highway",     "site_type": "Highway",     "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_3101_BHU", "state": "Odisha",            "city": "Bhubaneswar",         "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Fast (150kW+)",   "max_power_kw": 150},
    {"charger_id": "CH_3102_BHU", "state": "Odisha",            "city": "Bhubaneswar",         "zone": "Mall",        "site_type": "Mall",        "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_3103_BHU", "state": "Odisha",            "city": "Bhubaneswar",         "zone": "IT Park",     "site_type": "IT Park",     "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_3104_CUT", "state": "Odisha",            "city": "Cuttack",             "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Fast (150kW+)",   "max_power_kw": 150},
    {"charger_id": "CH_3105_CUT", "state": "Odisha",            "city": "Cuttack",             "zone": "Urban",       "site_type": "Urban",       "hw_type": "AC Slow (7kW)",      "max_power_kw": 7},
    {"charger_id": "CH_3106_ROK", "state": "Odisha",            "city": "Rourkela",            "zone": "Industrial",  "site_type": "Industrial",  "hw_type": "DC Fast (150kW+)",   "max_power_kw": 150},
    {"charger_id": "CH_3201_CHD", "state": "Punjab",            "city": "Chandigarh",          "zone": "Urban",       "site_type": "Urban",       "hw_type": "DC Fast (150kW+)",   "max_power_kw": 150},
    {"charger_id": "CH_3202_CHD", "state": "Punjab",            "city": "Chandigarh",          "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_3203_CHD", "state": "Punjab",            "city": "Chandigarh",          "zone": "Mall",        "site_type": "Mall",        "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_3204_AMR", "state": "Punjab",            "city": "Amritsar",            "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Fast (150kW+)",   "max_power_kw": 150},
    {"charger_id": "CH_3205_AMR", "state": "Punjab",            "city": "Amritsar",            "zone": "Urban",       "site_type": "Urban",       "hw_type": "AC Slow (7kW)",      "max_power_kw": 7},
    {"charger_id": "CH_3206_LDH", "state": "Punjab",            "city": "Ludhiana",            "zone": "Industrial",  "site_type": "Industrial",  "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_3301_JAI", "state": "Rajasthan",         "city": "Jaipur",              "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Fast (150kW+)",   "max_power_kw": 150},
    {"charger_id": "CH_3302_JAI", "state": "Rajasthan",         "city": "Jaipur",              "zone": "Mall",        "site_type": "Mall",        "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_3303_JAI", "state": "Rajasthan",         "city": "Jaipur",              "zone": "Urban",       "site_type": "Urban",       "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_3304_JDH", "state": "Rajasthan",         "city": "Jodhpur",             "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Fast (150kW+)",   "max_power_kw": 150},
    {"charger_id": "CH_3305_JDH", "state": "Rajasthan",         "city": "Jodhpur",             "zone": "Urban",       "site_type": "Urban",       "hw_type": "AC Slow (7kW)",      "max_power_kw": 7},
    {"charger_id": "CH_3306_UDA", "state": "Rajasthan",         "city": "Udaipur",             "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_3401_GAN", "state": "Sikkim",            "city": "Gangtok",             "zone": "Urban",       "site_type": "Urban",       "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_3402_GAN", "state": "Sikkim",            "city": "Gangtok",             "zone": "Highway",     "site_type": "Highway",     "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_3403_GAN", "state": "Sikkim",            "city": "Gangtok",             "zone": "Residential", "site_type": "Residential", "hw_type": "AC Slow (7kW)",      "max_power_kw": 7},
    {"charger_id": "CH_3404_NAM", "state": "Sikkim",            "city": "Namchi",              "zone": "Highway",     "site_type": "Highway",     "hw_type": "AC Slow (7kW)",      "max_power_kw": 7},
    {"charger_id": "CH_3405_MAN", "state": "Sikkim",            "city": "Mangan",              "zone": "Urban",       "site_type": "Urban",       "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_3501_CHN", "state": "Tamil Nadu",        "city": "Chennai",             "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Fast (150kW+)",   "max_power_kw": 150},
    {"charger_id": "CH_3502_CHN", "state": "Tamil Nadu",        "city": "Chennai",             "zone": "IT Park",     "site_type": "IT Park",     "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_3503_CHN", "state": "Tamil Nadu",        "city": "Chennai",             "zone": "Mall",        "site_type": "Mall",        "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_3504_COI", "state": "Tamil Nadu",        "city": "Coimbatore",          "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Fast (150kW+)",   "max_power_kw": 150},
    {"charger_id": "CH_3505_COI", "state": "Tamil Nadu",        "city": "Coimbatore",          "zone": "Industrial",  "site_type": "Industrial",  "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_3506_MDU", "state": "Tamil Nadu",        "city": "Madurai",             "zone": "Urban",       "site_type": "Urban",       "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_5561_HYD", "state": "Telangana",         "city": "Hyderabad",           "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Fast (150kW+)",   "max_power_kw": 150},
    {"charger_id": "CH_5562_HYD", "state": "Telangana",         "city": "Hyderabad",           "zone": "Mall",        "site_type": "Mall",        "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_5563_HYD", "state": "Telangana",         "city": "Hyderabad",           "zone": "IT Park",     "site_type": "IT Park",     "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_5564_HYD", "state": "Telangana",         "city": "Hyderabad",           "zone": "Urban",       "site_type": "Urban",       "hw_type": "AC Slow (7kW)",      "max_power_kw": 7},
    {"charger_id": "CH_5565_WAR", "state": "Telangana",         "city": "Warangal",            "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Fast (150kW+)",   "max_power_kw": 150},
    {"charger_id": "CH_5566_NZB", "state": "Telangana",         "city": "Nizamabad",           "zone": "Urban",       "site_type": "Urban",       "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_3801_AGT", "state": "Tripura",           "city": "Agartala",            "zone": "Urban",       "site_type": "Urban",       "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_3802_AGT", "state": "Tripura",           "city": "Agartala",            "zone": "Highway",     "site_type": "Highway",     "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_3803_AGT", "state": "Tripura",           "city": "Agartala",            "zone": "Mall",        "site_type": "Mall",        "hw_type": "AC Slow (7kW)",      "max_power_kw": 7},
    {"charger_id": "CH_3804_DHA", "state": "Tripura",           "city": "Dharmanagar",         "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_3805_UDA", "state": "Tripura",           "city": "Udaipur",             "zone": "Urban",       "site_type": "Urban",       "hw_type": "AC Slow (7kW)",      "max_power_kw": 7},
    {"charger_id": "CH_3901_LKW", "state": "Uttar Pradesh",     "city": "Lucknow",             "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Fast (150kW+)",   "max_power_kw": 150},
    {"charger_id": "CH_3902_LKW", "state": "Uttar Pradesh",     "city": "Lucknow",             "zone": "Mall",        "site_type": "Mall",        "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_3903_LKW", "state": "Uttar Pradesh",     "city": "Lucknow",             "zone": "Urban",       "site_type": "Urban",       "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_3904_NDA", "state": "Uttar Pradesh",     "city": "Noida",               "zone": "IT Park",     "site_type": "IT Park",     "hw_type": "DC Fast (150kW+)",   "max_power_kw": 150},
    {"charger_id": "CH_3905_NDA", "state": "Uttar Pradesh",     "city": "Noida",               "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_3906_AGR", "state": "Uttar Pradesh",     "city": "Agra",                "zone": "Highway",     "site_type": "Highway",     "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_4001_DDN", "state": "Uttarakhand",       "city": "Dehradun",            "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Fast (150kW+)",   "max_power_kw": 150},
    {"charger_id": "CH_4002_DDN", "state": "Uttarakhand",       "city": "Dehradun",            "zone": "Mall",        "site_type": "Mall",        "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_4003_DDN", "state": "Uttarakhand",       "city": "Dehradun",            "zone": "Urban",       "site_type": "Urban",       "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_4004_HRD", "state": "Uttarakhand",       "city": "Haridwar",            "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Fast (150kW+)",   "max_power_kw": 150},
    {"charger_id": "CH_4005_HRD", "state": "Uttarakhand",       "city": "Haridwar",            "zone": "Urban",       "site_type": "Urban",       "hw_type": "AC Slow (7kW)",      "max_power_kw": 7},
    {"charger_id": "CH_4006_NTL", "state": "Uttarakhand",       "city": "Nainital",            "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_4101_KOL", "state": "West Bengal",       "city": "Kolkata",             "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Fast (150kW+)",   "max_power_kw": 150},
    {"charger_id": "CH_4102_KOL", "state": "West Bengal",       "city": "Kolkata",             "zone": "Mall",        "site_type": "Mall",        "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_4103_KOL", "state": "West Bengal",       "city": "Kolkata",             "zone": "Park Street", "site_type": "Urban",       "hw_type": "AC Type 2 (22kW)",   "max_power_kw": 22},
    {"charger_id": "CH_4104_KOL", "state": "West Bengal",       "city": "Kolkata",             "zone": "Salt Lake",   "site_type": "IT Park",     "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
    {"charger_id": "CH_4105_HWH", "state": "West Bengal",       "city": "Howrah",              "zone": "Industrial",  "site_type": "Industrial",  "hw_type": "DC Fast (150kW+)",   "max_power_kw": 150},
    {"charger_id": "CH_4106_SLG", "state": "West Bengal",       "city": "Siliguri",            "zone": "Highway",     "site_type": "Highway",     "hw_type": "DC Standard (50kW)", "max_power_kw": 50},
]

# ─────────────────────────────────────────────────────────────────────────────
# CORRUPTION CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
# Per-day, ~30% of charger IDs are randomly selected as "corruption candidates".
# Each category fires independently at its own probability.
CORRUPTION_CONFIG = {
    # A) Forced fault injection — probability per record for a corruption-candidate charger
    "fault_force_prob":          0.35,   # 35% of corruption-candidate records get forced fault
    "fault_repeat_prob":         0.60,   # 60% of injected faults are marked as repeat
    "stuck_faulted_charger_pct": 0.08,   # 8% of chargers stuck faulted all day (broken charger KPI)

    # B) NULL storms — probability per record (applies to ALL records, not just candidates)
    "billing_null_storm_prob":   0.09,   # wipes the entire billing block
    "sensor_null_storm_prob":    0.07,   # wipes connector_temp + ambient + all phase currents
    "bms_null_storm_prob":       0.06,   # wipes SOC triplet during active session

    # C) Value range violations — probability per record
    "voltage_outlier_prob":      0.05,   # voltage outside 300–450V
    "uptime_outlier_prob":       0.04,   # uptime_pct > 100 or < 0
    "negative_revenue_prob":     0.04,   # negative revenue / negative energy

    # D) Duplicate record injection — fraction of records to duplicate
    "duplicate_record_prob":     0.03,

    # E) Identity / format violations — probability per record
    "bad_charger_id_prob":       0.02,   # malformed charger_id
    "bad_status_prob":           0.02,   # status = 'Unknown' or 'Offline'
    "null_location_prob":        0.015,  # state/city = NULL

    # F) Business rule violations
    "faulted_no_code_prob":      0.025,  # Faulted row with error_code = None
    "charging_negative_energy_prob": 0.02,  # Charging row with energy < 0
}

# Force some specific chargers to be "always problematic" across all days —
# this makes them consistently appear at the top of "Revenue Lost by Charger".
PROBLEMATIC_CHARGER_IDS = {
    "CH_2301_KOC",  # Kerala  — appears in your Power BI fault table
    "CH_3504_COI",  # Tamil Nadu
    "CH_5565_WAR",  # Telangana
    "CH_3201_CHD",  # Punjab
    "CH_2701_IMP",  # Manipur
    "CH_2901_AIZ",  # Mizoram
    "CH_1804_SUR",  # Gujarat
    "CH_3106_ROK",  # Odisha
}

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS & LOOKUP TABLES
# ─────────────────────────────────────────────────────────────────────────────
COST_SPLIT = {
    "electricity_ratio":  0.54,
    "maintenance_ratio":  0.19,
    "connectivity_ratio": 0.13,
    "staff_ratio":        0.14,
}

ELECTRICITY_RATE_INR_PER_KWH = 8.5
SELLING_RATE_INR_PER_KWH     = 15.0

FAULT_TAXONOMY = {
    "THERMAL_OVERLOAD_SHUTDOWN": {"severity": "Critical", "base_mttr_mins": 120, "rev_impact_mult": 3.0},
    "PHASE_IMBALANCE_DETECTED":  {"severity": "High",     "base_mttr_mins":  60, "rev_impact_mult": 2.0},
    "COMM_LOSS":                 {"severity": "High",     "base_mttr_mins":  45, "rev_impact_mult": 1.8},
    "CABLE_FAULT":               {"severity": "Critical", "base_mttr_mins": 180, "rev_impact_mult": 3.5},
    "AUTH_ERROR":                {"severity": "Low",      "base_mttr_mins":   5, "rev_impact_mult": 0.5},
    "GROUND_FAULT":              {"severity": "Critical", "base_mttr_mins": 240, "rev_impact_mult": 4.0},
    "ICE_VEHICLE_DETECTED":      {"severity": "Low",      "base_mttr_mins":  10, "rev_impact_mult": 0.3},
    "POWER_FAILURE":             {"severity": "High",     "base_mttr_mins":  90, "rev_impact_mult": 2.5},
}

# Faults that are forced-injected (higher severity for visual impact in Power BI)
INJECTABLE_FAULTS = [
    "GROUND_FAULT",
    "PHASE_IMBALANCE_DETECTED",
    "CABLE_FAULT",
    "THERMAL_OVERLOAD_SHUTDOWN",
    "POWER_FAILURE",
]

HW_CATEGORY_MAP = {
    "DC Fast (150kW+)":   "DC Fast",
    "DC Standard (50kW)": "DC Standard",
    "AC Type 2 (22kW)":   "AC Type 2",
    "AC Slow (7kW)":      "AC Slow",
}

# ─────────────────────────────────────────────────────────────────────────────
# REALISTIC GROWTH / SEASONALITY FACTORS
# ─────────────────────────────────────────────────────────────────────────────
def _year_growth_factor(year: int) -> float:
    factors = {2024: 1.0, 2025: 1.25, 2026: 1.56}
    return factors.get(year, 1.0)

def _seasonal_factor(month: int) -> float:
    seasonal = {
        1: 1.10, 2: 1.08, 3: 1.05, 4: 0.92,
        5: 0.88, 6: 0.85, 7: 0.80, 8: 0.82,
        9: 0.85, 10: 1.12, 11: 1.18, 12: 1.15,
    }
    return seasonal.get(month, 1.0)

def _weekend_factor(day_of_week: int) -> float:
    return 1.20 if day_of_week >= 5 else 1.0

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def time_of_day_band(dt: datetime) -> str:
    h = dt.hour
    if h < 4:  return "00-04"
    if h < 8:  return "04-08"
    if h < 12: return "08-12"
    if h < 16: return "12-16"
    if h < 20: return "16-20"
    return "20-24"

def is_peak_hour(dt: datetime) -> bool:
    return (8 <= dt.hour <= 10) or (17 <= dt.hour <= 21)

def flatten_record(r: dict) -> dict:
    return {
        "charger_id":             r["charger_id"],
        "timestamp":              r["timestamp"],
        "state":                  r["state"],
        "city":                   r["city"],
        "zone":                   r["zone"],
        "site_type":              r["site_type"],
        "hw_type":                r["hw_type"],
        "charger_type_category":  r["charger_type_category"],
        "max_power_kw":           r["max_power_kw"],
        "status":                 r["status"],
        "is_online":              r["is_online"],
        "uptime_pct":             r["uptime_pct"],
        "user_id":                r["user_id"],
        "session_duration_mins":  r["session_duration_mins"],
        "session_dur_bucket":     r["session_dur_bucket"],
        "utilisation_pct":        r["utilisation_pct"],
        "time_of_day_band":       r["time_of_day_band"],
        "total_active_power_kw":  r["power_metrics"]["total_active_power_kw"],
        "voltage_phase_a_v":      r["power_metrics"]["voltage_phase_a_v"],
        "voltage_phase_b_v":      r["power_metrics"]["voltage_phase_b_v"],
        "voltage_phase_c_v":      r["power_metrics"]["voltage_phase_c_v"],
        "current_phase_a_a":      r["power_metrics"]["current_phase_a_a"],
        "current_phase_b_a":      r["power_metrics"]["current_phase_b_a"],
        "current_phase_c_a":      r["power_metrics"]["current_phase_c_a"],
        "connector_temp_c":       r["thermal"]["connector_temp_c"],
        "ambient_temp_c":         r["thermal"]["ambient_temp_c"],
        "energy_delivered_kwh":   r["billing"]["energy_delivered_kwh"],
        "session_revenue_inr":    r["billing"]["session_revenue_inr"],
        "electricity_cost_inr":   r["billing"]["electricity_cost_inr"],
        "maintenance_cost_inr":   r["billing"]["maintenance_cost_inr"],
        "connectivity_cost_inr":  r["billing"]["connectivity_cost_inr"],
        "staff_cost_inr":         r["billing"]["staff_cost_inr"],
        "net_margin_inr":         r["billing"]["net_margin_inr"],
        "lost_revenue_inr":       r["billing"]["lost_revenue_inr"],
        "initial_soc_pct":        r["battery_state"]["initial_soc_pct"],
        "current_soc_pct":        r["battery_state"]["current_soc_pct"],
        "target_soc_pct":         r["battery_state"]["target_soc_pct"],
        "error_code":             r["fault"]["error_code"],
        "fault_severity":         r["fault"]["severity"],
        "is_faulted":             r["fault"]["is_faulted"],
        "repeat_fault":           r["fault"]["repeat_fault"],
        "mttr_estimate_mins":     r["fault"]["mttr_estimate_mins"],
        "downtime_mins_today":    r["fault"]["downtime_mins_today"],
        "customers_lost":         r["fault"]["customers_lost"],
        "fault_lost_revenue_inr": r["fault"]["lost_revenue_inr"],
        "zone_score":             r["location_intel"]["zone_score"],
        "peak_hour":              r["location_intel"]["peak_hour"],
        # NEW: corruption metadata — useful for building exception gold tables
        "_corruption_flags":      r.get("_corruption_flags", []),
    }

# ─────────────────────────────────────────────────────────────────────────────
# CORRUPTION ENGINE
# ─────────────────────────────────────────────────────────────────────────────
def apply_corruption(record: dict, is_candidate: bool, is_stuck_faulted: bool,
                     is_problematic: bool) -> dict:
    """
    Mutates `record` in-place with intentional data defects.
    Returns the mutated record (also mutated in-place for efficiency).
    Corruption is layered — a single record can have multiple defects.
    """
    flags = []
    cfg = CORRUPTION_CONFIG

    # ── A) FAULT INJECTION ──────────────────────────────────────────────────
    if is_stuck_faulted or is_problematic:
        # These chargers are forced faulted every record today
        forced_fault = random.choice(INJECTABLE_FAULTS)
        fault_info = FAULT_TAXONOMY[forced_fault]

        record["status"] = "Faulted"
        record["is_faulted"] = True
        record["error_code"] = forced_fault
        record["fault_severity"] = fault_info["severity"]
        record["repeat_fault"] = random.random() < 0.75  # high repeat rate
        record["mttr_estimate_mins"] = fault_info["base_mttr_mins"]

        rev_impact = fault_info["rev_impact_mult"]
        max_kw = record.get("max_power_kw", 50)
        record["lost_revenue_inr"] = round(
            (max_kw * SELLING_RATE_INR_PER_KWH / 60) * rev_impact, 4
        )
        record["fault_lost_revenue_inr"] = record["lost_revenue_inr"]

        record["customers_lost"] = round(
            (1.0 if is_peak_hour(datetime.fromisoformat(record["timestamp"])) else 0.4), 2
        )
        record["downtime_mins_today"] += random.randint(30, 200)
        record["uptime_pct"] = round(random.uniform(20.0, 55.0), 2)  # degraded uptime
        flags.append("FORCED_FAULT")

    elif is_candidate and random.random() < cfg["fault_force_prob"]:
        forced_fault = random.choice(INJECTABLE_FAULTS)
        fault_info = FAULT_TAXONOMY[forced_fault]

        record["status"] = "Faulted"
        record["is_faulted"] = True
        record["error_code"] = forced_fault
        record["fault_severity"] = fault_info["severity"]
        record["repeat_fault"] = random.random() < cfg["fault_repeat_prob"]
        record["mttr_estimate_mins"] = fault_info["base_mttr_mins"]

        rev_impact = fault_info["rev_impact_mult"]
        max_kw = record.get("max_power_kw", 50)
        record["lost_revenue_inr"] = round(
            (max_kw * SELLING_RATE_INR_PER_KWH / 60) * rev_impact, 4
        )
        record["fault_lost_revenue_inr"] = record["lost_revenue_inr"]
        record["downtime_mins_today"] += random.randint(10, 120)
        flags.append("INJECTED_FAULT")

    # ── B) NULL STORMS ───────────────────────────────────────────────────────
    if random.random() < cfg["billing_null_storm_prob"]:
        record["electricity_cost_inr"] = None
        record["maintenance_cost_inr"] = None
        record["connectivity_cost_inr"] = None
        record["staff_cost_inr"] = None
        record["net_margin_inr"] = None
        flags.append("BILLING_NULL_STORM")

    if random.random() < cfg["sensor_null_storm_prob"]:
        record["connector_temp_c"] = None
        record["ambient_temp_c"] = None
        record["current_phase_a_a"] = None
        record["current_phase_b_a"] = None
        record["current_phase_c_a"] = None
        record["total_active_power_kw"] = None
        record["utilisation_pct"] = None
        flags.append("SENSOR_NULL_STORM")

    if random.random() < cfg["bms_null_storm_prob"] and record.get("user_id"):
        record["initial_soc_pct"] = None
        record["current_soc_pct"] = None
        record["target_soc_pct"] = None
        flags.append("BMS_NULL_STORM")

    # ── C) VALUE RANGE VIOLATIONS ────────────────────────────────────────────
    if random.random() < cfg["voltage_outlier_prob"]:
        bad_v = random.choice([
            round(random.uniform(200, 295), 2),  # too low
            round(random.uniform(455, 520), 2),  # too high
        ])
        phase = random.choice(["voltage_phase_a_v", "voltage_phase_b_v", "voltage_phase_c_v"])
        record[phase] = bad_v
        flags.append("VOLTAGE_OUTLIER")

    if random.random() < cfg["uptime_outlier_prob"]:
        record["uptime_pct"] = random.choice([
            round(random.uniform(101, 115), 2),  # > 100 (impossible)
            round(random.uniform(-15, -0.1), 2), # negative
        ])
        flags.append("UPTIME_OUTLIER")

    if random.random() < cfg["negative_revenue_prob"]:
        record["session_revenue_inr"] = round(random.uniform(-500, -1), 2)
        record["energy_delivered_kwh"] = round(random.uniform(-50, -0.1), 3)
        flags.append("NEGATIVE_REVENUE")

    # ── D) DUPLICATE MARKER ──────────────────────────────────────────────────
    # The actual duplication happens at the day-generation level after record assembly.
    # We just tag here; the caller handles emission of a second copy.
    if random.random() < cfg["duplicate_record_prob"]:
        flags.append("DUPLICATE")

    # ── E) IDENTITY / FORMAT VIOLATIONS ─────────────────────────────────────
    if random.random() < cfg["bad_charger_id_prob"]:
        # Malformed charger ID (no underscore pattern fails DQ regex)
        record["charger_id"] = random.choice([
            "CHARGER" + str(random.randint(1000, 9999)),
            "ch-" + str(random.randint(100, 999)),
            "",
            "NULL",
        ])
        flags.append("BAD_CHARGER_ID")

    if random.random() < cfg["bad_status_prob"]:
        record["status"] = random.choice(["Unknown", "Offline", "Error", "Maintenance", ""])
        flags.append("BAD_STATUS")

    if random.random() < cfg["null_location_prob"]:
        if random.random() < 0.5:
            record["state"] = None
        else:
            record["city"] = None
        flags.append("NULL_LOCATION")

    # ── F) BUSINESS RULE VIOLATIONS ──────────────────────────────────────────
    if record.get("is_faulted") and random.random() < cfg["faulted_no_code_prob"]:
        # Faulted row but error_code cleared → violates business rule
        record["error_code"] = "None"
        record["fault_severity"] = "None"
        flags.append("FAULTED_NO_CODE")

    if record.get("status") == "Charging" and random.random() < cfg["charging_negative_energy_prob"]:
        record["energy_delivered_kwh"] = round(random.uniform(-20, -0.1), 3)
        flags.append("CHARGING_NEGATIVE_ENERGY")

    record["_corruption_flags"] = flags
    return record

# ─────────────────────────────────────────────────────────────────────────────
# CHARGER SIMULATION CLASS  (unchanged core logic)
# ─────────────────────────────────────────────────────────────────────────────
class EVCharger:
    def __init__(self, meta: dict, year_factor: float = 1.0, seasonal_factor: float = 1.0):
        self.meta = meta
        self.charger_id    = meta["charger_id"]
        self.max_power_kw  = meta["max_power_kw"]
        self.year_factor   = year_factor
        self.seasonal_factor = seasonal_factor

        self.status         = "Available"
        self.current_user_id   = None
        self.current_time      = None

        self.connector_temp_c = random.uniform(20.0, 25.0)
        self.ambient_temp_c   = random.uniform(18.0, 38.0)

        self.time_spent_in_session = 0
        self.target_duration_mins  = 0
        self.initial_battery_pct   = 0.0
        self.current_battery_pct   = 0.0
        self.target_battery_pct    = 0.0

        self.session_energy_kwh    = 0.0
        self.session_cost_inr      = 0.0
        self.session_start_time    = None

        self.error_code       = "None"
        self.is_online        = True
        self.fault_start_time = None
        self.fault_resolved   = True
        self.last_fault_type  = "None"
        self.fault_count_session = 0

        self.total_downtime_mins = 0
        self.total_minutes_tracked = 0
        self.downtime_minutes      = 0

    def _start_fault(self, fault_type: str):
        self.status           = "Faulted"
        self.error_code       = fault_type
        self.fault_start_time = self.current_time
        self.fault_resolved   = False
        repeat = (fault_type == self.last_fault_type)
        self.last_fault_type  = fault_type
        self.fault_count_session += 1
        return repeat

    def _resolve_fault(self):
        if self.fault_start_time:
            dt_mins = (self.current_time - self.fault_start_time).seconds // 60
            self.total_downtime_mins += dt_mins
        self.fault_start_time = None
        self.fault_resolved   = True
        self.status           = "Available"
        self.error_code       = "None"
        self.current_user_id  = None

    def generate_reading(self) -> Optional[dict]:
        self.current_time += timedelta(minutes=1)
        self.total_minutes_tracked += 1

        if random.random() < 0.01:
            self.is_online = False
            self.downtime_minutes += 1
            return None
        self.is_online = True

        volts_a = random.uniform(393.0, 407.0)
        volts_b = random.uniform(393.0, 407.0)
        volts_c = random.uniform(393.0, 407.0)
        amps_a = amps_b = amps_c = 0.0
        total_power_kw = 0.0

        peak_prob     = min(0.35, 0.18 * self.year_factor * self.seasonal_factor)
        offpeak_prob  = min(0.18, 0.08 * self.year_factor * self.seasonal_factor)

        if self.status == "Available":
            self.connector_temp_c = max(self.ambient_temp_c, self.connector_temp_c - 5.0)
            self.error_code = "None"

            if random.random() < 0.03:
                self.error_code = "ICE_VEHICLE_DETECTED"
            elif random.random() < (peak_prob if is_peak_hour(self.current_time) else offpeak_prob):
                self.status              = "Charging"
                self.current_user_id     = f"USR_{random.randint(1000, 9999)}"
                self.target_duration_mins = random.randint(20, 120)
                self.initial_battery_pct  = round(random.uniform(8.0, 45.0), 2)
                self.current_battery_pct  = self.initial_battery_pct
                self.target_battery_pct   = random.choice([70.0, 80.0, 90.0, 100.0])
                self.session_energy_kwh   = 0.0
                self.session_cost_inr     = 0.0
                self.session_start_time   = self.current_time

        elif self.status == "Charging":
            self.time_spent_in_session += 1
            max_amps = (self.max_power_kw * 1000) / (1.732 * 400)

            if self.current_battery_pct < 80.0:
                base_amps = max_amps * random.uniform(0.90, 1.00)
            elif self.current_battery_pct < 95.0:
                base_amps = max_amps * random.uniform(0.40, 0.60)
            else:
                base_amps = max_amps * random.uniform(0.05, 0.15)

            amps_a = base_amps + random.uniform(-1.0, 1.0)
            amps_b = base_amps + random.uniform(-1.0, 1.0)
            amps_c = base_amps + random.uniform(-1.0, 1.0)

            avg_voltage    = (volts_a + volts_b + volts_c) / 3
            avg_amps       = (amps_a + amps_b + amps_c) / 3
            total_power_kw = (1.732 * avg_voltage * avg_amps) / 1000
            energy_this_min          = total_power_kw / 60
            self.session_energy_kwh  += energy_this_min

            rev_rate = SELLING_RATE_INR_PER_KWH * min(1.0 + (self.year_factor - 1.0) * 0.1, 1.3)
            self.session_cost_inr    = self.session_energy_kwh * rev_rate

            charge_increment          = (energy_this_min / (self.max_power_kw * 0.5)) * 100
            self.current_battery_pct  = min(100.0, self.current_battery_pct + charge_increment)
            self.connector_temp_c    += random.uniform(0.3, 1.2)

            if self.connector_temp_c > 95.0:
                self._start_fault("THERMAL_OVERLOAD_SHUTDOWN")
            elif random.random() < 0.001:
                amps_c = amps_c * 0.2
                self._start_fault("PHASE_IMBALANCE_DETECTED")
            elif random.random() < 0.0002:
                self._start_fault("GROUND_FAULT")
            elif (
                self.current_battery_pct >= self.target_battery_pct
                or self.time_spent_in_session >= self.target_duration_mins
            ):
                self.status               = "Available"
                self.current_user_id      = None
                self.time_spent_in_session = 0

        elif self.status == "Faulted":
            self.downtime_minutes += 1
            fault_info = FAULT_TAXONOMY.get(self.error_code, {"base_mttr_mins": 30})
            p_resolve = 1.0 / max(fault_info["base_mttr_mins"], 1)
            if random.random() < p_resolve:
                self._resolve_fault()

        utilisation_pct = round(
            (total_power_kw / self.max_power_kw * 100) if self.max_power_kw > 0 else 0.0, 2
        )

        if self.session_start_time and self.status == "Charging":
            elapsed_mins = (self.current_time - self.session_start_time).seconds // 60
        else:
            elapsed_mins = self.time_spent_in_session

        if elapsed_mins < 15:     session_dur_bucket = "<15min"
        elif elapsed_mins < 30:   session_dur_bucket = "15-30min"
        elif elapsed_mins < 60:   session_dur_bucket = "30-60min"
        elif elapsed_mins < 120:  session_dur_bucket = "60-120min"
        else:                     session_dur_bucket = ">120min"

        electricity_cost = self.session_energy_kwh * ELECTRICITY_RATE_INR_PER_KWH
        total_cost       = electricity_cost / COST_SPLIT["electricity_ratio"] if electricity_cost > 0 else 0.0
        maintenance_cost  = total_cost * COST_SPLIT["maintenance_ratio"]
        connectivity_cost = total_cost * COST_SPLIT["connectivity_ratio"]
        staff_cost        = total_cost * COST_SPLIT["staff_ratio"]

        uptime_pct = round(
            (1 - self.downtime_minutes / max(self.total_minutes_tracked, 1)) * 100, 2
        ) if self.total_minutes_tracked > 0 else 100.0

        fault_info     = FAULT_TAXONOMY.get(self.error_code, {})
        fault_severity = fault_info.get("severity", "None")
        mttr_mins      = fault_info.get("base_mttr_mins", 0) if self.status == "Faulted" else 0
        repeat_fault   = (self.error_code == self.last_fault_type and self.error_code != "None")
        rev_impact_mult   = fault_info.get("rev_impact_mult", 0.0)

        lost_rev_this_min = round(
            (self.max_power_kw * SELLING_RATE_INR_PER_KWH / 60) * rev_impact_mult
            if self.status == "Faulted" else 0.0, 4
        )
        customers_lost = round(
            (1.0 if is_peak_hour(self.current_time) else 0.4)
            if self.status == "Faulted" else 0.0, 2
        )

        zone_score = round(
            (utilisation_pct * 0.6 + uptime_pct * 0.4) / 100, 4
        )

        # Original low-rate NULL injections (unchanged — these are on top of corruption)
        _billing_null = random.random() < 0.025
        if _billing_null:
            electricity_cost = maintenance_cost = connectivity_cost = staff_cost = total_cost = None

        _thermal_null = random.random() < 0.018
        _ambient_null = random.random() < 0.008
        _ia_null = random.random() < 0.012
        _ib_null = random.random() < 0.012
        _ic_null = random.random() < 0.012
        _volt_null = random.random() < 0.008
        _user_null = random.random() < 0.03 and self.current_user_id is not None
        _bms_null  = random.random() < 0.02
        _util_null = (_ia_null and _ib_null and _ic_null) or _volt_null
        _mttr_null = random.random() < 0.005 and self.status == "Faulted"

        payload = {
            "charger_id":            self.charger_id,
            "timestamp":             self.current_time.isoformat(),
            "state":                 self.meta["state"],
            "city":                  self.meta["city"],
            "zone":                  self.meta["zone"],
            "site_type":             self.meta["site_type"],
            "hw_type":               self.meta["hw_type"],
            "charger_type_category": HW_CATEGORY_MAP.get(self.meta["hw_type"], self.meta["hw_type"]),
            "max_power_kw":          self.max_power_kw,
            "status":                self.status,
            "is_online":             self.is_online,
            "uptime_pct":            uptime_pct,
            "user_id":               None if _user_null else self.current_user_id,
            "session_duration_mins": elapsed_mins,
            "session_dur_bucket":    session_dur_bucket,
            "utilisation_pct":       None if _util_null else utilisation_pct,
            "time_of_day_band":      time_of_day_band(self.current_time),
            "power_metrics": {
                "total_active_power_kw": None if (_volt_null or (_ia_null and _ib_null and _ic_null)) else round(total_power_kw, 3),
                "voltage_phase_a_v": None if _volt_null else round(volts_a, 2),
                "voltage_phase_b_v": None if _volt_null else round(volts_b, 2),
                "voltage_phase_c_v": None if _volt_null else round(volts_c, 2),
                "current_phase_a_a": None if _ia_null else round(amps_a, 2),
                "current_phase_b_a": None if _ib_null else round(amps_b, 2),
                "current_phase_c_a": None if _ic_null else round(amps_c, 2),
            },
            "thermal": {
                "connector_temp_c": None if _thermal_null else round(self.connector_temp_c, 2),
                "ambient_temp_c":   None if _ambient_null else round(self.ambient_temp_c, 2),
            },
            "billing": {
                "energy_delivered_kwh":  round(self.session_energy_kwh, 3),
                "session_revenue_inr":   round(self.session_cost_inr, 2),
                "electricity_cost_inr":  None if _billing_null else (round(electricity_cost, 2) if electricity_cost is not None else None),
                "maintenance_cost_inr":  None if _billing_null else (round(maintenance_cost, 2) if maintenance_cost is not None else None),
                "connectivity_cost_inr": None if _billing_null else (round(connectivity_cost, 2) if connectivity_cost is not None else None),
                "staff_cost_inr":        None if _billing_null else (round(staff_cost, 2) if staff_cost is not None else None),
                "net_margin_inr":        None if _billing_null else (round(self.session_cost_inr - total_cost, 2) if total_cost is not None else None),
                "lost_revenue_inr":      lost_rev_this_min,
            },
            "battery_state": {
                "initial_soc_pct": None if _bms_null else (round(self.initial_battery_pct, 2) if self.current_user_id else None),
                "current_soc_pct": None if _bms_null else (round(self.current_battery_pct, 2) if self.current_user_id else None),
                "target_soc_pct":  None if _bms_null else (round(self.target_battery_pct, 2)  if self.current_user_id else None),
            },
            "fault": {
                "error_code":          self.error_code,
                "severity":            fault_severity,
                "is_faulted":          self.status == "Faulted",
                "repeat_fault":        repeat_fault,
                "mttr_estimate_mins":  None if _mttr_null else mttr_mins,
                "downtime_mins_today": self.total_downtime_mins,
                "customers_lost":      customers_lost,
                "lost_revenue_inr":    lost_rev_this_min,
            },
            "location_intel": {
                "zone_score": None if _util_null else zone_score,
                "peak_hour":  is_peak_hour(self.current_time),
            },
            "_corruption_flags": [],  # filled by apply_corruption()
        }
        return payload

# ─────────────────────────────────────────────────────────────────────────────
# DAY-LEVEL BATCH GENERATION
# ─────────────────────────────────────────────────────────────────────────────
def generate_day(args: tuple) -> str:
    target_date_str, output_dir, tick_mins = args
    target_date = datetime.strptime(target_date_str, "%Y-%m-%d")
    year        = target_date.year
    month       = target_date.month
    dow         = target_date.weekday()
    date_str    = target_date.strftime("%Y%m%d")

    y_factor  = _year_growth_factor(year)
    s_factor  = _seasonal_factor(month) * _weekend_factor(dow)

    rng_seed = int(target_date_str.replace("-", ""))
    random.seed(rng_seed)

    # ── Determine which chargers are "corruption candidates" today ───────────
    n_chargers = len(CHARGER_REGISTRY)
    n_candidates = int(n_chargers * 0.30)  # 30% of chargers are corruption candidates
    candidate_ids = set(
        meta["charger_id"]
        for meta in random.sample(CHARGER_REGISTRY, n_candidates)
    )

    # Stuck-faulted chargers (broken charger KPI) — 8% of candidates
    n_stuck = max(1, int(n_candidates * CORRUPTION_CONFIG["stuck_faulted_charger_pct"]))
    stuck_ids = set(
        cid for cid in random.sample(list(candidate_ids), min(n_stuck, len(candidate_ids)))
    )

    chargers    = [EVCharger(meta, year_factor=y_factor, seasonal_factor=s_factor) for meta in CHARGER_REGISTRY]
    start_of_day = datetime(year, month, target_date.day, 0, 0, 0, tzinfo=timezone.utc)

    for ch in chargers:
        ch.current_time = start_of_day - timedelta(minutes=1)

    ticks   = 1440 // tick_mins
    records = []

    for _tick in range(ticks):
        for ch in chargers:
            for _ in range(tick_mins - 1):
                ch.current_time += timedelta(minutes=1)
                ch.total_minutes_tracked += 1

            reading = ch.generate_reading()
            if reading is None:
                continue

            flat = flatten_record(reading)

            # Promote nested fields that apply_corruption needs at flat level
            flat["connector_temp_c"] = reading["thermal"]["connector_temp_c"]
            flat["ambient_temp_c"]   = reading["thermal"]["ambient_temp_c"]
            flat["current_phase_a_a"] = reading["power_metrics"]["current_phase_a_a"]
            flat["current_phase_b_a"] = reading["power_metrics"]["current_phase_b_a"]
            flat["current_phase_c_a"] = reading["power_metrics"]["current_phase_c_a"]
            flat["total_active_power_kw"] = reading["power_metrics"]["total_active_power_kw"]
            flat["voltage_phase_a_v"] = reading["power_metrics"]["voltage_phase_a_v"]
            flat["voltage_phase_b_v"] = reading["power_metrics"]["voltage_phase_b_v"]
            flat["voltage_phase_c_v"] = reading["power_metrics"]["voltage_phase_c_v"]

            is_candidate   = ch.charger_id in candidate_ids
            is_stuck       = ch.charger_id in stuck_ids
            is_problematic = ch.charger_id in PROBLEMATIC_CHARGER_IDS

            flat = apply_corruption(flat, is_candidate, is_stuck, is_problematic)
            records.append(flat)

            # ── D) Actually emit duplicate records ───────────────────────────
            if "DUPLICATE" in flat.get("_corruption_flags", []):
                dup = dict(flat)
                dup["_corruption_flags"] = ["DUPLICATE_COPY"]
                records.append(dup)

    # Write as gzip-compressed JSONL
    day_dir = os.path.join(output_dir, "ev_telemetry", date_str)
    os.makedirs(day_dir, exist_ok=True)
    out_path = os.path.join(day_dir, f"ev_telemetry_{date_str}.jsonl.gz")

    with gzip.open(out_path, "wt", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    corruption_count = sum(1 for r in records if r.get("_corruption_flags"))
    corruption_pct   = round(corruption_count / max(len(records), 1) * 100, 1)

    return (
        f"{date_str}: {len(records):,} records "
        f"({corruption_count:,} corrupted, {corruption_pct}%) → {out_path}"
    )

# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
def date_range(start: date, end: date):
    current = start
    while current < end:
        yield current
        current += timedelta(days=1)

def main():
    parser = argparse.ArgumentParser(
        description="Generate multi-year EV telemetry data with intentional 30% corruption"
    )
    parser.add_argument("--output-dir", default="./ev_data_output",
                        help="Root output folder (default: ./ev_data_output)")
    parser.add_argument("--start", default="2026-01-01",
                        help="Start date inclusive (default: 2026-01-01)")
    parser.add_argument("--end", default="2026-06-04",
                        help="End date exclusive (default: 2026-06-04)")
    parser.add_argument("--tick-mins", type=int, default=10,
                        help="Minutes between emitted records (default: 10)")
    parser.add_argument("--workers", type=int, default=4,
                        help="Parallel worker processes (default: 4)")

    args = parser.parse_args()

    start_date = datetime.strptime(args.start, "%Y-%m-%d").date()
    end_date   = datetime.strptime(args.end,   "%Y-%m-%d").date()
    all_days   = list(date_range(start_date, end_date))

    print("=" * 70)
    print("EV Charging Network — Multi-Year Batch Generator (with Corruption)")
    print("=" * 70)
    print(f"  Date range    : {args.start}  →  {args.end}  ({len(all_days)} days)")
    print(f"  Chargers      : {len(CHARGER_REGISTRY)}")
    print(f"  Tick interval : {args.tick_mins} min  ({1440 // args.tick_mins} ticks/day)")
    print(f"  Workers       : {args.workers}")
    print(f"  Output dir    : {os.path.abspath(args.output_dir)}")
    print()
    print("  Corruption layers active:")
    print("    A) Forced fault injection   ~10% of records")
    print("    B) NULL storms              ~8%  of records")
    print("    C) Value range violations   ~5%  of records")
    print("    D) Duplicate records        ~3%  of records")
    print("    E) Identity violations      ~2%  of records")
    print("    F) Business rule violations ~2%  of records")
    print("    ─────────────────────────────────────────────")
    print("    Total corrupted             ~30% of records")
    print()
    print(f"  Problematic chargers (always faulted): {', '.join(sorted(PROBLEMATIC_CHARGER_IDS))}")
    print("=" * 70)

    os.makedirs(args.output_dir, exist_ok=True)

    work_items = [
        (d.strftime("%Y-%m-%d"), args.output_dir, args.tick_mins)
        for d in all_days
    ]

    completed = 0
    failed    = 0
    print(f"\nStarting generation with {args.workers} parallel workers...\n")

    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(generate_day, item): item[0] for item in work_items}
        for future in as_completed(futures):
            date_key = futures[future]
            try:
                msg = future.result()
                completed += 1
                if completed % 50 == 0 or completed <= 5:
                    pct = completed / len(all_days) * 100
                    print(f"  [{completed:4d}/{len(all_days)}  {pct:5.1f}%]  {msg}")
                elif completed % 10 == 0:
                    pct = completed / len(all_days) * 100
                    print(f"  [{completed:4d}/{len(all_days)}  {pct:5.1f}%]  ...")
            except Exception as exc:
                failed += 1
                print(f"  ERROR on {date_key}: {exc}", file=sys.stderr)

    print("\n" + "=" * 70)
    print(f"DONE  ✓  {completed} days generated,  {failed} failed")

    try:
        total_bytes = 0
        ev_dir = os.path.join(args.output_dir, "ev_telemetry")
        for dirpath, _, filenames in os.walk(ev_dir):
            for fn in filenames:
                total_bytes += os.path.getsize(os.path.join(dirpath, fn))
        print(f"Total output size: {total_bytes / 1e9:.2f} GB")
    except Exception:
        pass

    print()
    print("Corruption summary per category visible in Power BI:")
    print("  → Faults & Rev Impact : GROUND_FAULT / CABLE_FAULT / THERMAL_OVERLOAD")
    print("    appear much more frequently; PHASE_IMBALANCE most common (matches your pie)")
    print("  → Faults & Rev Impact : 'Broken Chargers' KPI driven by stuck-faulted chargers")
    print("  → Charger Diagnostics : uptime < 100% for problematic charger IDs")
    print("  → Financials          : net_profit_inr negative from lost_revenue spikes")
    print("  → DQ pipeline (PL_03): NULL rate checks, duplicate checks, value range checks")
    print("    will fire 'Warning' status rows in dq_validation_results")
    print()
    print("Next steps:")
    print(f"  1. Upload the '{os.path.join(args.output_dir, 'ev_telemetry')}' folder")
    print("     into your ADLS Gen 2 'landing' container.")
    print("  2. The folder structure matches ADF expectations:")
    print("     landing/ev_telemetry/YYYYMMDD/ev_telemetry_YYYYMMDD.jsonl.gz")
    print("  3. The '_corruption_flags' column is written to raw_ev_telemetry via PL_01")
    print("     and can be used in gold exception tables to categorise exception types.")
    print("=" * 70)

if __name__ == "__main__":
    main()