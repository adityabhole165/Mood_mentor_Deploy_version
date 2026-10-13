# MoodMentor - typed text / .txt / .csv input, PDF report
# Assessment fixes: 1 centred login | 2 black button text | 3 page loader | 4 light/dark mode
#                   5 five recommendations | 6 white 'More' panel | 7 history calendar
# Note: the Start/End date inputs and their calendar popup are ALWAYS white with black text.

import codecs
import hashlib
import hmac
import html
import io
import json
import os
import re
import secrets
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from collections import Counter
from typing import Any
from xml.sax.saxutils import escape as xml_escape

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

APP_NAME = "MoodMentor"
DEFAULT_API = "https://ml-api-f92t.onrender.com"
TIMEOUT = (10, 180)
HEALTH_TIMEOUT = (5, 60)
MAX_LOGIN_ATTEMPTS = 5

# ---- Input limits ----
MIN_CHARS = 3
MAX_CHARS = 5000
MAX_UPLOAD_BYTES = 1_000_000  # 1 MB
MAX_ROWS = 1000               # max lines / CSV rows read from one file
MAX_BATCH = 10                # max entries analyzed in one batch
RECOMMENDATION_COUNT = 5      # TASK 5: always show exactly 5 recommendations
INPUT_METHODS = ["Write text", "Upload .txt file", "Upload .csv file"]

# ---- PDF report ----
MAX_PDF_ENTRIES = 500  # entries printed in one PDF
PDF_TEXT_FIELDS = ("text", "entry_text", "input_text", "journal_text", "entry", "content")
TEXT_COLUMN_HINTS = (
    "text", "entry", "journal", "journal_entry", "content",
    "message", "note", "notes", "description", "body",
)
EXAMPLES = {
    "Calm but uncertain": "I feel hopeful about the week, but I am uncertain about a few things at work.",
    "Overwhelmed": "I have been feeling overwhelmed lately and find it hard to switch off after work.",
    "Frustrated": "I am frustrated that my efforts were not acknowledged, and I keep replaying the situation.",
}

EVENTS = {
    "helpful": "Helpful",
    "complete": "Done",
    "accept": "Accept",
    "reject": "Reject",
    "skip": "Skip",
    "hide": "Hide",
}
PAGES = ["Overview", "Analyze mood", "Trends", "History", "Reports"]
GREEN, GREEN_DARK, INK = "#24543D", "#183D2C", "#292D28"
PALETTE = [
    "#24543D", "#4F8A68", "#8EB59B", "#C9B98A",
    "#B98F5E", "#77786E", "#A6B8A5", "#D8D2C5",
]

LOGO = (
    '<svg width="34" height="34" viewBox="0 0 40 40" xmlns="http://www.w3.org/2000/svg">'
    '<rect width="40" height="40" rx="11" fill="#24543D"/>'
    '<path d="M7 24c4-9 7-9 10-3s6 6 9-2 5-6 7-3" fill="none" '
    'stroke="#F7F4EC" stroke-width="2.6" stroke-linecap="round"/>'
    '<circle cx="20" cy="13" r="2.4" fill="#C9B98A"/></svg>'
)

st.set_page_config(
    page_title=APP_NAME,
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded",
)

esc = html.escape

st.markdown(
    f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600&family=DM+Sans:wght@400;500;600&display=swap');

:root {{
    --bg: #F7F4EC;
    --surface: #FFFEFA;
    --line: #E2DCCF;
    --ink: {INK};
    --muted: #6F7167;
    --g: {GREEN};
    --gd: {GREEN_DARK};
    --gs: #E7EEE7;
    /* TASK 2: buttons are light so BLACK text is readable in both themes */
    --btn-bg: #E4EFE6;
    --btn-hover: #CFE3D4;
    --btn-primary: #8EB59B;
    --btn-primary-hover: #7FA98D;
}}

html, body, .stApp, [data-testid="stAppViewContainer"] {{
    font-family: 'DM Sans', sans-serif;
    background: var(--bg);
    color: var(--ink);
}}

#MainMenu, footer, [data-testid="stToolbar"] {{
    visibility: hidden;
}}

[data-testid="stHeader"] {{
    display: none !important;
}}

/* ---------- Hide Streamlit header on ALL screen sizes ---------- */
[data-testid="stHeader"],
header[data-testid="stHeader"],
[data-testid="stDecoration"],
[data-testid="stToolbar"] {{
    display: none !important;
    visibility: hidden !important;
    height: 0 !important;
    min-height: 0 !important;
}}

/* Mobile (phones) */
@media (max-width: 768px) {{
    [data-testid="stHeader"],
    header[data-testid="stHeader"] {{
        display: none !important;
    }}
    .block-container {{
        padding-top: 1rem !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }}
}}

/* Tablet */
@media (min-width: 769px) and (max-width: 1024px) {{
    [data-testid="stHeader"],
    header[data-testid="stHeader"] {{
        display: none !important;
    }}
    .block-container {{
        padding-top: 1.5rem !important;
    }}
}}

/* Desktop */
@media (min-width: 1025px) {{
    [data-testid="stHeader"],
    header[data-testid="stHeader"] {{
        display: none !important;
    }}
    .block-container {{
        padding-top: 2rem !important;
    }}
}}

.block-container {{
    padding-top: 2rem;
    max-width: 1180px;
}}

[data-testid="stMain"],
[data-testid="stMain"] p,
[data-testid="stMain"] li,
[data-testid="stMain"] label,
[data-testid="stMain"] [data-testid="stWidgetLabel"] p,
[data-testid="stMain"] [data-testid="stMetricValue"],
[data-testid="stMain"] [data-testid="stMetricLabel"] {{
    color: var(--ink) !important;
}}

[data-testid="stMain"] h1,
[data-testid="stMain"] h2,
[data-testid="stMain"] h3,
[data-testid="stMain"] h4 {{
    font-family: 'Fraunces', serif;
    font-weight: 600;
    letter-spacing: -.01em;
    color: var(--ink) !important;
}}

[data-testid="stSidebar"] {{
    background: var(--gd) !important;
}}

[data-testid="stSidebar"] * {{
    color: #F7F4EC !important;
}}

[data-testid="stSidebar"] input,
[data-testid="stSidebar"] textarea,
[data-testid="stSidebar"] [data-baseweb="select"] > div {{
    background: var(--surface) !important;
    color: var(--ink) !important;
    -webkit-text-fill-color: var(--ink) !important;
}}

[data-testid="stSidebar"] [data-baseweb="select"] *,
[data-testid="stSidebar"] input {{
    color: var(--ink) !important;
}}

[data-testid="stSidebar"] hr {{
    border-color: rgba(247, 244, 236, .18);
}}

.brand {{
    display: flex;
    align-items: center;
    gap: .7rem;
    margin-bottom: .2rem;
}}

.brand b {{
    font-family: 'Fraunces', serif;
    font-size: 1.35rem;
}}

.hero {{
    padding: 2rem 2.2rem;
    border-radius: 20px;
    background: linear-gradient(135deg, #183D2C, #2D6549);
    margin-bottom: 1.4rem;
}}

.hero h1, .hero p {{
    color: #FFFEFA !important;
    margin: 0;
}}

.hero h1 {{
    font-family: 'Fraunces', serif !important;
    font-size: 2.1rem;
    font-weight: 500;
}}

.hero p {{
    color: #DCE8DD !important;
    margin-top: .5rem;
    max-width: 640px;
}}

.chip {{
    display: inline-block;
    padding: .18rem .7rem;
    margin: .15rem .25rem .15rem 0;
    border-radius: 999px;
    background: var(--gs);
    color: var(--gd);
    font-size: .82rem;
    font-weight: 500;
}}

.muted {{
    color: var(--muted) !important;
    font-size: .88rem;
}}

.big-emotion {{
    font-family: 'Fraunces', serif;
    font-size: 2.4rem;
    color: var(--g);
    line-height: 1.1;
    margin: .2rem 0;
}}

div[data-testid="stMetric"] {{
    background: var(--surface);
    border: 1px solid var(--line);
    padding: 14px 16px;
    border-radius: 14px;
}}

[data-testid="stMain"] [data-testid="stVerticalBlockBorderWrapper"] {{
    border: 1px solid var(--line) !important;
    border-radius: 14px !important;
    background: var(--surface) !important;
}}

[data-testid="stMain"] input,
[data-testid="stMain"] textarea,
[data-testid="stMain"] [data-baseweb="select"] > div,
[data-testid="stMain"] [data-baseweb="input"] > div {{
    background: var(--surface) !important;
    color: var(--ink) !important;
    -webkit-text-fill-color: var(--ink) !important;
    border-color: var(--line) !important;
    border-radius: 10px !important;
}}

[data-testid="stMain"] [data-baseweb="select"] *,
[data-testid="stMain"] [role="option"] {{
    color: var(--ink) !important;
}}

/* Global buttons - TASK 2: black text on light buttons */
[data-testid="stMain"] .stButton > button,
[data-testid="stMain"] [data-testid="stFormSubmitButton"] button,
[data-testid="stMain"] .stDownloadButton > button {{
    border-radius: 10px;
    border: 1px solid #6B7F70;
    background: var(--btn-bg) !important;
    color: #000000 !important;
    -webkit-text-fill-color: #000000 !important;
    font-weight: 600;
    transition: all .15s ease;
}}

[data-testid="stMain"] .stButton > button *,
[data-testid="stMain"] [data-testid="stFormSubmitButton"] button *,
[data-testid="stMain"] .stDownloadButton > button * {{
    color: #000000 !important;
    -webkit-text-fill-color: #000000 !important;
}}

[data-testid="stMain"] .stButton > button:hover,
[data-testid="stMain"] [data-testid="stFormSubmitButton"] button:hover,
[data-testid="stMain"] .stDownloadButton > button:hover {{
    background: var(--btn-hover) !important;
    border-color: #000000;
}}

/* "More" trigger on recommendation cards: white, black border + text (TASK 6) */
[data-testid="stMain"] [class*="st-key-more_"] button,
[data-testid="stMain"] [class*="st-key-more_"] [data-testid="stPopoverButton"] {{
    background: #FFFFFF !important;
    border: 1.5px solid #000000 !important;
    border-radius: 10px !important;
    color: #000000 !important;
    -webkit-text-fill-color: #000000 !important;
    font-weight: 600 !important;
}}
[data-testid="stMain"] [class*="st-key-more_"] button:hover,
[data-testid="stMain"] [class*="st-key-more_"] [data-testid="stPopoverButton"]:hover {{
    background: #F0F0F0 !important;
}}
[data-testid="stMain"] [class*="st-key-more_"] button *,
[data-testid="stMain"] [class*="st-key-more_"] button svg {{
    color: #000000 !important;
    fill: #000000 !important;
    -webkit-text-fill-color: #000000 !important;
}}

[data-testid="stMain"] button:focus-visible {{
    outline: 2px solid #8EAC96 !important;
    outline-offset: 2px;
}}

[data-testid="stMain"] [data-testid="stTabs"] button {{
    color: var(--ink) !important;
    background: transparent !important;
}}

[data-testid="stMain"] [data-testid="stTabs"] button[aria-selected="true"] {{
    color: var(--g) !important;
}}

:root, .stApp {{
    color-scheme: light;
}}

[data-testid="stMain"] [data-baseweb="input"],
[data-testid="stMain"] [data-baseweb="base-input"],
[data-testid="stMain"] [data-baseweb="textarea"] {{
    background: var(--surface) !important;
    border-color: var(--line) !important;
}}

[data-testid="stMain"] [data-baseweb="input"] input,
[data-testid="stMain"] [data-baseweb="base-input"] input,
[data-testid="stMain"] textarea {{
    color: var(--ink) !important;
    -webkit-text-fill-color: var(--ink) !important;
    caret-color: #24543D;
}}

[data-testid="stMain"] input:-webkit-autofill {{
    -webkit-box-shadow: 0 0 0 40px var(--surface) inset !important;
    -webkit-text-fill-color: var(--ink) !important;
}}

[data-testid="stMain"] input::placeholder,
[data-testid="stMain"] textarea::placeholder {{
    color: #8A8B80 !important;
    -webkit-text-fill-color: #8A8B80 !important;
    opacity: 1;
}}

[data-testid="stMain"] [data-baseweb="input"] button svg {{
    fill: #6F7167;
}}

[data-testid="stMain"] [data-testid="stForm"] {{
    background: transparent;
    border: none;
    padding: 0;
}}

[data-testid="stMain"] .brand b {{
    color: var(--ink);
}}

[data-testid="stMain"] [data-testid="stRadio"] [role="radiogroup"] {{
    gap: .3rem;
    flex-wrap: wrap;
}}

[data-testid="stMain"] [data-testid="stRadio"] label {{
    border-radius: 999px;
    padding: .4rem 1rem;
    margin: 0;
    cursor: pointer;
    border: 1px solid transparent;
    transition: background .15s ease;
}}

[data-testid="stMain"] [data-testid="stRadio"] label > div:first-child {{
    display: none;
}}

[data-testid="stMain"] [data-testid="stRadio"] label:hover {{
    background: var(--gs);
}}

[data-testid="stMain"] [data-testid="stRadio"] label:has(input:checked) {{
    background: var(--g);
}}

[data-testid="stMain"] [data-testid="stRadio"] label:has(input:checked) p {{
    color: #FFFFFF !important;
}}

/* File uploader */
[data-testid="stMain"] [data-testid="stFileUploaderDropzone"] {{
    background: var(--surface) !important;
    border: 1.5px dashed #B9C4B8 !important;
    border-radius: 12px !important;
}}
[data-testid="stMain"] [data-testid="stFileUploaderDropzone"] *,
[data-testid="stMain"] [data-testid="stFileUploaderFile"] * {{
    color: var(--ink) !important;
}}
[data-testid="stMain"] [data-testid="stFileUploaderDropzone"] button {{
    background: var(--btn-primary) !important;
    border-color: #5E8A6D !important;
}}
[data-testid="stMain"] [data-testid="stFileUploaderDropzone"] button * {{
    color: #000000 !important;
    -webkit-text-fill-color: #000000 !important;
}}

/* Overview action buttons */
[data-testid="stMain"] .st-key-start_checkin_container button {{
    background: linear-gradient(135deg, #A9D1B6, #8EB59B) !important;
    color: #000000 !important;
    -webkit-text-fill-color: #000000 !important;
    border: 1px solid #5E8A6D !important;
    border-radius: 12px !important;
    font-size: 18px !important;
    font-weight: 800 !important;
    letter-spacing: .3px !important;
    padding: 14px 22px !important;
    min-height: 54px !important;
    box-shadow: 0 5px 14px rgba(36, 84, 61, .25) !important;
    transition: all .2s ease-in-out !important;
}}

[data-testid="stMain"] .st-key-start_checkin_container button * {{
    color: #000000 !important;
    -webkit-text-fill-color: #000000 !important;
}}

[data-testid="stMain"] .st-key-start_checkin_container button:hover {{
    background: linear-gradient(135deg, #9CC9AB, #7FA98D) !important;
    border-color: #000000 !important;
    box-shadow: 0 8px 20px rgba(36, 84, 61, .35) !important;
    transform: translateY(-2px);
}}

[data-testid="stMain"] .st-key-start_checkin_container button:focus-visible {{
    outline: 3px solid #8EB59B !important;
    outline-offset: 3px !important;
}}

[data-testid="stMain"] .st-key-start_checkin_container button:active {{
    transform: translateY(0);
    box-shadow: 0 2px 6px rgba(36, 84, 61, .25) !important;
}}

/* ---------- Primary buttons (Sign in, Create account, Analyze my mood...) ----------
   TASK 2: light-green background with BLACK label. */
[data-testid="stMain"] button[kind="primary"],
[data-testid="stMain"] button[data-testid="stBaseButton-primary"],
[data-testid="stMain"] button[data-testid="stBaseButton-primaryFormSubmit"],
[data-testid="stMain"] .st-key-analyze_btn button {{
    background: var(--btn-primary) !important;
    border: 1px solid #5E8A6D !important;
    color: #000000 !important;
    -webkit-text-fill-color: #000000 !important;
    font-weight: 700 !important;
}}

[data-testid="stMain"] button[kind="primary"]:hover,
[data-testid="stMain"] button[data-testid="stBaseButton-primary"]:hover,
[data-testid="stMain"] button[data-testid="stBaseButton-primaryFormSubmit"]:hover,
[data-testid="stMain"] .st-key-analyze_btn button:hover {{
    background: var(--btn-primary-hover) !important;
    border-color: #000000 !important;
}}

[data-testid="stMain"] button[kind="primary"] *,
[data-testid="stMain"] button[data-testid="stBaseButton-primary"] *,
[data-testid="stMain"] button[data-testid="stBaseButton-primaryFormSubmit"] *,
[data-testid="stMain"] .st-key-analyze_btn button * {{
    color: #000000 !important;
    -webkit-text-fill-color: #000000 !important;
}}

/* ---------- Date inputs (Start / End) - ALWAYS white box, black text ----------
   Fixed colours (no theme variables) so it looks the same in light and dark mode. */
[data-testid="stMain"] [data-testid="stDateInput"] [data-baseweb="input"],
[data-testid="stMain"] [data-testid="stDateInput"] [data-baseweb="base-input"],
[data-testid="stMain"] [data-testid="stDateInput"] [data-baseweb="input"] > div,
[data-testid="stMain"] [data-testid="stDateInput"] input {{
    background: #FFFFFF !important;
    background-color: #FFFFFF !important;
    color: #000000 !important;
    -webkit-text-fill-color: #000000 !important;
    caret-color: #000000;
    border-color: #C9CFCB !important;
}}
[data-testid="stMain"] [data-testid="stDateInput"] input::placeholder {{
    color: #6B6F6B !important;
    -webkit-text-fill-color: #6B6F6B !important;
    opacity: 1;
}}

/* ---------- Calendar popup: black body with white text in Light mode ----------
   The popup renders in a portal outside stMain, so these rules are global. */
[data-baseweb="popover"]:has([data-baseweb="calendar"]),
[data-baseweb="popover"]:has([data-baseweb="calendar"]) > div,
[data-baseweb="calendar"] {{
    background: #000000 !important;
    background-color: #000000 !important;
    color: #FFFFFF !important;
    color-scheme: light;
    border-radius: 12px;
}}

[data-baseweb="popover"]:has([data-baseweb="calendar"]) > div {{
    border: 1px solid #D1D5DB;
    box-shadow: 0 10px 28px rgba(0, 0, 0, .18);
}}

/* Header and weekday row: white text over the black body */
[data-baseweb="calendar"] *,
[data-baseweb="calendar"] button,
[data-baseweb="calendar"] [role="presentation"],
[data-baseweb="calendar"] [role="columnheader"],
[data-baseweb="calendar"] [data-baseweb="select"] * {{
    color: #F7F4EC !important;
    -webkit-text-fill-color: #F7F4EC !important;
}}

[data-baseweb="calendar"] div:not([role="gridcell"]),
[data-baseweb="calendar"] button,
[data-baseweb="calendar"] [data-baseweb="select"] > div {{
    background-color: #000000 !important;
}}

[data-baseweb="calendar"] svg,
[data-baseweb="calendar"] svg * {{
    fill: #F7F4EC !important;
}}

/* Day cells: slate-blue background with dark date numbers */
[data-baseweb="calendar"] [role="gridcell"],
[data-baseweb="calendar"] [role="gridcell"] * {{
    background-color: #000000 !important;
    color: #F7F4EC !important;
    -webkit-text-fill-color: #F7F4EC !important;
}}

[data-baseweb="calendar"] [role="gridcell"]:hover,
[data-baseweb="calendar"] [role="gridcell"]:hover * {{
    background-color: #262626 !important;
}}

/* Disabled days: remain white-text on black, slightly faded */
[data-baseweb="calendar"] [role="gridcell"][aria-disabled="true"],
[data-baseweb="calendar"] [role="gridcell"][aria-disabled="true"] * {{
    opacity: .45;
}}

/* Selected day: dark-gray highlight, with white date text */
[data-baseweb="calendar"] [role="gridcell"][aria-selected="true"],
[data-baseweb="calendar"] [role="gridcell"][aria-selected="true"] * {{
    background-color: #333333 !important;
    color: #FFFFFF !important;
    -webkit-text-fill-color: #FFFFFF !important;
    opacity: 1;
    font-weight: 700;
}}

/* Select menus (dropdown lists) */
[data-baseweb="popover"] [data-baseweb="menu"],
[data-baseweb="popover"] ul[role="listbox"] {{
    background: var(--surface) !important;
}}
[data-baseweb="popover"] [role="option"],
[data-baseweb="popover"] [role="option"] * {{
    color: var(--ink) !important;
    -webkit-text-fill-color: var(--ink) !important;
}}
[data-baseweb="popover"] [role="option"]:hover,
[data-baseweb="popover"] [role="option"][aria-selected="true"] {{
    background: var(--gs) !important;
}}

/* ---------- "More" panel (TASK 6) ----------
   White panel, every button inside has a black border and black text.
   st.popover renders in a portal, so the rules are global. */
[data-testid="stPopoverBody"],
div[data-baseweb="popover"]:has([data-testid="stPopoverBody"]) > div {{
    background: #FFFFFF !important;
    border-radius: 12px;
}}
[data-testid="stPopoverBody"] {{
    border: 1px solid #D1D5DB;
}}
[data-testid="stPopoverBody"] *,
[data-testid="stPopoverBody"] label p {{
    color: #000000 !important;
    -webkit-text-fill-color: #000000 !important;
}}
[data-testid="stPopoverBody"] button {{
    background: #FFFFFF !important;
    border: 1.5px solid #000000 !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
}}
[data-testid="stPopoverBody"] button:hover {{
    background: #F0F0F0 !important;
}}

@media (max-width: 700px) {{
    .hero {{ padding: 1.3rem; }}
    .hero h1 {{ font-size: 1.6rem; }}
}}
</style>
""",
    unsafe_allow_html=True,
)


# ---------- TASK 4: light / dark theme ----------
# Light colours live in the :root block above. Dark mode only OVERRIDES them.
DARK_CSS = """
:root {
    --bg: #111713;
    --surface: #1B241F;
    --line: #33423A;
    --ink: #ECEFE9;
    --muted: #A5ADA6;
    --gs: #26352D;
}
html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
    background: var(--bg) !important;
    color: var(--ink);
}
[data-testid="stSidebar"] { background: #0C1812 !important; }
.chip { background: #26352D; color: #CFE3D4; }
.big-emotion { color: #8EB59B; }
.brand b { color: var(--ink); }
.muted { color: var(--muted) !important; }
[data-testid="stMain"] [data-testid="stCaptionContainer"],
[data-testid="stMain"] [data-testid="stCaptionContainer"] * { color: var(--muted) !important; }
[data-testid="stMain"] [data-testid="stTabs"] button[aria-selected="true"] { color: #8EB59B !important; }
[data-testid="stMain"] [data-testid="stAlert"] * { color: var(--ink) !important; }
[data-testid="stMain"] [data-testid="stExpander"] details {
    background: var(--surface); border-color: var(--line);
}
[data-testid="stMain"] [data-testid="stExpander"] summary,
[data-testid="stMain"] [data-testid="stExpander"] summary * { color: var(--ink) !important; }
[data-testid="stMain"] hr { border-color: var(--line) !important; }
[data-testid="stMain"] [data-testid="stDataFrame"],
[data-testid="stMain"] [data-testid="stJson"] { filter: invert(1) hue-rotate(180deg); }
/* Keep the calendar neutral in Dark mode; the slate palette is Light-mode only. */
[data-baseweb="popover"]:has([data-baseweb="calendar"]),
[data-baseweb="popover"]:has([data-baseweb="calendar"]) > div,
[data-baseweb="calendar"] { background: #FFFFFF !important; background-color: #FFFFFF !important; color: #000000 !important; }
[data-baseweb="calendar"] *,
[data-baseweb="calendar"] button,
[data-baseweb="calendar"] [role="presentation"],
[data-baseweb="calendar"] [role="columnheader"],
[data-baseweb="calendar"] [data-baseweb="select"] * { color: #000000 !important; -webkit-text-fill-color: #000000 !important; }
[data-baseweb="calendar"] div:not([role="gridcell"]),
[data-baseweb="calendar"] button,
[data-baseweb="calendar"] [data-baseweb="select"] > div,
[data-baseweb="calendar"] [role="gridcell"],
[data-baseweb="calendar"] [role="gridcell"] * { background-color: #FFFFFF !important; }
[data-baseweb="calendar"] svg, [data-baseweb="calendar"] svg * { fill: #000000 !important; }
[data-baseweb="calendar"] [role="gridcell"][aria-selected="true"],
[data-baseweb="calendar"] [role="gridcell"][aria-selected="true"] * { background-color: #CFE3D4 !important; color: #000000 !important; -webkit-text-fill-color: #000000 !important; }
"""

THEME_NAME = {"light": "Light", "dark": "Dark"}


def is_dark() -> bool:
    return st.session_state.get("theme", "light") == "dark"


def toggle_theme():
    st.session_state.theme = "light" if is_dark() else "dark"


def inject_theme():
    """Add the dark overrides after the base CSS when dark mode is on."""
    if is_dark():
        st.markdown("<style>" + DARK_CSS + "</style>", unsafe_allow_html=True)


def theme_button(key: str):
    """The Light mode / Dark mode switch button (shows the mode you will switch TO)."""
    label = "☀️ Light mode" if is_dark() else "🌙 Dark mode"
    st.button(label, key=key, on_click=toggle_theme, use_container_width=True)


def chart_ink() -> str:
    return "#ECEFE9" if is_dark() else "#000000"


# ---------- TASK 3: page loader ----------
# Pure CSS: a full-screen overlay that fades out by itself, so it needs no JavaScript.
LOADER_HTML = """<style>
#mm-loader {
  position: fixed; inset: 0; z-index: 999999;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: .6rem; background: var(--bg);
  animation: mm-loader-hide .6s ease 2.6s forwards;
}
@keyframes mm-loader-hide { to { opacity: 0; visibility: hidden; pointer-events: none; } }
#mm-loader .mm-compass { width: 100px; height: 100px; margin-bottom: .4rem; }
#mm-loader .mm-needle { transform-origin: 48px 48px; animation: mm-swing 2.2s ease-in-out infinite; }
@keyframes mm-swing { 0% { transform: rotate(-40deg); } 50% { transform: rotate(40deg); } 100% { transform: rotate(-40deg); } }
#mm-loader .mm-title { font-family: 'Fraunces', serif; font-size: 2.2rem; font-weight: 600; color: var(--ink); }
#mm-loader .mm-sub { font-size: 1.05rem; letter-spacing: .12em; text-transform: uppercase; color: var(--muted); }
#mm-loader .mm-text { font-size: 1rem; color: var(--ink); margin-top: .4rem; }
#mm-loader .mm-text::after { content: ""; animation: mm-dots 1.2s steps(1, end) infinite; }
@keyframes mm-dots { 0% { content: ""; } 25% { content: "."; } 50% { content: ".."; } 75% { content: "..."; } }
</style>
<div id="mm-loader">
<svg class="mm-compass" viewBox="0 0 96 96" xmlns="http://www.w3.org/2000/svg">
<circle cx="48" cy="48" r="44" fill="none" stroke="#8EB59B" stroke-width="4"/>
<circle cx="48" cy="48" r="36" fill="none" stroke="#C9B98A" stroke-width="1.5" stroke-dasharray="3 5"/>
<g class="mm-needle">
<polygon points="48,14 56,48 48,43 40,48" fill="#C9B98A"/>
<polygon points="48,82 56,48 48,53 40,48" fill="#4F8A68"/>
</g>
<circle cx="48" cy="48" r="4" fill="#8EB59B"/>
</svg>
<div class="mm-title">Mood Mentor</div>
<div class="mm-sub">The Mind Compass</div>
<div class="mm-text">Loading</div>
</div>"""


def show_loader():
    """Show the loader once per browser session (first page load)."""
    if st.session_state.get("loader_done"):
        return
    st.markdown(LOADER_HTML, unsafe_allow_html=True)
    st.session_state.loader_done = True


# ---------- TASK 1: centre the login screen ----------
LOGIN_CSS = """
<style>
/* Centre the whole login page horizontally AND vertically */
.block-container {
    min-height: 100vh;
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    justify-content: center;
}
.block-container > [data-testid="stVerticalBlock"] { width: 100%; }

/* Left information box: everything centred */
.st-key-login_left { text-align: center; align-items: center; }
.st-key-login_left .brand { justify-content: center; }
.st-key-login_left [data-testid="stMarkdownContainer"],
.st-key-login_left h1,
.st-key-login_left p { text-align: center !important; }

/* Right sign-in box: centred, comfortable width */
.st-key-login_right { max-width: 460px; margin: 0 auto; width: 100%; }
</style>
"""


# ---------- API ----------
def api_base() -> str:
    configured = ""
    try:
        configured = st.secrets.get("MOOD_MENTOR_API_URL", "")
    except Exception:
        pass
    return (os.getenv("MOOD_MENTOR_API_URL") or configured or DEFAULT_API).rstrip("/")


def api_request(method, path, *, params=None, payload=None, raw=False, timeout=TIMEOUT):
    try:
        response = requests.request(
            method,
            f"{api_base()}{path}",
            params=params,
            json=payload,
            timeout=timeout,
        )
        if not response.ok:
            try:
                detail = response.json().get("detail", response.text)
            except Exception:
                detail = response.text
            raise RuntimeError(f"API {response.status_code}: {detail}")
        return response.content if raw else response.json()
    except requests.Timeout as exc:
        raise RuntimeError(
            "The API took too long to respond. The model may be warming up on Render; retry in a minute."
        ) from exc
    except requests.RequestException as exc:
        raise RuntimeError(f"Could not reach the MoodMentor API at {api_base()}: {exc}") from exc


def safe(fn, *args, quiet=False, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        if not quiet:
            st.error(str(exc))
        return None


# ---------- Demo auth (use a managed identity provider + persistent DB in production) ----------
AUTH_DB = os.getenv("MOOD_MENTOR_AUTH_DB", "/tmp/moodmentor_accounts.sqlite3")


def auth_conn():
    conn = sqlite3.connect(AUTH_DB)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS accounts (
            username TEXT PRIMARY KEY,
            salt TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )"""
    )
    conn.commit()
    return conn


def hash_pw(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 240_000).hex()


def create_account(username, password):
    username = username.strip().lower()
    if not 3 <= len(username) <= 64 or not all(c.isalnum() or c in "._-" for c in username):
        raise ValueError("Use 3-64 characters: letters, numbers, dot, underscore or hyphen.")
    if len(password) < 10:
        raise ValueError("Password must be at least 10 characters.")
    salt = secrets.token_bytes(16)
    conn = auth_conn()
    try:
        conn.execute(
            "INSERT INTO accounts VALUES (?,?,?,?)",
            (username, salt.hex(), hash_pw(password, salt), datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    except sqlite3.IntegrityError as exc:
        raise ValueError("That username already exists.") from exc
    finally:
        conn.close()


def verify_account(username, password) -> bool:
    conn = auth_conn()
    try:
        row = conn.execute(
            "SELECT salt,password_hash FROM accounts WHERE username=?",
            (username.strip().lower(),),
        ).fetchone()
    finally:
        conn.close()
    return bool(row) and hmac.compare_digest(
        hash_pw(password, bytes.fromhex(row[0])), row[1]
    )


# ---------- Helpers ----------
def records(payload: Any):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("items", "records", "data", "history", "trend", "emotion_frequency"):
            if isinstance(payload.get(key), list):
                return payload[key]
    return []


def frame(payload):
    rows = records(payload)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def as_dict(value):
    return value if isinstance(value, dict) else {}


def pick(obj, *keys, default=None):
    for key in keys:
        if isinstance(obj, dict) and obj.get(key) is not None:
            return obj[key]
    return default


def date_col(df):
    return next(
        (column for column in ("timestamp", "created_at", "date", "recorded_at", "period")
         if column in df.columns),
        None,
    )


def style_fig(fig, height=320):
    ink = chart_ink()
    surface = "#1B241F" if is_dark() else "#FFFEFA"
    grid = "#33423A" if is_dark() else "#E2DCCF"
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=40, b=10),
        paper_bgcolor=surface,
        plot_bgcolor=surface,
        font=dict(family="DM Sans", color=ink),
        xaxis=dict(color=ink, title_font=dict(color=ink), tickfont=dict(color=ink), gridcolor=grid),
        yaxis=dict(color=ink, title_font=dict(color=ink), tickfont=dict(color=ink), gridcolor=grid),
        legend=dict(font=dict(color=ink)),
        title_font=dict(color=ink),
        uniformtext=dict(minsize=10, mode="hide"),
        colorway=PALETTE,
    )
    return fig


def hero(title, subtitle):
    st.markdown(
        f'<div class="hero"><h1>{esc(str(title))}</h1><p>{esc(str(subtitle))}</p></div>',
        unsafe_allow_html=True,
    )


def chips_html(items):
    return "".join(f'<span class="chip">{esc(str(item))}</span>' for item in items)


def go(page):
    st.session_state.page = page


def safe_key(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", str(value))


def preview(text: str, limit: int = 60) -> str:
    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


# ---------- Input pipeline: read -> validate -> preprocess ----------
class InputError(ValueError):
    """A user-facing problem with the supplied input."""


@dataclass
class Loaded:
    entries: list = field(default_factory=list)   # [{"label": str, "text": str}]
    problems: list = field(default_factory=list)  # human-readable rejection reasons
    notes: list = field(default_factory=list)     # informational messages
    has_input: bool = False


_ZERO_WIDTH_RE = re.compile("[\u200b-\u200f\u202a-\u202e\u2060\ufeff]")
_CONTROL_RE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def preprocess_text(raw) -> str:
    """Normalise text before it is sent to the API."""
    text = unicodedata.normalize("NFKC", str(raw))
    text = _ZERO_WIDTH_RE.sub("", text)
    text = _CONTROL_RE.sub(" ", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def validate_entry(raw):
    """Return (clean_text, None) for valid input or (None, reason) for invalid input."""
    if raw is None:
        return None, "the entry is empty."
    text = preprocess_text(raw)
    if not text:
        return None, "the entry is empty."
    if len(text) < MIN_CHARS:
        return None, f"too short (minimum {MIN_CHARS} characters)."
    if not any(ch.isalpha() for ch in text):
        return None, "contains no letters, so there is nothing to analyze."
    if len(text) > MAX_CHARS:
        return None, f"too long ({len(text):,} characters; maximum {MAX_CHARS:,})."
    return text, None


def build_entries(items, empty_msg="No text found: the input is empty."):
    """items: iterable of (label, raw_text). Blank items are skipped, invalid ones reported."""
    loaded = Loaded(has_input=True)
    blanks = 0
    for label, raw in items:
        if raw is None or not str(raw).strip():
            blanks += 1
            continue
        text, problem = validate_entry(raw)
        if problem:
            loaded.problems.append(f"{label}: {problem}")
        else:
            loaded.entries.append({"label": label, "text": text})
    if blanks and (loaded.entries or loaded.problems):
        loaded.notes.append(f"Skipped {blanks} blank entr{'y' if blanks == 1 else 'ies'}.")
    if not loaded.entries and not loaded.problems:
        loaded.problems.append(empty_msg)
    return loaded


def decode_upload(data: bytes) -> str:
    if not data:
        raise InputError("The file is empty.")
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError as exc:
            raise InputError("The file could not be decoded as text.") from exc
    if b"\x00" in data:
        raise InputError("This looks like a binary file, not plain text.")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def read_upload(file, extension: str) -> str:
    name = str(getattr(file, "name", "") or "")
    if not name.lower().endswith(extension):
        raise InputError(f"Please upload a {extension} file (received “{name or 'unnamed file'}”).")
    data = file.getvalue()
    if len(data) > MAX_UPLOAD_BYTES:
        raise InputError(
            f"The file is too large ({len(data) / 1_000_000:.1f} MB). "
            f"The limit is {MAX_UPLOAD_BYTES / 1_000_000:.0f} MB."
        )
    return decode_upload(data)


def load_typed(text) -> Loaded:
    loaded = build_entries(
        [("Typed entry", text)],
        empty_msg="The entry is empty. Write a journal entry first.",
    )
    loaded.has_input = bool(text and str(text).strip())
    return loaded


def load_txt(file, per_line: bool = False) -> Loaded:
    text = read_upload(file, ".txt")
    if per_line:
        lines = text.splitlines()
        items = [(f"Line {i}", line) for i, line in enumerate(lines[:MAX_ROWS], 1)]
        loaded = build_entries(items, empty_msg="The text file has no readable text.")
        if len(lines) > MAX_ROWS:
            loaded.notes.append(f"Only the first {MAX_ROWS:,} lines were read.")
        return loaded
    return build_entries(
        [("Text file", text)], empty_msg="The text file has no readable text."
    )


def parse_csv(file) -> pd.DataFrame:
    text = read_upload(file, ".csv")
    if not text.strip():
        raise InputError("The CSV file is empty.")
    first_line = text.splitlines()[0]
    delimiter = max((",", ";", "\t", "|"), key=first_line.count)
    if first_line.count(delimiter) == 0:
        delimiter = ","
    try:
        df = pd.read_csv(
            io.StringIO(text), dtype=str, keep_default_na=False, sep=delimiter
        )
    except pd.errors.EmptyDataError as exc:
        raise InputError("The CSV file is empty.") from exc
    except (pd.errors.ParserError, ValueError) as exc:
        raise InputError(f"Could not read this CSV file: {exc}") from exc
    df.columns = [str(column).strip() for column in df.columns]
    if df.empty or len(df.columns) == 0:
        raise InputError("The CSV has a header row but no data rows.")
    return df


def guess_text_column(df: pd.DataFrame) -> str:
    lowered = {str(column).lower(): column for column in df.columns}
    for hint in TEXT_COLUMN_HINTS:
        if hint in lowered:
            return lowered[hint]
    return max(df.columns, key=lambda column: df[column].astype(str).str.len().mean())


def load_csv(df: pd.DataFrame, column: str) -> Loaded:
    if column not in df.columns:
        raise InputError(f"Column “{column}” was not found in the CSV.")
    values = df[column].tolist()
    items = [(f"Row {i}", value) for i, value in enumerate(values[:MAX_ROWS], 2)]
    loaded = build_entries(items, empty_msg=f"The column “{column}” has no text.")
    if len(values) > MAX_ROWS:
        loaded.notes.append(f"Only the first {MAX_ROWS:,} rows were read.")
    return loaded


def load_csv_file(file, column=None) -> Loaded:
    df = parse_csv(file)
    return load_csv(df, column or guess_text_column(df))


# ---------- Input self-test (runs locally, never calls the API) ----------
class _FakeUpload:
    def __init__(self, name: str, data: bytes):
        self.name = name
        self._data = data
        self.size = len(data)

    def getvalue(self) -> bytes:
        return self._data


def run_input_self_test():
    long_text = "word " * (MAX_CHARS // 5 + 20)
    big_file = b"x" * (MAX_UPLOAD_BYTES + 1)
    cases = [
        ("Typed: valid text", lambda: load_typed("I feel calm today."), 1),
        ("Typed: empty", lambda: load_typed(""), 0),
        ("Typed: whitespace only", lambda: load_typed("   \n\t  "), 0),
        ("Typed: numbers/symbols only", lambda: load_typed("12345 !!! ???"), 0),
        ("Typed: too long", lambda: load_typed(long_text), 0),
        (".txt: valid UTF-8", lambda: load_txt(_FakeUpload("a.txt", "I feel hopeful.".encode())), 1),
        (".txt: UTF-16 with BOM", lambda: load_txt(_FakeUpload("a.txt", "Feeling okay today".encode("utf-16"))), 1),
        (".txt: empty file", lambda: load_txt(_FakeUpload("a.txt", b"")), 0),
        (".txt: binary content", lambda: load_txt(_FakeUpload("a.txt", b"\x00\x01\x02\xff")), 0),
        (".txt: wrong extension", lambda: load_txt(_FakeUpload("a.pdf", b"hello there")), 0),
        (".txt: file too large", lambda: load_txt(_FakeUpload("big.txt", big_file)), 0),
        (
            ".txt: one entry per line (blank lines skipped)",
            lambda: load_txt(_FakeUpload("a.txt", b"I am happy.\n\n   \nI am worried.\n"), per_line=True),
            2,
        ),
        (
            ".csv: 'text' column, blank row skipped",
            lambda: load_csv_file(_FakeUpload("a.csv", b"id,text\n1,I feel great\n2,\n3,I am tired\n")),
            2,
        ),
        (".csv: semicolon delimiter", lambda: load_csv_file(_FakeUpload("a.csv", b"id;entry\n1;Feeling low\n")), 1),
        (".csv: single column", lambda: load_csv_file(_FakeUpload("a.csv", b"journal\nToday was fine\n")), 1),
        (".csv: header only", lambda: load_csv_file(_FakeUpload("a.csv", b"text\n")), 0),
        (".csv: empty file", lambda: load_csv_file(_FakeUpload("a.csv", b"")), 0),
        (".csv: all rows blank or invalid", lambda: load_csv_file(_FakeUpload("a.csv", b"text\n \n123\n")), 0),
    ]
    rows = []
    for name, fn, expected in cases:
        try:
            loaded = fn()
            count = len(loaded.entries)
            detail = (
                f"{count} valid entr{'y' if count == 1 else 'ies'}"
                if count
                else (loaded.problems[0] if loaded.problems else "no entries")
            )
        except InputError as exc:
            count, detail = 0, str(exc)
        except Exception as exc:  # unexpected crash = failed test
            count, detail = -1, f"Unexpected error: {exc}"
        rows.append(
            {
                "Test": name,
                "Expected": f"{expected} valid entr{'y' if expected == 1 else 'ies'}" if expected else "Rejected",
                "Result": detail,
                "Status": "✅ Pass" if count == expected else "❌ Fail",
            }
        )
    cleaned = preprocess_text("  Hello \u200b  world\t ")
    rows.append(
        {
            "Test": "Preprocessing: whitespace and zero-width cleanup",
            "Expected": "Hello world",
            "Result": cleaned,
            "Status": "✅ Pass" if cleaned == "Hello world" else "❌ Fail",
        }
    )
    return rows


# ---------- PDF report ----------
def pdf_text(value) -> str:
    """Make text safe for the built-in PDF fonts (Windows-1252 range)."""
    text = unicodedata.normalize("NFKC", str(value))
    return text.encode("cp1252", errors="replace").decode("cp1252")


def pdf_para(value) -> str:
    return xml_escape(pdf_text(value)).replace("\n", "<br/>")


def _num(value, percent=False) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    if number != number:
        return "-"
    return f"{number:.0%}" if percent else f"{number:.2f}"


def _label(value) -> str:
    if value is None or (isinstance(value, float) and value != value):
        return "-"
    if isinstance(value, str) and value.strip().startswith("["):
        try:
            value = json.loads(value)
        except ValueError:
            pass
    if isinstance(value, (list, tuple)):
        value = ", ".join(str(v) for v in value) or "-"
    return str(value).replace("_", " ").title()


def entries_from_history(df) -> list:
    """Turn an emotion-history DataFrame into PDF entries (newest first)."""
    if df is None or df.empty:
        return []
    data = df.copy()
    when_col = date_col(data)
    if when_col:
        data["_ts"] = pd.to_datetime(data[when_col], errors="coerce", utc=True)
        data = data.sort_values("_ts", ascending=False)
    text_col = next((c for c in PDF_TEXT_FIELDS if c in data.columns), None)
    entries = []
    for _, row in data.iterrows():
        when = "-"
        if when_col:
            stamp = row["_ts"]
            when = stamp.strftime("%Y-%m-%d %H:%M") if pd.notna(stamp) else str(row[when_col])
        text = ""
        if text_col and isinstance(row[text_col], str):
            text = row[text_col]
        entries.append(
            {
                "when": when,
                "text": text,
                "emotion": _label(row.get("dominant_emotion")),
                "confidence": _num(row.get("confidence"), percent=True),
                "intensity": _num(row.get("intensity")),
                "polarity": _label(row.get("polarity")),
                "triggered": _label(row.get("triggered_emotions"))
                if "triggered_emotions" in data.columns
                else "",
                "suggestions": [],
            }
        )
    return entries


def entries_from_results(results) -> list:
    """Turn fresh analysis results (with their text) into PDF entries."""
    entries = []
    for item in results:
        summary = extract_summary(item["result"])
        recs = pick(item["result"], "recommendations", "items", default=[])
        if isinstance(recs, dict):
            recs = recs.get("items", [])
        titles = []
        if isinstance(recs, list):
            for rec in recs[:5]:
                title = pick(as_dict(rec), "title", "name")
                if title:
                    titles.append(str(title))
        entries.append(
            {
                "when": item["label"],
                "text": item["text"],
                "emotion": _label(summary["dominant"]),
                "confidence": _num(summary["confidence"], percent=True),
                "intensity": _num(summary["intensity"]),
                "polarity": _label(summary["polarity"]),
                "triggered": "",
                "suggestions": titles,
            }
        )
    return entries


def build_pdf_report(username, entries, scope="Mood history") -> bytes:
    """Build the MOOD MENTOR REPORT PDF and return its bytes."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
        )
    except ImportError as exc:
        raise RuntimeError(
            "PDF export needs the 'reportlab' package. Add 'reportlab' to requirements.txt and redeploy."
        ) from exc

    green = colors.HexColor(GREEN)
    green_dark = colors.HexColor(GREEN_DARK)
    ink = colors.HexColor(INK)
    line = colors.HexColor("#E2DCCF")
    soft = colors.HexColor("#E7EEE7")

    base = getSampleStyleSheet()["Normal"]
    body = ParagraphStyle("mm_body", parent=base, fontName="Helvetica", fontSize=10, leading=14, textColor=ink)
    h2 = ParagraphStyle(
        "mm_h2", parent=body, fontName="Helvetica-Bold", fontSize=14, leading=18,
        textColor=green_dark, spaceBefore=12, spaceAfter=6,
    )
    entry_title = ParagraphStyle(
        "mm_entry", parent=body, fontName="Helvetica-Bold", fontSize=11,
        textColor=green_dark, spaceBefore=8, spaceAfter=2,
    )
    entry_text = ParagraphStyle("mm_text", parent=body, leftIndent=8, spaceBefore=2)
    note = ParagraphStyle("mm_note", parent=body, fontSize=9, textColor=colors.HexColor("#6F7167"))

    def make_table(rows, widths, header=False):
        table = Table(rows, colWidths=widths, hAlign="LEFT")
        style = [
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 9.5),
            ("TEXTCOLOR", (0, 0), (-1, -1), ink),
            ("GRID", (0, 0), (-1, -1), 0.5, line),
            ("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [colors.white, soft]),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ]
        if header:
            style += [
                ("BACKGROUND", (0, 0), (-1, 0), green),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ]
        table.setStyle(TableStyle(style))
        return table

    generated = datetime.now().strftime("%Y-%m-%d %H:%M")

    def decorate(canvas, document):
        width, height = A4
        canvas.saveState()
        canvas.setFillColor(green_dark)
        canvas.rect(0, height - 26 * mm, width, 26 * mm, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 20)
        canvas.drawString(18 * mm, height - 16 * mm, "MOOD MENTOR REPORT")
        canvas.setFillColor(colors.HexColor("#DCE8DD"))
        canvas.setFont("Helvetica", 9)
        canvas.drawString(18 * mm, height - 22 * mm, pdf_text(f"{scope} | {username}"))
        canvas.setFillColor(colors.HexColor("#6F7167"))
        canvas.setFont("Helvetica", 8)
        canvas.drawString(
            18 * mm, 10 * mm,
            "MoodMentor offers general wellness information, not medical diagnosis or treatment.",
        )
        canvas.drawRightString(width - 18 * mm, 10 * mm, f"Page {document.page}")
        canvas.restoreState()

    total = len(entries)
    shown = entries[:MAX_PDF_ENTRIES]
    story = [
        Paragraph("Report details", h2),
        make_table(
            [
                ["User", pdf_text(username)],
                ["Scope", pdf_text(scope)],
                ["Generated", generated],
                ["Entries", str(total)],
            ],
            [35 * mm, 139 * mm],
        ),
    ]

    if not shown:
        story += [Spacer(1, 10), Paragraph("No entries to include in this report yet.", body)]
    else:
        counts = Counter(entry["emotion"] for entry in entries)
        rows = [["Emotion", "Entries", "Share"]] + [
            [pdf_text(emotion), str(count), f"{count / total:.0%}"]
            for emotion, count in counts.most_common()
        ]
        story += [
            Paragraph("Emotion summary", h2),
            make_table(rows, [90 * mm, 40 * mm, 44 * mm], header=True),
            Paragraph("Entries", h2),
        ]
        for number, entry in enumerate(shown, 1):
            block = [
                Paragraph(f"{number}. {pdf_para(entry['when'])}", entry_title),
                Paragraph(
                    f"<b>Emotion:</b> {pdf_para(entry['emotion'])} | "
                    f"<b>Confidence:</b> {entry['confidence']} | "
                    f"<b>Intensity:</b> {entry['intensity']} | "
                    f"<b>Polarity:</b> {pdf_para(entry['polarity'])}",
                    body,
                ),
            ]
            if entry["triggered"] not in ("", "-"):
                block.append(
                    Paragraph(f"<b>Triggered emotions:</b> {pdf_para(entry['triggered'])}", body)
                )
            if entry["text"].strip():
                block.append(
                    Paragraph("<b>Entry:</b><br/>" + pdf_para(entry["text"].strip()), entry_text)
                )
            if entry["suggestions"]:
                block.append(
                    Paragraph(
                        "<b>Suggested for you:</b> " + pdf_para("; ".join(entry["suggestions"])),
                        body,
                    )
                )
            block.append(HRFlowable(width="100%", thickness=0.5, color=line, spaceBefore=6))
            story.append(KeepTogether(block))
        if total > MAX_PDF_ENTRIES:
            story.append(
                Paragraph(f"Only the {MAX_PDF_ENTRIES} most recent of {total} entries are shown.", note)
            )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=34 * mm,
        bottomMargin=18 * mm,
        title="MOOD MENTOR REPORT",
        author=APP_NAME,
    )
    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
    return buffer.getvalue()


# ---------- Login ----------
def require_login():
    if st.session_state.get("signed_in"):
        return

    locked = st.session_state.get("login_attempts", 0) >= MAX_LOGIN_ATTEMPTS

    # TASK 1: centre everything. vertical_alignment lines the two boxes up in the middle.
    st.markdown(LOGIN_CSS, unsafe_allow_html=True)
    try:
        left, right = st.columns([1.2, 1], gap="large", vertical_alignment="center")
    except TypeError:  # very old Streamlit
        left, right = st.columns([1.2, 1], gap="large")

    with left:
        with st.container(key="login_left"):
            st.markdown(f'<div class="brand">{LOGO}<b>{APP_NAME}</b></div>', unsafe_allow_html=True)
            st.markdown("# Understand your mood.\n# Build better patterns.")
            st.write(
                "Write a short journal entry, or upload a text or CSV file, and get an emotion "
                "analysis, trend tracking and wellness suggestions that fit how you feel."
            )
            st.markdown(
                chips_html(
                    (
                        "Emotion analysis",
                        "Type, .txt or .csv input",
                        "Daily, weekly and monthly trends",
                        "Personal recommendations",
                        "CSV, JSON and ZIP exports",
                    )
                ),
                unsafe_allow_html=True,
            )
            st.caption(
                "Your text is sent to the configured MoodMentor API for analysis. "
                "Avoid entering sensitive identifying details."
            )

    with right:
        with st.container(key="login_right"):
            _, theme_col = st.columns([2, 1])
            with theme_col:
                theme_button("theme_toggle_login")  # TASK 4 on the login page too
            with st.container(border=True):
                tab_signin, tab_create = st.tabs(["Sign in", "Create account"])
                with tab_signin:
                    with st.form("login_form"):
                        user = st.text_input("Username")
                        password = st.text_input("Password", type="password")
                        ok = st.form_submit_button(
                            "Sign in", type="primary", use_container_width=True
                        )
                    if ok:
                        if locked:
                            st.error("Too many failed attempts. Reload the page to try again.")
                        elif verify_account(user, password):
                            st.session_state.update(
                                signed_in=True,
                                username=user.strip().lower(),
                                login_attempts=0,
                            )
                            st.rerun()
                        else:
                            st.session_state.login_attempts = (
                                st.session_state.get("login_attempts", 0) + 1
                            )
                            st.error("Incorrect username or password.")

                with tab_create:
                    with st.form("register_form"):
                        new_user = st.text_input("Choose a username")
                        new_password = st.text_input("Password (10+ characters)", type="password")
                        confirm_password = st.text_input("Confirm password", type="password")
                        ok_create = st.form_submit_button(
                            "Create account", type="primary", use_container_width=True
                        )
                    if ok_create:
                        if new_password != confirm_password:
                            st.error("Passwords do not match.")
                        else:
                            try:
                                create_account(new_user, new_password)
                                st.success("Account created. Switch to Sign in to continue.")
                            except Exception as exc:
                                st.error(str(exc))
    st.stop()


# ---------- Top navigation ----------
def topbar():
    brand, nav, theme_col, out = st.columns([1.5, 4.3, 1.4, 1.1])
    brand.markdown(f'<div class="brand">{LOGO}<b>{APP_NAME}</b></div>', unsafe_allow_html=True)
    nav.radio("Navigate", PAGES, key="page", horizontal=True, label_visibility="collapsed")
    with theme_col:
        theme_button("theme_toggle_top")  # TASK 4
    if out.button("Sign out", use_container_width=True):
        keep = {k: st.session_state[k] for k in ("theme", "loader_done") if k in st.session_state}
        st.session_state.clear()
        st.session_state.update(keep)
        st.rerun()
    st.divider()


# ---------- Sidebar ----------
def sidebar():
    with st.sidebar:
        st.markdown("### Settings")
        st.markdown(f"Signed in as **{st.session_state.username}**")
        # Locked to the logged-in user so nobody can read/delete another user's API data.
        st.text_input(
            "API user ID",
            value=st.session_state.username,
            disabled=True,
            help="Your history and feedback on the API are scoped to this ID.",
        )
        user_id = st.session_state.username

        with st.expander("Analysis preferences"):
            model = st.selectbox("Emotion model", ["BERT", "DistilBERT"])
            top_k = RECOMMENDATION_COUNT  # TASK 5: fixed at 5
            st.caption(f"Recommendations shown: {RECOMMENDATION_COUNT}")
            content_types = st.multiselect(
                "Content types",
                ["breathing", "meditation", "journaling", "movement", "mindfulness", "music", "article"],
            )
            tags = st.multiselect(
                "Tags",
                ["calm", "focus", "sleep", "stress", "confidence", "gratitude", "energy"],
            )
            blocked = st.text_input("Blocked content IDs (comma-separated)")
            persist = st.checkbox("Save analysis to history", True)
        st.divider()
        st.caption(f"API: {api_base()}")
        st.markdown(f"[API docs]({api_base()}/docs)")

    return user_id, {
        "model_type": model,
        "top_k": top_k,
        "preferred_types": content_types,
        "preferred_tags": tags,
        "blocked_content_ids": [item.strip() for item in blocked.split(",") if item.strip()],
        "persist_history": persist,
    }


# ---------- Recommendations ----------
def send_feedback(user_id, content_id, event, rating=None):
    payload = {"user_id": user_id, "content_id": content_id, "event": event}
    if rating is not None:
        payload["rating"] = float(rating)
    if safe(api_request, "POST", "/feedback", payload=payload) is not None:
        st.toast("Feedback saved")
        return True
    return False


def more_popover(container, key):
    """Popover with a key (needed for the CSS hook); falls back on older Streamlit."""
    try:
        return container.popover("More", use_container_width=True, key=key)
    except TypeError:
        return container.popover("More", use_container_width=True)


def render_recommendations(result, user_id):
    recommendations = pick(result, "recommendations", "items", default=[])
    if isinstance(recommendations, dict):
        recommendations = recommendations.get("items", [])
    if not isinstance(recommendations, list) or not recommendations:
        st.info("No recommendations came back for this entry. Please try again.")
        return

    recommendations = recommendations[:RECOMMENDATION_COUNT]  # TASK 5: show 5

    st.subheader("Recommended for you")
    for index, recommendation in enumerate(recommendations):
        recommendation = as_dict(recommendation)
        content_id = str(pick(recommendation, "content_id", "id", default=f"item-{index + 1}"))
        key_id = f"{index}_{safe_key(content_id)}"
        title = pick(recommendation, "title", "name", default=f"Recommendation {index + 1}")
        score = pick(recommendation, "score", "final_score", "rank_score")

        with st.container(border=True):
            col_main, col_score = st.columns([5, 1])
            with col_main:
                st.markdown(f"#### {title}")
                description = pick(recommendation, "description", "summary", "content")
                if description:
                    st.write(str(description))
                tags = pick(recommendation, "tags", "content_type")
                if tags:
                    tag_items = tags if isinstance(tags, list) else [tags]
                    st.markdown(chips_html(tag_items), unsafe_allow_html=True)
                why = pick(recommendation, "reasons", "explanation")
                if why:
                    st.caption(f"Why this may help: {why}")
                url = pick(recommendation, "url", "link")
                if url and str(url).startswith(("https://", "http://")):
                    st.markdown(f"[Open resource]({url})")

            with col_score:
                if score is not None:
                    try:
                        st.metric("Match", f"{float(score):.2f}")
                    except (TypeError, ValueError):
                        st.metric("Match", str(score))

            button_helpful, button_done, button_more = st.columns([1, 1, 1])
            if button_helpful.button(
                "Helpful", key=f"fb_{key_id}_helpful", use_container_width=True
            ) and send_feedback(user_id, content_id, "helpful"):
                st.rerun()
            if button_done.button(
                "Done", key=f"fb_{key_id}_complete", use_container_width=True
            ) and send_feedback(user_id, content_id, "complete"):
                st.rerun()

            with more_popover(button_more, f"more_{key_id}"):
                for event in ("accept", "reject", "skip", "hide"):
                    if st.button(
                        EVENTS[event],
                        key=f"fb_{key_id}_{event}",
                        use_container_width=True,
                    ) and send_feedback(user_id, content_id, event):
                        st.rerun()
                rating = st.slider("Rating", 1, 5, 4, key=f"rate_{key_id}")
                if st.button("Submit rating", key=f"rate_submit_{key_id}"):
                    send_feedback(user_id, content_id, "rate", rating)


# ---------- Pages ----------
def page_overview(user_id):
    hero(
        f"Welcome back, {st.session_state.username}",
        "A clear view of your emotional patterns, recent entries and next steps.",
    )
    health = safe(api_request, "GET", "/health", quiet=True, timeout=HEALTH_TIMEOUT)

    emotions_df = recommendations_df = feedback_df = pd.DataFrame()
    if health is not None:
        emotions_df = frame(
            safe(api_request, "GET", "/history/emotions", params={"user_id": user_id}, quiet=True)
        )
        recommendations_df = frame(
            safe(api_request, "GET", "/history/recommendations", params={"user_id": user_id}, quiet=True)
        )
        feedback_df = frame(
            safe(api_request, "GET", "/history/feedback", params={"user_id": user_id}, quiet=True)
        )

    metric_a, metric_b, metric_c, metric_d = st.columns(4)
    metric_a.metric("Entries analyzed", len(emotions_df))
    metric_b.metric("Recommendations", len(recommendations_df))
    metric_c.metric("Feedback given", len(feedback_df))
    metric_d.metric("API", str(pick(as_dict(health), "status", default="Offline")).title())

    if health is None:
        st.warning("The API did not respond. On free hosting it can take about a minute to wake up.")
        if st.button("Retry connection"):
            st.rerun()

    left, right = st.columns([1.1, 1], gap="large")
    with left:
        st.subheader("Emotion mix")
        if not emotions_df.empty and "dominant_emotion" in emotions_df.columns:
            counts = (
                emotions_df["dominant_emotion"]
                .astype(str)
                .str.replace("_", " ", regex=False)
                .str.title()
                .value_counts()
                .reset_index()
            )
            counts.columns = ["Emotion", "Entries"]
            fig = px.pie(counts, names="Emotion", values="Entries", hole=0.62)
            fig.update_traces(
                textposition="outside",
                textinfo="label+percent",
                textfont=dict(color=chart_ink()),
            )
            fig.update_layout(showlegend=False)
            st.plotly_chart(style_fig(fig, 330), use_container_width=True)
        else:
            st.info("No entries yet. Your emotion mix will appear after your first check-in.")

    with right:
        st.subheader("Next step")
        with st.container(border=True):
            st.write("Take a minute to write how today feels.")
            with st.container(key="start_checkin_container"):
                st.button(
                    "🌿  Start a check-in",
                    type="primary",
                    on_click=go,
                    args=("Analyze mood",),
                    use_container_width=True,
                    key="start_checkin_button",
                )
                st.button(
                    "📈  View trends",
                    type="primary",
                    on_click=go,
                    args=("Trends",),
                    use_container_width=True,
                    key="view_trends_button",
                )

        st.subheader("Recent entries")
        if not emotions_df.empty:
            date_column = date_col(emotions_df)
            recent = (
                emotions_df.sort_values(date_column, ascending=False)
                if date_column
                else emotions_df
            )
            st.dataframe(recent.head(5), use_container_width=True, hide_index=True)
        else:
            st.caption("Nothing recorded yet.")


# ----- Analyze page helpers -----
def apply_example():
    choice = st.session_state.get("example_choice", "Write my own")
    st.session_state.journal_text = EXAMPLES.get(choice, "")


def collect_entries(method: str) -> Loaded:
    """Render the widgets for the chosen input method and return validated entries."""
    if method == INPUT_METHODS[0]:
        st.selectbox(
            "Start from an example",
            ["Write my own"] + list(EXAMPLES),
            key="example_choice",
            on_change=apply_example,
        )
        text = st.text_area(
            "Journal entry",
            key="journal_text",
            height=190,
            max_chars=MAX_CHARS,
            placeholder="Today I feel...",
        )
        st.caption(f"{len(text.strip()):,} / {MAX_CHARS:,} characters")
        return load_typed(text)

    if method == INPUT_METHODS[1]:
        upload = st.file_uploader(
            "Upload a .txt file",
            type=["txt"],
            key="txt_upload",
            help=f"Plain text, up to {MAX_UPLOAD_BYTES / 1_000_000:.0f} MB.",
        )
        mode = st.radio(
            "Treat the file as",
            ["One entry", "One entry per line"],
            horizontal=True,
            key="txt_mode",
        )
        if upload is None:
            return Loaded()
        try:
            return load_txt(upload, per_line=(mode == "One entry per line"))
        except InputError as exc:
            return Loaded(problems=[str(exc)], has_input=True)

    upload = st.file_uploader(
        "Upload a .csv file",
        type=["csv"],
        key="csv_upload",
        help=f"CSV with a header row, up to {MAX_UPLOAD_BYTES / 1_000_000:.0f} MB. "
        "Each row is one entry.",
    )
    if upload is None:
        return Loaded()
    try:
        df = parse_csv(upload)
    except InputError as exc:
        return Loaded(problems=[str(exc)], has_input=True)

    columns = list(df.columns)
    guess = guess_text_column(df)
    file_id = getattr(upload, "file_id", None) or upload.name
    column = st.selectbox(
        "Column that contains the text",
        columns,
        index=columns.index(guess),
        key=f"csv_column_{safe_key(file_id)}",
        help="The first row of the file is used as the header.",
    )
    try:
        return load_csv(df, column)
    except InputError as exc:
        return Loaded(problems=[str(exc)], has_input=True)


def show_load_report(loaded: Loaded):
    for note in loaded.notes:
        st.caption(note)
    if loaded.entries:
        count = len(loaded.entries)
        st.success(f"{count} valid entr{'y' if count == 1 else 'ies'} ready to analyze.")
    for problem in loaded.problems[:8]:
        st.warning(problem)
    if len(loaded.problems) > 8:
        st.caption(f"…and {len(loaded.problems) - 8} more rejected entries.")


def choose_targets(entries):
    if len(entries) == 1:
        return entries
    with st.expander(f"Preview {len(entries)} valid entries"):
        st.dataframe(
            pd.DataFrame(
                {
                    "Entry": [item["label"] for item in entries],
                    "Preview": [preview(item["text"], 90) for item in entries],
                    "Characters": [len(item["text"]) for item in entries],
                }
            ),
            use_container_width=True,
            hide_index=True,
        )
    scope = st.radio(
        "What should be analyzed?",
        ["One entry", f"All entries (first {MAX_BATCH})"],
        horizontal=True,
        key="scope",
    )
    if scope.startswith("One"):
        index = st.selectbox(
            "Entry to analyze",
            list(range(len(entries))),
            format_func=lambda n: f"{entries[n]['label']}: {preview(entries[n]['text'])}",
            key="entry_pick",
        )
        return [entries[index]]
    if len(entries) > MAX_BATCH:
        st.caption(f"Only the first {MAX_BATCH} entries will be analyzed.")
    return entries[:MAX_BATCH]


def run_analysis(targets, user_id, preferences):
    results = []
    progress = st.progress(0.0, text="Analyzing. The first request can take longer while the API warms up...")
    failure = None
    for position, entry in enumerate(targets, 1):
        try:
            result = api_request(
                "POST",
                "/analyze",
                payload={"text": entry["text"], "user_id": user_id, **preferences},
            )
            results.append({"label": entry["label"], "text": entry["text"], "result": result})
        except Exception as exc:
            failure = f"{entry['label']}: {exc}"
            break
        progress.progress(position / len(targets), text=f"Analyzed {position} of {len(targets)}")
    progress.empty()
    if failure:
        st.error(
            f"Stopped after {len(results)} of {len(targets)} entries. {failure}"
            if results
            else failure
        )
    return results


def extract_summary(result):
    emotional_state = as_dict(pick(result, "emotional_state", "state", default={}))
    emotion_data = as_dict(pick(result, "emotion", "prediction", default={}))
    sentiment_data = as_dict(pick(result, "sentiment", default={}))
    return {
        "confidence": pick(
            emotional_state, "emotion_confidence",
            default=pick(emotion_data, "primary_confidence"),
        ),
        "dominant": pick(
            emotional_state, "dominant_emotion",
            default=pick(emotion_data, "primary_emotion", default="Unknown"),
        ),
        "polarity": pick(
            emotional_state, "polarity",
            default=pick(sentiment_data, "label", default="-"),
        ),
        "intensity": pick(emotional_state, "intensity"),
        "severity": pick(emotional_state, "severity", default="-"),
        "scores": pick(
            emotional_state, "emotion_probabilities", "all_scores",
            default=pick(emotion_data, "scores", default={}),
        ),
    }


def render_result(result, user_id):
    summary = extract_summary(result)
    confidence, intensity = summary["confidence"], summary["intensity"]

    col_one, col_two = st.columns([1.2, 1], gap="large")
    with col_one:
        st.markdown("Dominant emotion")
        dominant_text = esc(str(summary["dominant"]).replace("_", " ").title())
        st.markdown(f'<div class="big-emotion">{dominant_text}</div>', unsafe_allow_html=True)
        st.markdown(
            chips_html(
                [f"Polarity: {summary['polarity']}", f"Severity: {summary['severity']}"]
            ),
            unsafe_allow_html=True,
        )
        metric_one, metric_two = st.columns(2)
        metric_one.metric(
            "Confidence",
            f"{float(confidence):.0%}" if isinstance(confidence, (int, float)) else "-",
        )
        metric_two.metric(
            "Intensity",
            f"{float(intensity):.2f}" if isinstance(intensity, (int, float)) else "-",
        )

    with col_two:
        scores = summary["scores"]
        if isinstance(scores, dict) and scores:
            score_df = pd.DataFrame(
                [
                    {"Emotion": str(label).replace("_", " ").title(), "Score": value}
                    for label, value in scores.items()
                ]
            )
            score_df["Score"] = pd.to_numeric(score_df["Score"], errors="coerce")
            score_df = score_df.dropna().sort_values("Score")
            if not score_df.empty:
                fig = px.bar(
                    score_df,
                    x="Score",
                    y="Emotion",
                    orientation="h",
                    title="Emotion profile",
                    color_discrete_sequence=[GREEN],
                )
                st.plotly_chart(style_fig(fig, 300), use_container_width=True)

    render_recommendations(result, user_id)


def show_results(user_id):
    results = st.session_state.get("analysis_results")
    if not results:
        return

    st.divider()
    index = 0
    if len(results) > 1:
        st.subheader("Batch summary")
        rows = []
        for item in results:
            summary = extract_summary(item["result"])
            confidence = summary["confidence"]
            rows.append(
                {
                    "Entry": item["label"],
                    "Preview": preview(item["text"], 70),
                    "Emotion": str(summary["dominant"]).replace("_", " ").title(),
                    "Confidence": f"{float(confidence):.0%}"
                    if isinstance(confidence, (int, float))
                    else "-",
                    "Polarity": summary["polarity"],
                }
            )
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        index = st.selectbox(
            "Show details for",
            list(range(len(results))),
            format_func=lambda n: f"{results[n]['label']}: {preview(results[n]['text'])}",
            key="result_view",
        )

    render_result(results[index]["result"], user_id)

    download_payload = (
        results[0]["result"]
        if len(results) == 1
        else [
            {"entry": item["label"], "text": item["text"], "result": item["result"]}
            for item in results
        ]
    )
    col_json, col_pdf = st.columns(2)
    col_json.download_button(
        "Download analysis (JSON)",
        json.dumps(download_payload, indent=2, ensure_ascii=False, default=str),
        "moodmentor_analysis.json",
        "application/json",
        use_container_width=True,
    )
    try:
        pdf_bytes = build_pdf_report(
            st.session_state.get("username", user_id),
            entries_from_results(results),
            "Current analysis",
        )
        col_pdf.download_button(
            "Download analysis (PDF)",
            pdf_bytes,
            "moodmentor_analysis.pdf",
            "application/pdf",
            use_container_width=True,
        )
    except Exception as exc:
        col_pdf.caption(f"PDF unavailable: {exc}")


def page_analyze(user_id, preferences):
    hero(
        "Check in with yourself",
        "Write freely, or upload a .txt or .csv file. MoodMentor reads the emotional tone "
        "and suggests resources that fit.",
    )

    method = st.radio(
        "How would you like to add your entry?",
        INPUT_METHODS,
        horizontal=True,
        key="input_method",
    )
    is_upload = method != INPUT_METHODS[0]
    loaded = collect_entries(method)

    if is_upload and loaded.has_input:
        show_load_report(loaded)

    targets = choose_targets(loaded.entries) if loaded.entries else []

    consent = st.checkbox(
        "I understand this text is sent to the MoodMentor API for processing.",
        key="consent",
    )
    clicked = st.button(
        "Analyze my mood", type="primary", use_container_width=True, key="analyze_btn"
    )

    if clicked:
        if not consent:
            st.warning("Confirm the checkbox before sending your text.")
        elif not targets:
            if is_upload and not loaded.has_input:
                st.warning("Upload a file first.")
            elif is_upload:
                st.error("None of the entries in this file are valid, so nothing was sent.")
            else:
                for problem in loaded.problems:
                    st.warning(problem)
        else:
            results = run_analysis(targets, user_id, preferences)
            if results:
                st.session_state.analysis_results = results
                st.session_state.pop("result_view", None)
                st.toast("Analysis complete")

    show_results(user_id)


def page_trends(user_id):
    hero(
        "Notice the patterns",
        "See how your emotional intensity and polarity change over time.",
    )
    granularity = st.radio(
        "Group by", ["daily", "weekly", "monthly"], index=1, horizontal=True
    )
    payload = safe(
        api_request,
        "GET",
        "/trends",
        params={"user_id": user_id, "granularity": granularity},
    )
    payload = as_dict(payload)
    if not payload:
        return

    trend_df = frame({"trend": payload.get("trend", [])})
    frequency_df = frame({"emotion_frequency": payload.get("emotion_frequency", [])})
    if trend_df.empty and frequency_df.empty:
        st.info("No trend data yet. Analyze an entry with history saving turned on.")
        return

    if not trend_df.empty:
        st.subheader(f"{granularity.title()} trend")
        x_column = next(
            (
                column
                for column in ("period", "date", "week", "month", "timestamp")
                if column in trend_df.columns
            ),
            trend_df.columns[0],
        )
        for column in trend_df.columns:
            if column != x_column and trend_df[column].dtype == object:
                converted = pd.to_numeric(trend_df[column], errors="coerce")
                trend_df[column] = converted.fillna(trend_df[column])

        numeric_columns = [
            column
            for column in trend_df.columns
            if column != x_column
            and pd.api.types.is_numeric_dtype(trend_df[column])
        ]
        if numeric_columns:
            fig = px.line(trend_df, x=x_column, y=numeric_columns, markers=True)
            st.plotly_chart(style_fig(fig, 380), use_container_width=True)
        st.dataframe(trend_df, use_container_width=True, hide_index=True)

    if not frequency_df.empty:
        st.subheader("Emotion frequency")
        label_column = next(
            (
                column
                for column in ("emotion", "dominant_emotion", "name")
                if column in frequency_df.columns
            ),
            frequency_df.columns[0],
        )
        value_column = next(
            (
                column
                for column in ("count", "frequency", "total", "samples")
                if column in frequency_df.columns
            ),
            None,
        )
        if value_column:
            fig = px.bar(
                frequency_df,
                x=label_column,
                y=value_column,
                color_discrete_sequence=[GREEN],
            )
            st.plotly_chart(style_fig(fig), use_container_width=True)
        st.dataframe(frequency_df, use_container_width=True, hide_index=True)

    if not trend_df.empty:
        st.download_button(
            "Export trends (CSV)",
            trend_df.to_csv(index=False).encode(),
            "moodmentor_trends.csv",
            "text/csv",
        )


def clear_history_dates():
    st.session_state["hist_from"] = None
    st.session_state["hist_to"] = None


def page_history(user_id):
    hero(
        "Your history",
        "Search and filter past emotion records, recommendations and feedback.",
    )
    query = st.text_input("Search", placeholder="Emotion, title, event, date...")
    # TASK 7: date pickers (st.date_input opens a calendar; always white with black text)
    col_start, col_end = st.columns(2)
    start_date = col_start.date_input(
        "Start Date From", value=None, format="DD/MM/YYYY", key="hist_from", help="Click to open the calendar"
    )
    end_date = col_end.date_input(
        "To End date ", value=None, format="DD/MM/YYYY", key="hist_to", help="Click to open the calendar"
    )
    if start_date and end_date and start_date > end_date:
        st.warning("“From” is after “To”, so the two dates were swapped.")
        start_date, end_date = end_date, start_date
    if start_date or end_date:
        st.caption(
            f"Showing records from {start_date.strftime('%d %b %Y') if start_date else 'the beginning'} "
            f"to {end_date.strftime('%d %b %Y') if end_date else 'today'}."
        )
        st.button("Clear dates", key="hist_clear", on_click=clear_history_dates)

    endpoints = {
        "Emotions": "/history/emotions",
        "Recommendations": "/history/recommendations",
        "Feedback": "/history/feedback",
    }
    tabs = st.tabs(list(endpoints))
    for tab, (label, path) in zip(tabs, endpoints.items()):
        with tab:
            data_df = frame(
                safe(api_request, "GET", path, params={"user_id": user_id})
            )
            if data_df.empty:
                st.info(f"No {label.lower()} recorded yet.")
                continue

            if query:
                mask = data_df.astype(str).apply(
                    lambda column: column.str.contains(query, case=False, na=False, regex=False)
                ).any(axis=1)
                data_df = data_df[mask]

            date_column = date_col(data_df)
            if date_column and (start_date or end_date):
                dates = pd.to_datetime(data_df[date_column], errors="coerce").dt.date
                keep = pd.Series(True, index=data_df.index)
                if start_date:
                    keep &= dates >= start_date
                if end_date:
                    keep &= dates <= end_date
                data_df = data_df[keep.fillna(False)]

            for column_name, filter_key in (
                ("dominant_emotion", "filter_emotion"),
                ("event", "filter_event"),
            ):
                applies_to_tab = (
                    (label == "Emotions") == (column_name == "dominant_emotion")
                )
                if column_name in data_df.columns and applies_to_tab:
                    options = sorted(data_df[column_name].dropna().astype(str).unique())
                    selected = st.multiselect(
                        f"Filter {column_name.replace('_', ' ')}",
                        options,
                        key=f"{filter_key}_{label}",
                    )
                    if selected:
                        data_df = data_df[data_df[column_name].astype(str).isin(selected)]

            st.caption(f"{len(data_df)} record(s)")
            st.dataframe(data_df, use_container_width=True, hide_index=True)
            if label != "Emotions":  # Emotions tab has no download buttons
                st.download_button(
                    f"Download {label.lower()} (CSV)",
                    data_df.to_csv(index=False).encode(),
                    f"moodmentor_{label.lower()}.csv",
                    "text/csv",
                    key=f"dl_{label}",
                )


def page_reports(user_id):
    hero(
        "Reports and privacy",
        "Export your data or permanently delete what the API has stored.",
    )
    st.subheader("Export")
    col_csv, col_json, col_pdf, col_stats = st.columns(4)

    if col_csv.button("Prepare CSV bundle (ZIP)", use_container_width=True):
        data = safe(
            api_request,
            "GET",
            "/reports",
            params={"user_id": user_id, "format": "csv"},
            raw=True,
        )
        if data is not None:
            st.session_state.report_zip = data

    if col_json.button("Prepare JSON report", use_container_width=True):
        data = safe(
            api_request,
            "GET",
            "/reports",
            params={"user_id": user_id, "format": "json"},
        )
        if data is not None:
            st.session_state.report_json = data

    if col_pdf.button("Prepare PDF report", use_container_width=True):
        history = safe(api_request, "GET", "/history/emotions", params={"user_id": user_id})
        if history is not None:
            try:
                st.session_state.report_pdf = build_pdf_report(
                    user_id, entries_from_history(frame(history)), "Full emotion history"
                )
            except Exception as exc:
                st.error(str(exc))

    if col_stats.button("Refresh API stats", use_container_width=True):
        st.session_state.report_stats = safe(api_request, "GET", "/stats")

    if st.session_state.get("report_zip"):
        st.download_button(
            "Download report ZIP",
            st.session_state.report_zip,
            "moodmentor_report.zip",
            "application/zip",
        )
    if st.session_state.get("report_json"):
        st.download_button(
            "Download report JSON",
            json.dumps(
                st.session_state.report_json,
                indent=2,
                ensure_ascii=False,
                default=str,
            ),
            "moodmentor_report.json",
            "application/json",
        )
    if st.session_state.get("report_pdf"):
        st.download_button(
            "Download report PDF",
            st.session_state.report_pdf,
            "moodmentor_report.pdf",
            "application/pdf",
        )
    if st.session_state.get("report_stats"):
        st.json(st.session_state.report_stats)

    st.divider()
    st.subheader("Delete my data")
    st.warning(
        "Deletion is permanent. It removes stored data for the API user ID in the sidebar, "
        "not your local dashboard account."
    )
    confirmed = st.checkbox("I understand this permanently deletes my stored API data.")
    typed_user_id = st.text_input(f"Type your API user ID to confirm: {user_id}")
    if st.button(
        "Delete my API data",
        disabled=not (confirmed and typed_user_id == user_id),
    ):
        result = safe(api_request, "DELETE", f"/users/{user_id}/data")
        if result is not None:
            st.success("Deletion completed.")
            st.json(result)
            for key in ("analysis_results", "report_zip", "report_json", "report_pdf", "report_stats"):
                st.session_state.pop(key, None)


def main():
    inject_theme()   # TASK 4: dark overrides (if selected)
    show_loader()    # TASK 3: loader on first page load
    require_login()
    st.session_state.setdefault("page", "Overview")
    topbar()
    user_id, preferences = sidebar()
    current_page = st.session_state.page

    if current_page == "Overview":
        page_overview(user_id)
    elif current_page == "Analyze mood":
        page_analyze(user_id, preferences)
    elif current_page == "Trends":
        page_trends(user_id)
    elif current_page == "History":
        page_history(user_id)
    else:
        page_reports(user_id)

    st.divider()
    st.caption(
        "MoodMentor offers general wellness information, not medical diagnosis or treatment. "
        "If you are in crisis, contact a local helpline or emergency services."
    )


if __name__ == "__main__":
    main()