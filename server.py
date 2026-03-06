"""
Nepal Election 2082 — Live Scraper & API Server
================================================
Scrapes result.election.gov.np and ekantipur in the background,
caches the data, and serves it via a local REST API that the
dashboard HTML connects to.

Install:
    pip install flask flask-cors requests beautifulsoup4 playwright
    playwright install chromium

Run:
    python server.py

Then open dashboard.html in your browser.
The dashboard auto-connects to http://localhost:5000
"""

import os
import json
import time
import threading
import logging
from datetime import datetime
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────
REFRESH_INTERVAL = 300          # seconds between scrapes
EC_BASE          = "https://result.election.gov.np"
EKANTIPUR_BASE   = "https://election.ekantipur.com"
CHUNAB_BASE      = "https://www.chunab.org"
NEPSEBAJAR_BASE  = "https://election.nepsebajar.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

# ─────────────────────────────────────────────────────────────
# AUTHORITATIVE 165-CONSTITUENCY MASTER LIST
# Province seat counts: Koshi=28, Madhesh=32, Bagmati=33,
#   Gandaki=18, Lumbini=26, Karnali=12, Sudurpashchim=16
# ─────────────────────────────────────────────────────────────
MASTER = [
  # ── KOSHI (28) ──────────────────────────────────────────────
  {"id":"1",  "name":"Morang - 1",        "district":"Morang",          "province":"1","province_name":"Koshi"},
  {"id":"2",  "name":"Morang - 2",        "district":"Morang",          "province":"1","province_name":"Koshi"},
  {"id":"3",  "name":"Morang - 3",        "district":"Morang",          "province":"1","province_name":"Koshi"},
  {"id":"4",  "name":"Morang - 4",        "district":"Morang",          "province":"1","province_name":"Koshi"},
  {"id":"5",  "name":"Morang - 5",        "district":"Morang",          "province":"1","province_name":"Koshi"},
  {"id":"6",  "name":"Morang - 6",        "district":"Morang",          "province":"1","province_name":"Koshi"},
  {"id":"7",  "name":"Jhapa - 1",         "district":"Jhapa",           "province":"1","province_name":"Koshi"},
  {"id":"8",  "name":"Jhapa - 2",         "district":"Jhapa",           "province":"1","province_name":"Koshi"},
  {"id":"9",  "name":"Jhapa - 3",         "district":"Jhapa",           "province":"1","province_name":"Koshi"},
  {"id":"10", "name":"Jhapa - 4",         "district":"Jhapa",           "province":"1","province_name":"Koshi"},
  {"id":"11", "name":"Jhapa - 5",         "district":"Jhapa",           "province":"1","province_name":"Koshi"},
  {"id":"12", "name":"Sunsari - 1",       "district":"Sunsari",         "province":"1","province_name":"Koshi"},
  {"id":"13", "name":"Sunsari - 2",       "district":"Sunsari",         "province":"1","province_name":"Koshi"},
  {"id":"14", "name":"Sunsari - 3",       "district":"Sunsari",         "province":"1","province_name":"Koshi"},
  {"id":"15", "name":"Sunsari - 4",       "district":"Sunsari",         "province":"1","province_name":"Koshi"},
  {"id":"16", "name":"Ilam - 1",          "district":"Ilam",            "province":"1","province_name":"Koshi"},
  {"id":"17", "name":"Ilam - 2",          "district":"Ilam",            "province":"1","province_name":"Koshi"},
  {"id":"18", "name":"Udayapur - 1",      "district":"Udayapur",        "province":"1","province_name":"Koshi"},
  {"id":"19", "name":"Udayapur - 2",      "district":"Udayapur",        "province":"1","province_name":"Koshi"},
  {"id":"20", "name":"Taplejung",         "district":"Taplejung",       "province":"1","province_name":"Koshi"},
  {"id":"21", "name":"Panchthar",         "district":"Panchthar",       "province":"1","province_name":"Koshi"},
  {"id":"22", "name":"Sankhuwasabha",     "district":"Sankhuwasabha",   "province":"1","province_name":"Koshi"},
  {"id":"23", "name":"Tehrathum",         "district":"Tehrathum",       "province":"1","province_name":"Koshi"},
  {"id":"24", "name":"Bhojpur",           "district":"Bhojpur",         "province":"1","province_name":"Koshi"},
  {"id":"25", "name":"Dhankuta",          "district":"Dhankuta",        "province":"1","province_name":"Koshi"},
  {"id":"26", "name":"Solukhumbu",        "district":"Solukhumbu",      "province":"1","province_name":"Koshi"},
  {"id":"27", "name":"Khotang",           "district":"Khotang",         "province":"1","province_name":"Koshi"},
  {"id":"28", "name":"Okhaldhunga",       "district":"Okhaldhunga",     "province":"1","province_name":"Koshi"},
  # ── MADHESH (32) ────────────────────────────────────────────
  {"id":"29", "name":"Saptari - 1",       "district":"Saptari",         "province":"2","province_name":"Madhesh"},
  {"id":"30", "name":"Saptari - 2",       "district":"Saptari",         "province":"2","province_name":"Madhesh"},
  {"id":"31", "name":"Saptari - 3",       "district":"Saptari",         "province":"2","province_name":"Madhesh"},
  {"id":"32", "name":"Saptari - 4",       "district":"Saptari",         "province":"2","province_name":"Madhesh"},
  {"id":"33", "name":"Siraha - 1",        "district":"Siraha",          "province":"2","province_name":"Madhesh"},
  {"id":"34", "name":"Siraha - 2",        "district":"Siraha",          "province":"2","province_name":"Madhesh"},
  {"id":"35", "name":"Siraha - 3",        "district":"Siraha",          "province":"2","province_name":"Madhesh"},
  {"id":"36", "name":"Siraha - 4",        "district":"Siraha",          "province":"2","province_name":"Madhesh"},
  {"id":"37", "name":"Dhanusha - 1",      "district":"Dhanusha",        "province":"2","province_name":"Madhesh"},
  {"id":"38", "name":"Dhanusha - 2",      "district":"Dhanusha",        "province":"2","province_name":"Madhesh"},
  {"id":"39", "name":"Dhanusha - 3",      "district":"Dhanusha",        "province":"2","province_name":"Madhesh"},
  {"id":"40", "name":"Dhanusha - 4",      "district":"Dhanusha",        "province":"2","province_name":"Madhesh"},
  {"id":"41", "name":"Mahottari - 1",     "district":"Mahottari",       "province":"2","province_name":"Madhesh"},
  {"id":"42", "name":"Mahottari - 2",     "district":"Mahottari",       "province":"2","province_name":"Madhesh"},
  {"id":"43", "name":"Mahottari - 3",     "district":"Mahottari",       "province":"2","province_name":"Madhesh"},
  {"id":"44", "name":"Mahottari - 4",     "district":"Mahottari",       "province":"2","province_name":"Madhesh"},
  {"id":"45", "name":"Sarlahi - 1",       "district":"Sarlahi",         "province":"2","province_name":"Madhesh"},
  {"id":"46", "name":"Sarlahi - 2",       "district":"Sarlahi",         "province":"2","province_name":"Madhesh"},
  {"id":"47", "name":"Sarlahi - 3",       "district":"Sarlahi",         "province":"2","province_name":"Madhesh"},
  {"id":"48", "name":"Sarlahi - 4",       "district":"Sarlahi",         "province":"2","province_name":"Madhesh"},
  {"id":"49", "name":"Rautahat - 1",      "district":"Rautahat",        "province":"2","province_name":"Madhesh"},
  {"id":"50", "name":"Rautahat - 2",      "district":"Rautahat",        "province":"2","province_name":"Madhesh"},
  {"id":"51", "name":"Rautahat - 3",      "district":"Rautahat",        "province":"2","province_name":"Madhesh"},
  {"id":"52", "name":"Rautahat - 4",      "district":"Rautahat",        "province":"2","province_name":"Madhesh"},
  {"id":"53", "name":"Bara - 1",          "district":"Bara",            "province":"2","province_name":"Madhesh"},
  {"id":"54", "name":"Bara - 2",          "district":"Bara",            "province":"2","province_name":"Madhesh"},
  {"id":"55", "name":"Bara - 3",          "district":"Bara",            "province":"2","province_name":"Madhesh"},
  {"id":"56", "name":"Bara - 4",          "district":"Bara",            "province":"2","province_name":"Madhesh"},
  {"id":"57", "name":"Parsa - 1",         "district":"Parsa",           "province":"2","province_name":"Madhesh"},
  {"id":"58", "name":"Parsa - 2",         "district":"Parsa",           "province":"2","province_name":"Madhesh"},
  {"id":"59", "name":"Parsa - 3",         "district":"Parsa",           "province":"2","province_name":"Madhesh"},
  {"id":"60", "name":"Parsa - 4",         "district":"Parsa",           "province":"2","province_name":"Madhesh"},
  # ── BAGMATI (33) ────────────────────────────────────────────
  {"id":"61", "name":"Kathmandu - 1",     "district":"Kathmandu",       "province":"3","province_name":"Bagmati"},
  {"id":"62", "name":"Kathmandu - 2",     "district":"Kathmandu",       "province":"3","province_name":"Bagmati"},
  {"id":"63", "name":"Kathmandu - 3",     "district":"Kathmandu",       "province":"3","province_name":"Bagmati"},
  {"id":"64", "name":"Kathmandu - 4",     "district":"Kathmandu",       "province":"3","province_name":"Bagmati"},
  {"id":"65", "name":"Kathmandu - 5",     "district":"Kathmandu",       "province":"3","province_name":"Bagmati"},
  {"id":"66", "name":"Kathmandu - 6",     "district":"Kathmandu",       "province":"3","province_name":"Bagmati"},
  {"id":"67", "name":"Kathmandu - 7",     "district":"Kathmandu",       "province":"3","province_name":"Bagmati"},
  {"id":"68", "name":"Kathmandu - 8",     "district":"Kathmandu",       "province":"3","province_name":"Bagmati"},
  {"id":"69", "name":"Kathmandu - 9",     "district":"Kathmandu",       "province":"3","province_name":"Bagmati"},
  {"id":"70", "name":"Kathmandu - 10",    "district":"Kathmandu",       "province":"3","province_name":"Bagmati"},
  {"id":"71", "name":"Chitwan - 1",       "district":"Chitwan",         "province":"3","province_name":"Bagmati"},
  {"id":"72", "name":"Chitwan - 2",       "district":"Chitwan",         "province":"3","province_name":"Bagmati"},
  {"id":"73", "name":"Chitwan - 3",       "district":"Chitwan",         "province":"3","province_name":"Bagmati"},
  {"id":"74", "name":"Lalitpur - 1",      "district":"Lalitpur",        "province":"3","province_name":"Bagmati"},
  {"id":"75", "name":"Lalitpur - 2",      "district":"Lalitpur",        "province":"3","province_name":"Bagmati"},
  {"id":"76", "name":"Lalitpur - 3",      "district":"Lalitpur",        "province":"3","province_name":"Bagmati"},
  {"id":"77", "name":"Kavrepalanchok - 1","district":"Kavrepalanchok",  "province":"3","province_name":"Bagmati"},
  {"id":"78", "name":"Kavrepalanchok - 2","district":"Kavrepalanchok",  "province":"3","province_name":"Bagmati"},
  {"id":"79", "name":"Sindhupalchok - 1", "district":"Sindhupalchok",   "province":"3","province_name":"Bagmati"},
  {"id":"80", "name":"Sindhupalchok - 2", "district":"Sindhupalchok",   "province":"3","province_name":"Bagmati"},
  {"id":"81", "name":"Makwanpur - 1",     "district":"Makwanpur",       "province":"3","province_name":"Bagmati"},
  {"id":"82", "name":"Makwanpur - 2",     "district":"Makwanpur",       "province":"3","province_name":"Bagmati"},
  {"id":"83", "name":"Nuwakot - 1",       "district":"Nuwakot",         "province":"3","province_name":"Bagmati"},
  {"id":"84", "name":"Nuwakot - 2",       "district":"Nuwakot",         "province":"3","province_name":"Bagmati"},
  {"id":"85", "name":"Dhading - 1",       "district":"Dhading",         "province":"3","province_name":"Bagmati"},
  {"id":"86", "name":"Dhading - 2",       "district":"Dhading",         "province":"3","province_name":"Bagmati"},
  {"id":"87", "name":"Bhaktapur - 1",     "district":"Bhaktapur",       "province":"3","province_name":"Bagmati"},
  {"id":"88", "name":"Bhaktapur - 2",     "district":"Bhaktapur",       "province":"3","province_name":"Bagmati"},
  {"id":"89", "name":"Dolakha",           "district":"Dolakha",         "province":"3","province_name":"Bagmati"},
  {"id":"90", "name":"Ramechhap",         "district":"Ramechhap",       "province":"3","province_name":"Bagmati"},
  {"id":"91", "name":"Sindhuli - 1",      "district":"Sindhuli",        "province":"3","province_name":"Bagmati"},
  {"id":"92", "name":"Sindhuli - 2",      "district":"Sindhuli",        "province":"3","province_name":"Bagmati"},
  {"id":"93", "name":"Rasuwa",            "district":"Rasuwa",          "province":"3","province_name":"Bagmati"},
  # ── GANDAKI (18) ────────────────────────────────────────────
  {"id":"94",  "name":"Kaski - 1",        "district":"Kaski",           "province":"4","province_name":"Gandaki"},
  {"id":"95",  "name":"Kaski - 2",        "district":"Kaski",           "province":"4","province_name":"Gandaki"},
  {"id":"96",  "name":"Kaski - 3",        "district":"Kaski",           "province":"4","province_name":"Gandaki"},
  {"id":"97",  "name":"Tanahun - 1",      "district":"Tanahun",         "province":"4","province_name":"Gandaki"},
  {"id":"98",  "name":"Tanahun - 2",      "district":"Tanahun",         "province":"4","province_name":"Gandaki"},
  {"id":"99",  "name":"Syangja - 1",      "district":"Syangja",         "province":"4","province_name":"Gandaki"},
  {"id":"100", "name":"Syangja - 2",      "district":"Syangja",         "province":"4","province_name":"Gandaki"},
  {"id":"101", "name":"Baglung - 1",      "district":"Baglung",         "province":"4","province_name":"Gandaki"},
  {"id":"102", "name":"Baglung - 2",      "district":"Baglung",         "province":"4","province_name":"Gandaki"},
  {"id":"103", "name":"Nawalpur - 1",     "district":"Nawalpur",        "province":"4","province_name":"Gandaki"},
  {"id":"104", "name":"Nawalpur - 2",     "district":"Nawalpur",        "province":"4","province_name":"Gandaki"},
  {"id":"105", "name":"Gorkha - 1",       "district":"Gorkha",          "province":"4","province_name":"Gandaki"},
  {"id":"106", "name":"Gorkha - 2",       "district":"Gorkha",          "province":"4","province_name":"Gandaki"},
  {"id":"107", "name":"Lamjung",          "district":"Lamjung",         "province":"4","province_name":"Gandaki"},
  {"id":"108", "name":"Manang",           "district":"Manang",          "province":"4","province_name":"Gandaki"},
  {"id":"109", "name":"Mustang",          "district":"Mustang",         "province":"4","province_name":"Gandaki"},
  {"id":"110", "name":"Myagdi",           "district":"Myagdi",          "province":"4","province_name":"Gandaki"},
  {"id":"111", "name":"Parbat",           "district":"Parbat",          "province":"4","province_name":"Gandaki"},
  # ── LUMBINI (26) ────────────────────────────────────────────
  {"id":"112", "name":"Rupandehi - 1",    "district":"Rupandehi",       "province":"5","province_name":"Lumbini"},
  {"id":"113", "name":"Rupandehi - 2",    "district":"Rupandehi",       "province":"5","province_name":"Lumbini"},
  {"id":"114", "name":"Rupandehi - 3",    "district":"Rupandehi",       "province":"5","province_name":"Lumbini"},
  {"id":"115", "name":"Rupandehi - 4",    "district":"Rupandehi",       "province":"5","province_name":"Lumbini"},
  {"id":"116", "name":"Rupandehi - 5",    "district":"Rupandehi",       "province":"5","province_name":"Lumbini"},
  {"id":"117", "name":"Dang - 1",         "district":"Dang",            "province":"5","province_name":"Lumbini"},
  {"id":"118", "name":"Dang - 2",         "district":"Dang",            "province":"5","province_name":"Lumbini"},
  {"id":"119", "name":"Dang - 3",         "district":"Dang",            "province":"5","province_name":"Lumbini"},
  {"id":"120", "name":"Kapilvastu - 1",   "district":"Kapilvastu",      "province":"5","province_name":"Lumbini"},
  {"id":"121", "name":"Kapilvastu - 2",   "district":"Kapilvastu",      "province":"5","province_name":"Lumbini"},
  {"id":"122", "name":"Kapilvastu - 3",   "district":"Kapilvastu",      "province":"5","province_name":"Lumbini"},
  {"id":"123", "name":"Banke - 1",        "district":"Banke",           "province":"5","province_name":"Lumbini"},
  {"id":"124", "name":"Banke - 2",        "district":"Banke",           "province":"5","province_name":"Lumbini"},
  {"id":"125", "name":"Banke - 3",        "district":"Banke",           "province":"5","province_name":"Lumbini"},
  {"id":"126", "name":"Gulmi - 1",        "district":"Gulmi",           "province":"5","province_name":"Lumbini"},
  {"id":"127", "name":"Gulmi - 2",        "district":"Gulmi",           "province":"5","province_name":"Lumbini"},
  {"id":"128", "name":"Palpa - 1",        "district":"Palpa",           "province":"5","province_name":"Lumbini"},
  {"id":"129", "name":"Palpa - 2",        "district":"Palpa",           "province":"5","province_name":"Lumbini"},
  {"id":"130", "name":"Bardiya - 1",      "district":"Bardiya",         "province":"5","province_name":"Lumbini"},
  {"id":"131", "name":"Bardiya - 2",      "district":"Bardiya",         "province":"5","province_name":"Lumbini"},
  {"id":"132", "name":"Nawalparasi West - 1","district":"Nawalparasi West","province":"5","province_name":"Lumbini"},
  {"id":"133", "name":"Nawalparasi West - 2","district":"Nawalparasi West","province":"5","province_name":"Lumbini"},
  {"id":"134", "name":"Arghakhanchi",     "district":"Arghakhanchi",    "province":"5","province_name":"Lumbini"},
  {"id":"135", "name":"Pyuthan",          "district":"Pyuthan",         "province":"5","province_name":"Lumbini"},
  {"id":"136", "name":"Rolpa",            "district":"Rolpa",           "province":"5","province_name":"Lumbini"},
  {"id":"137", "name":"Rukum East",       "district":"Rukum East",      "province":"5","province_name":"Lumbini"},
  # ── KARNALI (12) ────────────────────────────────────────────
  {"id":"138", "name":"Surkhet - 1",      "district":"Surkhet",         "province":"6","province_name":"Karnali"},
  {"id":"139", "name":"Surkhet - 2",      "district":"Surkhet",         "province":"6","province_name":"Karnali"},
  {"id":"140", "name":"Dailekh - 1",      "district":"Dailekh",         "province":"6","province_name":"Karnali"},
  {"id":"141", "name":"Dailekh - 2",      "district":"Dailekh",         "province":"6","province_name":"Karnali"},
  {"id":"142", "name":"Rukum West",       "district":"Rukum West",      "province":"6","province_name":"Karnali"},
  {"id":"143", "name":"Salyan",           "district":"Salyan",          "province":"6","province_name":"Karnali"},
  {"id":"144", "name":"Jajarkot",         "district":"Jajarkot",        "province":"6","province_name":"Karnali"},
  {"id":"145", "name":"Dolpa",            "district":"Dolpa",           "province":"6","province_name":"Karnali"},
  {"id":"146", "name":"Jumla",            "district":"Jumla",           "province":"6","province_name":"Karnali"},
  {"id":"147", "name":"Kalikot",          "district":"Kalikot",         "province":"6","province_name":"Karnali"},
  {"id":"148", "name":"Mugu",             "district":"Mugu",            "province":"6","province_name":"Karnali"},
  {"id":"149", "name":"Humla",            "district":"Humla",           "province":"6","province_name":"Karnali"},
  # ── SUDURPASHCHIM (16) ──────────────────────────────────────
  {"id":"150", "name":"Kailali - 1",      "district":"Kailali",         "province":"7","province_name":"Sudurpashchim"},
  {"id":"151", "name":"Kailali - 2",      "district":"Kailali",         "province":"7","province_name":"Sudurpashchim"},
  {"id":"152", "name":"Kailali - 3",      "district":"Kailali",         "province":"7","province_name":"Sudurpashchim"},
  {"id":"153", "name":"Kailali - 4",      "district":"Kailali",         "province":"7","province_name":"Sudurpashchim"},
  {"id":"154", "name":"Kailali - 5",      "district":"Kailali",         "province":"7","province_name":"Sudurpashchim"},
  {"id":"155", "name":"Kanchanpur - 1",   "district":"Kanchanpur",      "province":"7","province_name":"Sudurpashchim"},
  {"id":"156", "name":"Kanchanpur - 2",   "district":"Kanchanpur",      "province":"7","province_name":"Sudurpashchim"},
  {"id":"157", "name":"Kanchanpur - 3",   "district":"Kanchanpur",      "province":"7","province_name":"Sudurpashchim"},
  {"id":"158", "name":"Achham - 1",       "district":"Achham",          "province":"7","province_name":"Sudurpashchim"},
  {"id":"159", "name":"Achham - 2",       "district":"Achham",          "province":"7","province_name":"Sudurpashchim"},
  {"id":"160", "name":"Bajura",           "district":"Bajura",          "province":"7","province_name":"Sudurpashchim"},
  {"id":"161", "name":"Bajhang",          "district":"Bajhang",         "province":"7","province_name":"Sudurpashchim"},
  {"id":"162", "name":"Doti",             "district":"Doti",            "province":"7","province_name":"Sudurpashchim"},
  {"id":"163", "name":"Darchula",         "district":"Darchula",        "province":"7","province_name":"Sudurpashchim"},
  {"id":"164", "name":"Baitadi",          "district":"Baitadi",         "province":"7","province_name":"Sudurpashchim"},
  {"id":"165", "name":"Dadeldhura",       "district":"Dadeldhura",      "province":"7","province_name":"Sudurpashchim"},
]

# Quick lookup: name → master entry (for merging live data)
MASTER_BY_NAME = {m["name"].lower(): m for m in MASTER}
MASTER_BY_ID   = {m["id"]: m for m in MASTER}

# Province data (corrected seat counts)
PROVINCES = {
    "1": {"name": "Koshi",         "seats": 28},
    "2": {"name": "Madhesh",       "seats": 32},
    "3": {"name": "Bagmati",       "seats": 33},
    "4": {"name": "Gandaki",       "seats": 18},
    "5": {"name": "Lumbini",       "seats": 26},
    "6": {"name": "Karnali",       "seats": 12},
    "7": {"name": "Sudurpashchim", "seats": 16},
}

# Party color map
PARTY_COLORS = {
    "CPN-UML":                   "#e03030",
    "Nepali Congress":           "#1a8c3a",
    "CPN (Maoist Centre)":       "#cc0000",
    "Rastriya Swatantra Party":  "#f5a623",
    "RSP":                       "#f5a623",
    "RPP":                       "#6a5acd",
    "Rastriya Prajatantra Party":"#6a5acd",
    "Janamat Party":             "#20b2aa",
    "Nagarik Unmukti Party":     "#ff6b6b",
    "CPN (Unified Socialist)":   "#c44b2b",
    "Loktantrik Samajwadi Party":"#2b8c44",
    "Independent":               "#888888",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# SHARED CACHE — seeded with MASTER so dashboard is never empty
# ─────────────────────────────────────────────────────────────
def build_pending_regions():
    """Return all 165 constituencies as pending, using MASTER data."""
    return [
        {
            **m,
            "status":        "pending",
            "votes_counted": 0,
            "total_votes":   50000,
            "parties":       [],
        }
        for m in MASTER
    ]

cache = {
    "regions":      build_pending_regions(),
    "last_updated": None,
    "status":       "initializing",
    "error":        None,
    "hero": {
        "balendra": {"votes": None, "status": None, "constituency": None},
        "oli":      {"votes": None, "status": None, "constituency": None},
    }
}
cache_lock = threading.Lock()

# ─────────────────────────────────────────────────────────────
# SCRAPER — Election Commission REST API
# ─────────────────────────────────────────────────────────────
EC_API_ENDPOINTS = [
    "/api/Result/GetAllConstituencyResult",
    "/api/Result/GetFPTPResult",
    "/api/Result/GetElectionResult",
    "/api/Result/GetConstituencyWiseResult",
    "/api/GetConstituencyResult",
    "/api/result/GetAllConstituencyResult",
    "/api/result/constituency",
    "/api/Result/constituency",
    "/api/Result/GetAllResult",
    "/api/constituency/result",
    "/Result/GetAllConstituencyResult",
]

def try_ec_api():
    """Try hitting the EC REST endpoints directly."""
    for ep in EC_API_ENDPOINTS:
        try:
            url = EC_BASE + ep
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.ok:
                data = r.json()
                if isinstance(data, list) and len(data) > 0:
                    log.info(f"EC API hit: {ep} — {len(data)} records")
                    return data
                if isinstance(data, dict) and data.get("data"):
                    log.info(f"EC API hit: {ep} — {len(data['data'])} records")
                    return data["data"]
        except Exception as e:
            log.debug(f"EC API {ep} failed: {e}")
    return None


def normalize_ec_record(rec):
    """Normalize a raw EC API record into our standard format,
    anchoring to MASTER so IDs and province info stay consistent."""
    parties = []
    raw_parties = (rec.get("Parties") or rec.get("parties") or
                   rec.get("CandidateResults") or [])
    for p in raw_parties:
        parties.append({
            "party":     p.get("PartyName") or p.get("party") or "",
            "candidate": p.get("CandidateName") or p.get("candidate") or "",
            "votes":     int(p.get("VoteCount") or p.get("votes") or 0),
            "status":    ("won"     if p.get("IsWinner")
                          else "leading" if p.get("IsLeading")
                          else "trailing"),
        })
    parties.sort(key=lambda x: x["votes"], reverse=True)

    # Try to match to MASTER by ID first, then by name
    ec_id   = str(rec.get("ConstituencyId") or rec.get("id") or "")
    ec_name = rec.get("ConstituencyName") or rec.get("name") or ""
    base    = (MASTER_BY_ID.get(ec_id) or
               MASTER_BY_NAME.get(ec_name.lower()) or
               None)

    prov_no = str(rec.get("ProvinceNo") or rec.get("province") or
                  (base["province"] if base else "?"))

    return {
        "id":            base["id"]   if base else ec_id,
        "name":          base["name"] if base else ec_name or "Unknown",
        "district":      base["district"]      if base else (rec.get("District") or "—"),
        "province":      base["province"]      if base else prov_no,
        "province_name": base["province_name"] if base else PROVINCES.get(prov_no, {}).get("name", "Province " + prov_no),
        "status":        ("declared" if rec.get("IsResult")
                          else "counting" if (rec.get("VoteCount") or 0) > 100
                          else "pending"),
        "votes_counted": int(rec.get("VoteCount") or rec.get("votes_counted") or 0),
        "total_votes":   int(rec.get("TotalVoters") or rec.get("total_votes") or 50000),
        "parties":       parties,
    }


# ─────────────────────────────────────────────────────────────
# SCRAPER — Playwright (JS-rendered pages)
# ─────────────────────────────────────────────────────────────
def scrape_with_playwright(url, wait_selector=None, timeout=30000):
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_extra_http_headers(HEADERS)
            page.goto(url, timeout=timeout)
            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector, timeout=timeout)
                except Exception:
                    pass
            else:
                page.wait_for_load_state("networkidle", timeout=timeout)
            html = page.content()
            browser.close()
            return html
    except ImportError:
        log.warning("Playwright not installed. Run: playwright install chromium")
        return None
    except Exception as e:
        log.warning(f"Playwright failed for {url}: {e}")
        return None


def parse_table_results(html, source_name):
    """Parse standard HTML table results from any election page."""
    soup = BeautifulSoup(html, "html.parser")
    regions = []
    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        for row in rows[1:]:
            cols = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(cols) >= 3 and cols[0]:
                regions.append({
                    "id":            "",        # blank → merge_live_into_master uses name match
                    "name":          cols[0],
                    "district":      cols[1] if len(cols) > 1 else "—",
                    "province":      "?",
                    "province_name": "Unknown",
                    "status":        "counting",
                    "votes_counted": 0,
                    "total_votes":   50000,
                    "parties": [
                        {"party": cols[2], "candidate": "", "votes": 0, "status": "leading"}
                    ] if len(cols) > 2 else [],
                    "_source": source_name,
                })
    return regions


def scrape_ekantipur():
    """Scrape Ekantipur election results page — parses candidate vote rows."""
    log.info("Scraping Ekantipur...")
    html = scrape_with_playwright(
        EKANTIPUR_BASE + "/?lng=eng",
        wait_selector=".election-result, .constituency-result, table, .result-table, .candidate",
        timeout=45000,
    )
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    regions = []

    # Strategy A: look for structured constituency blocks
    constituency_blocks = soup.find_all(
        ["div", "section", "article"],
        class_=lambda c: c and any(k in c for k in ["constituency", "result", "election"])
    )
    for block in constituency_blocks:
        name_tag = block.find(["h2", "h3", "h4", "strong", "span"],
                               class_=lambda c: c and "name" in (c or ""))
        if not name_tag:
            name_tag = block.find(["h2", "h3", "h4"])
        if not name_tag:
            continue
        name = name_tag.get_text(strip=True)
        if not name or len(name) < 3:
            continue

        parties = []
        candidate_rows = block.find_all(["tr", "li", "div"],
                                         class_=lambda c: c and "candidate" in (c or ""))
        for row in candidate_rows:
            texts = [t.strip() for t in row.stripped_strings if t.strip()]
            if len(texts) >= 2:
                votes = 0
                for t in texts:
                    if t.replace(",", "").isdigit():
                        votes = int(t.replace(",", ""))
                        break
                parties.append({
                    "candidate": texts[0],
                    "party":     texts[1] if len(texts) > 1 else "",
                    "votes":     votes,
                    "status":    "leading" if not parties else "trailing",
                })
        if parties:
            parties.sort(key=lambda x: x["votes"], reverse=True)
            base = MASTER_BY_NAME.get(name.lower())
            regions.append({
                "id":            base["id"]           if base else "",
                "name":          base["name"]         if base else name,
                "district":      base["district"]     if base else "—",
                "province":      base["province"]     if base else "?",
                "province_name": base["province_name"] if base else "Unknown",
                "status":        "counting",
                "votes_counted": parties[0]["votes"] if parties else 0,
                "total_votes":   50000,
                "parties":       parties,
                "_source":       "ekantipur",
            })

    # Strategy B: fall back to table parsing if no blocks found
    if not regions:
        regions = parse_table_results(html, "ekantipur")

    log.info(f"Ekantipur parsed {len(regions)} regions")
    return regions


def scrape_ec_html():
    """Scrape EC results page via Playwright (JS-rendered)."""
    log.info("Scraping EC HTML page...")
    html = scrape_with_playwright(
        EC_BASE + "/",
        wait_selector="table, .result-table",
        timeout=40000,
    )
    if not html:
        return []
    return parse_table_results(html, "ec_html")


# ─────────────────────────────────────────────────────────────
# MERGE LIVE DATA INTO MASTER
# ─────────────────────────────────────────────────────────────
def merge_live_into_master(live_regions):
    """
    Always return all 165 constituencies from MASTER.
    Overlay live data where available; keep pending status for the rest.
    Matches by id first (only when id is non-empty), then by normalised name.
    """
    live_by_id   = {r["id"]: r for r in live_regions if r.get("id")}
    live_by_name = {r["name"].lower(): r for r in live_regions if r.get("name")}

    result = []
    for m in MASTER:
        live = live_by_id.get(m["id"]) or live_by_name.get(m["name"].lower())
        if live:
            merged = {**m}   # start from MASTER (correct id/name/district/province)
            merged["status"]        = live.get("status", "pending")
            merged["votes_counted"] = live.get("votes_counted", 0)
            merged["total_votes"]   = live.get("total_votes", 50000)
            merged["parties"]       = live.get("parties", [])
            result.append(merged)
        else:
            result.append({
                **m,
                "status":        "pending",
                "votes_counted": 0,
                "total_votes":   50000,
                "parties":       [],
            })
    return result


# ─────────────────────────────────────────────────────────────
# CANDIDATE SCRAPER — NepseBajar
# ─────────────────────────────────────────────────────────────
def nepsebajar_slug(name):
    import re
    s = name.lower()
    s = re.sub(r'[^a-z0-9\s-]', '', s)
    s = re.sub(r'\s+', '-', s.strip())
    s = re.sub(r'-+', '-', s)
    return s


def nepsebajar_id(constituency_id):
    return int(constituency_id)


def fetch_candidates_nepsebajar(constituency_id, constituency_name):
    nb_id = nepsebajar_id(constituency_id)
    slug  = nepsebajar_slug(constituency_name)
    url   = f"{NEPSEBAJAR_BASE}/en/pratinidhi/{nb_id}/{slug}-election-result-live-election-2082"
    log.info(f"NepseBajar scrape: {url}")

    try:
        html = scrape_with_playwright(url, wait_selector=".candidate, img", timeout=25000)
        if not html:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.ok:
                html = r.text
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        candidates = []

        for img in soup.find_all("img", src=lambda s: s and "/img/candidates/" in s):
            photo_url = img["src"]
            if not photo_url.startswith("http"):
                photo_url = NEPSEBAJAR_BASE + photo_url

            card = img.find_parent(["div", "article", "li", "a"])
            if not card:
                continue

            name_el = card.find(["h4", "h3", "strong", "a"])
            name = name_el.get_text(strip=True) if name_el else "—"
            if constituency_name.lower() in name.lower() and len(name) > 30:
                name = "—"

            party = "—"
            texts = [t.get_text(strip=True) for t in card.find_all(["p", "span", "div"])
                     if t.get_text(strip=True) and len(t.get_text(strip=True)) > 2]
            for t in texts:
                if any(kw in t for kw in ["Congress", "UML", "Maoist", "Swatantra",
                                           "Prajatantra", "Independent", "Janamat",
                                           "Samajwadi", "Communist", "Unmukti"]):
                    party = t
                    break

            logo_img   = card.find("img", src=lambda s: s and "/partylogo/" in s)
            party_logo = None
            if logo_img:
                party_logo = logo_img["src"]
                if not party_logo.startswith("http"):
                    party_logo = NEPSEBAJAR_BASE + party_logo

            votes = 0
            for t in card.find_all(string=True):
                t = t.strip()
                if t.isdigit() and int(t) > 0:
                    votes = int(t)
                    break

            if name and name != "—":
                candidates.append({
                    "name":       name,
                    "party":      party,
                    "votes":      votes,
                    "status":     "trailing",
                    "photo_url":  photo_url,
                    "party_logo": party_logo,
                })

        if candidates:
            candidates.sort(key=lambda x: x["votes"], reverse=True)
            if candidates[0]["votes"] > 0:
                candidates[0]["status"] = "leading"
            log.info(f"NepseBajar: {len(candidates)} candidates for {constituency_name}")
            return candidates

    except Exception as e:
        log.warning(f"NepseBajar scrape failed for {constituency_name}: {e}")

    return []


def fetch_candidates(constituency_id, constituency_name):
    """
    Fetch candidates. Tries:
    1. EC REST API
    2. NepseBajar scrape (photos + live data)
    3. Returns empty list (dashboard falls back to party list)
    """
    ec_endpoints = [
        f"/api/Result/GetCandidateResult?constituencyId={constituency_id}",
        f"/api/Result/GetCandidateList?constituencyId={constituency_id}",
        f"/api/candidate?constituency={constituency_id}",
        f"/api/Result/GetCandidate/{constituency_id}",
    ]
    for ep in ec_endpoints:
        try:
            r = requests.get(EC_BASE + ep, headers=HEADERS, timeout=10)
            if r.ok:
                data = r.json()
                raw = data if isinstance(data, list) else data.get("data", [])
                if raw:
                    results = []
                    for c in raw:
                        cid   = c.get("CandidateId") or c.get("id") or c.get("candidateId")
                        photo = None
                        for key in ["PhotoPath","Photo","ImagePath","CandidateImage","photo","image"]:
                            val = c.get(key)
                            if val:
                                photo = val if val.startswith("http") else EC_BASE + "/" + val.lstrip("/")
                                break
                        if not photo and cid:
                            photo = f"{EC_BASE}/CandidateImages/{cid}.jpg"

                        results.append({
                            "name":       c.get("CandidateName") or c.get("name") or "—",
                            "party":      c.get("PartyName") or c.get("party") or "—",
                            "votes":      int(c.get("VoteCount") or c.get("votes") or 0),
                            "status":     ("won"     if c.get("IsWinner")
                                           else "leading" if c.get("IsLeading")
                                           else "trailing"),
                            "age":        c.get("Age") or c.get("age"),
                            "education":  c.get("Education") or c.get("education"),
                            "symbol":     c.get("Symbol") or c.get("symbol"),
                            "photo_url":  photo,
                            "party_logo": None,
                        })
                    log.info(f"EC API: {len(results)} candidates for {constituency_name}")
                    return results
        except Exception as e:
            log.debug(f"EC candidate API {ep} failed: {e}")

    nb = fetch_candidates_nepsebajar(constituency_id, constituency_name)
    if nb:
        return nb

    return []


# ─────────────────────────────────────────────────────────────
# HERO VOTE TRACKER
# ─────────────────────────────────────────────────────────────
BALEN_KEYWORDS = ["balendra", "balen shah", "balen"]
OLI_KEYWORDS   = ["kp sharma oli", "kp oli", "sharma oli", "k.p. oli"]

def update_hero_votes(regions):
    balen = {"votes": None, "status": None, "constituency": None}
    oli   = {"votes": None, "status": None, "constituency": None}

    for region in regions:
        for p in region.get("parties", []):
            cname = (p.get("candidate") or "").lower()
            if balen["votes"] is None and any(k in cname for k in BALEN_KEYWORDS):
                balen = {"votes": p["votes"], "status": p["status"], "constituency": region["name"]}
            if oli["votes"] is None and any(k in cname for k in OLI_KEYWORDS):
                oli   = {"votes": p["votes"], "status": p["status"], "constituency": region["name"]}

    with cache_lock:
        if balen["votes"] is not None:
            cache["hero"]["balendra"] = balen
        if oli["votes"] is not None:
            cache["hero"]["oli"] = oli


# ─────────────────────────────────────────────────────────────
# MAIN SCRAPE LOOP
# ─────────────────────────────────────────────────────────────
def scrape_all():
    """Full scrape cycle. Tries EC API → EC HTML → Ekantipur.
    Always produces exactly 165 regions by merging into MASTER."""
    log.info("Starting scrape cycle...")
    live_regions = []

    # Strategy 1: EC REST API
    ec_data = try_ec_api()
    if ec_data:
        live_regions = [normalize_ec_record(r) for r in ec_data]
        log.info(f"EC API: got {len(live_regions)} live records")

    # Strategy 2: EC HTML via Playwright
    if not live_regions:
        live_regions = scrape_ec_html()
        log.info(f"EC HTML: got {len(live_regions)} records")

    # Strategy 3: Ekantipur fallback
    if not live_regions:
        live_regions = scrape_ekantipur()
        log.info(f"Ekantipur: got {len(live_regions)} records")

    # Validate: only discard if zero constituencies have any votes
    if live_regions:
        counting_count = sum(1 for r in live_regions if r.get("votes_counted", 0) > 0)
        if counting_count < 1:
            log.warning("No constituencies with real votes — likely pre-counting data, ignoring.")
            live_regions = []

    # Always produce full 165-region list
    regions = merge_live_into_master(live_regions)

    update_hero_votes(regions)

    # Status: pending → counting → final
    if live_regions:
        finished = sum(1 for r in live_regions if r.get("status") in ("declared", "won", "final"))
        status = "final" if finished == len(regions) else "counting"
    else:
        status = "pending"

    with cache_lock:
        cache["regions"]      = regions
        cache["last_updated"] = datetime.now().isoformat()
        cache["status"]       = status
        cache["error"]        = None if live_regions else "Counting has not started yet — all 165 constituencies pending."
    log.info(f"Cache updated: {len(regions)} regions | live: {len(live_regions)} | status: {status}")


def background_loop():
    while True:
        try:
            scrape_all()
        except Exception as e:
            log.error(f"Scrape loop error: {e}")
            with cache_lock:
                cache["status"] = "error"
                cache["error"]  = str(e)
        time.sleep(REFRESH_INTERVAL)


# ─────────────────────────────────────────────────────────────
# FLASK API
# ─────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)


@app.route("/")
def index():
    return send_from_directory(".", "dashboard.html")


@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(".", filename)


@app.route("/api/status")
def api_status():
    with cache_lock:
        return jsonify({
            "status":       cache["status"],
            "last_updated": cache["last_updated"],
            "total":        len(cache["regions"]),
            "error":        cache["error"],
        })


@app.route("/api/regions")
def api_regions():
    province = request.args.get("province")
    with cache_lock:
        regions = cache["regions"]
        if province and province != "all":
            regions = [r for r in regions if r.get("province") == province]
        return jsonify({
            "status":       cache["status"],
            "last_updated": cache["last_updated"],
            "count":        len(regions),
            "regions":      regions,
        })


@app.route("/api/region/<region_id>")
def api_region(region_id):
    with cache_lock:
        region = next((r for r in cache["regions"] if r["id"] == region_id), None)
    if not region:
        return jsonify({"error": "Region not found"}), 404
    return jsonify(region)


@app.route("/api/candidates/<region_id>")
def api_candidates(region_id):
    with cache_lock:
        region = next((r for r in cache["regions"] if r["id"] == region_id), None)
    if not region:
        return jsonify({"error": "Region not found"}), 404

    candidates = fetch_candidates(region_id, region["name"])
    if not candidates:
        candidates = [
            {
                "name":   p.get("candidate") or p.get("party"),
                "party":  p.get("party"),
                "votes":  p.get("votes", 0),
                "status": p.get("status", "trailing"),
            }
            for p in region.get("parties", [])
        ]
    return jsonify({"candidates": candidates})


@app.route("/api/hero")
def api_hero():
    with cache_lock:
        return jsonify(cache["hero"])


@app.route("/api/summary")
def api_summary():
    with cache_lock:
        regions     = cache["regions"]
        counting    = sum(1 for r in regions if r["status"] == "counting")
        declared    = sum(1 for r in regions if r["status"] == "declared")
        pending     = sum(1 for r in regions if r["status"] == "pending")
        total_votes = sum(r.get("votes_counted", 0) for r in regions)

        party_seats = {}
        for r in regions:
            if r["status"] == "declared" and r.get("parties"):
                winner = r["parties"][0]["party"]
                party_seats[winner] = party_seats.get(winner, 0) + 1

        return jsonify({
            "total_constituencies": len(regions),
            "counting":             counting,
            "declared":             declared,
            "pending":              pending,
            "total_votes_counted":  total_votes,
            "party_seats":          dict(sorted(party_seats.items(), key=lambda x: -x[1])),
            "last_updated":         cache["last_updated"],
        })


# ─────────────────────────────────────────────────────────────
# START BACKGROUND SCRAPER
# Must be at module level — NOT inside __main__ — so that
# gunicorn (used in production on Render) also starts the thread.
# ─────────────────────────────────────────────────────────────
_scraper_thread = threading.Thread(target=background_loop, daemon=True)
_scraper_thread.start()
log.info("Background scraper thread started.")

# ─────────────────────────────────────────────────────────────
# ENTRY POINT (local dev only — gunicorn bypasses this block)
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════╗
║     Nepal Chunab 2082 — Live Election Server         ║
╠══════════════════════════════════════════════════════╣
║  API running at:  http://localhost:5000              ║
║  Open dashboard:  http://localhost:5000              ║
╠══════════════════════════════════════════════════════╣
║  Endpoints:                                          ║
║   GET /api/status          — server health           ║
║   GET /api/regions         — all 165 constituencies  ║
║   GET /api/regions?province=3  — filter by province  ║
║   GET /api/region/<id>     — single region           ║
║   GET /api/candidates/<id> — candidates for region   ║
║   GET /api/hero            — Balen & Oli vote counts ║
║   GET /api/summary         — overall seat tally      ║
╚══════════════════════════════════════════════════════╝
    """)
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
