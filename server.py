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
REFRESH_INTERVAL = 180          # seconds between scrapes (3 min — more responsive on election day)
EC_BASE          = "https://result.election.gov.np"
EKANTIPUR_BASE   = "https://election.ekantipur.com"
ONLINEKHABAR_BASE= "https://election.onlinekhabar.com"
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
    "source":       "none",
    "error":        None,
    "hero": {
        "balendra": {"votes": None, "status": None, "constituency": None},
        "oli":      {"votes": None, "status": None, "constituency": None},
    }
}
cache_lock = threading.Lock()

# ─────────────────────────────────────────────────────────────
# SCRAPER — Election Commission REST API
# result.election.gov.np uses a .NET backend.
# We try multiple known endpoint patterns — the correct one
# returns a JSON list of constituency result objects.
# ─────────────────────────────────────────────────────────────
EC_API_ENDPOINTS = [
    # Most likely real endpoints (observed from network tab in 2079/2078 elections)
    "/api/Result/GetPRResult",
    "/api/Result/GetFPTPResult",
    "/api/Result/GetAllResult",
    "/api/Result/GetConstituencyWiseResult",
    "/api/Home/GetConstituencyResult",
    "/api/Home/GetAllConstituencyResult",
    # Generic fallbacks
    "/api/Result/GetAllConstituencyResult",
    "/api/GetConstituencyResult",
    "/api/result/GetAllConstituencyResult",
    "/api/result/constituency",
    "/api/Result/constituency",
    "/api/Results",
    "/api/results",
]

def try_ec_api():
    """Try hitting the EC REST endpoints directly.
    Accepts any JSON response that contains a non-empty list
    of objects with constituency-like keys.
    """
    for ep in EC_API_ENDPOINTS:
        try:
            url = EC_BASE + ep
            r = requests.get(url, headers=HEADERS, timeout=20)
            if not r.ok:
                continue
            ct = r.headers.get("Content-Type", "")
            if "json" not in ct and not r.text.strip().startswith(("[", "{")):
                continue
            data = r.json()
            # Accept list directly
            if isinstance(data, list) and len(data) > 0:
                # Sanity-check: at least one item has constituency-like keys
                sample = data[0]
                if any(k for k in sample if "constit" in k.lower() or "name" in k.lower()):
                    log.info(f"EC API hit: {ep} — {len(data)} records")
                    return data
            # Accept wrapped in "data" key
            if isinstance(data, dict):
                for key in ("data", "Data", "result", "Result", "results", "Results"):
                    inner = data.get(key)
                    if isinstance(inner, list) and len(inner) > 0:
                        log.info(f"EC API hit: {ep} (key={key}) — {len(inner)} records")
                        return inner
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
def scrape_with_playwright(url, wait_selector=None, timeout=45000, intercept_json=False):
    """
    Load a JS-rendered page with Playwright.

    If intercept_json=True, also capture any XHR/fetch responses that look
    like election JSON — often faster than parsing the rendered HTML.
    Returns (html, captured_json_list).  html may be None on failure.
    """
    captured_json = []
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            ctx = browser.new_context(
                extra_http_headers={
                    "User-Agent": HEADERS["User-Agent"],
                    "Accept-Language": HEADERS["Accept-Language"],
                },
                ignore_https_errors=True,
            )
            page = ctx.new_page()

            if intercept_json:
                def on_response(response):
                    try:
                        ct = response.headers.get("content-type", "")
                        if "json" in ct and response.status == 200:
                            text = response.text()
                            if len(text) > 200:
                                data = json.loads(text)
                                # Only keep if it looks like election data
                                if isinstance(data, list) and len(data) > 5:
                                    captured_json.append(data)
                                elif isinstance(data, dict):
                                    for k in ("data","Data","result","Result","results","Results"):
                                        v = data.get(k)
                                        if isinstance(v, list) and len(v) > 5:
                                            captured_json.append(v)
                                            break
                    except Exception:
                        pass
                page.on("response", on_response)

            page.goto(url, timeout=timeout, wait_until="domcontentloaded")

            # Try the preferred selector first, then fall back to a short fixed wait
            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector, timeout=15000)
                except Exception:
                    pass
            # Extra 3 s for JS rendering after DOM load
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass

            html = page.content()
            browser.close()
            return html, captured_json
    except ImportError:
        log.warning("Playwright not installed — run: playwright install chromium")
        return None, []
    except Exception as e:
        log.warning(f"Playwright failed for {url}: {e}")
        return None, []


# ── Rich HTML parsers ────────────────────────────────────────

def _extract_number(text):
    """Pull the first integer out of a string."""
    import re
    m = re.search(r"[\d,]+", text.replace(",", ""))
    return int(m.group().replace(",", "")) if m else 0


def parse_ec_html(html):
    """
    Parse the EC results page HTML.
    The page typically shows a table:
      Constituency | Province | Leading Party | Candidate | Votes | Status
    We extract whatever we can and match back to MASTER by name.
    """
    soup = BeautifulSoup(html, "html.parser")
    regions = []

    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        for row in rows[1:]:
            cells = [td.get_text(strip=True) for td in row.find_all(["td","th"])]
            if len(cells) < 2:
                continue

            # Heuristic: first non-empty cell that matches a MASTER constituency
            name = ""
            for cell in cells:
                if cell.lower() in MASTER_BY_NAME:
                    name = cell
                    break
            if not name:
                name = cells[0]

            # Try to find votes column (largest number in the row)
            votes = 0
            for cell in cells:
                n = _extract_number(cell)
                if n > votes:
                    votes = n

            # Party: look for known party keywords
            party = ""
            for cell in cells:
                if any(kw in cell for kw in ["Congress","UML","Maoist","Swatantra",
                                              "Prajatantra","Independent","Janamat",
                                              "Samajwadi","Unmukti","Communist"]):
                    party = cell
                    break

            if name:
                regions.append({
                    "id": "",
                    "name": name,
                    "district": "—",
                    "province": "?",
                    "province_name": "Unknown",
                    "status": "counting",
                    "votes_counted": votes,
                    "total_votes": 50000,
                    "parties": [
                        {"party": party or "Unknown", "candidate": "",
                         "votes": votes, "status": "leading"}
                    ] if party else [],
                    "_source": "ec_html",
                })

    # De-duplicate by name
    seen = set()
    unique = []
    for r in regions:
        key = r["name"].lower()
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


def parse_ekantipur_html(html):
    """
    Ekantipur election page uses React.  The rendered DOM typically contains
    divs/spans rather than tables.  We try tables first, then fall back to
    looking for constituency name patterns inside any element.
    """
    import re
    soup = BeautifulSoup(html, "html.parser")
    regions = []

    # Pass 1: tables (same as before)
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for row in rows[1:]:
            cells = [td.get_text(strip=True) for td in row.find_all(["td","th"])]
            if len(cells) < 2:
                continue
            name = cells[0]
            if not name or len(name) > 80:
                continue
            party = cells[2] if len(cells) > 2 else ""
            votes = _extract_number(cells[3]) if len(cells) > 3 else 0
            regions.append({
                "id": "", "name": name, "district": cells[1] if len(cells) > 1 else "—",
                "province": "?", "province_name": "Unknown",
                "status": "counting", "votes_counted": votes, "total_votes": 50000,
                "parties": [{"party": party, "candidate": "", "votes": votes,
                              "status": "leading"}] if party else [],
                "_source": "ekantipur",
            })

    if regions:
        return regions

    # Pass 2: look for any element whose text matches a known constituency name
    all_text_els = soup.find_all(string=True)
    matched_names = set()
    for text in all_text_els:
        t = text.strip()
        if t.lower() in MASTER_BY_NAME and t not in matched_names:
            matched_names.add(t)
            # Try to find vote count in adjacent sibling/parent text
            parent = text.parent
            nearby_text = " ".join(s.strip() for s in parent.find_all(string=True))
            votes = _extract_number(nearby_text)
            regions.append({
                "id": "", "name": t, "district": "—",
                "province": "?", "province_name": "Unknown",
                "status": "counting" if votes > 0 else "pending",
                "votes_counted": votes, "total_votes": 50000,
                "parties": [], "_source": "ekantipur",
            })

    return regions


def scrape_ec_html():
    """Scrape EC results page (JS-rendered). Also intercepts XHR JSON."""
    log.info("Scraping EC HTML page...")
    html, captured = scrape_with_playwright(
        EC_BASE + "/",
        wait_selector="table, tr, .result",
        intercept_json=True,
    )
    # Prefer intercepted JSON (more structured)
    if captured:
        for payload in captured:
            try:
                normalised = [normalize_ec_record(r) for r in payload]
                if normalised:
                    log.info(f"EC HTML (intercepted JSON): {len(normalised)} records")
                    return normalised
            except Exception as e:
                log.debug(f"EC intercepted JSON parse error: {e}")

    if not html:
        return []
    result = parse_ec_html(html)
    log.info(f"EC HTML (parsed): {len(result)} records")
    return result


def scrape_ekantipur():
    """Scrape Ekantipur election results page."""
    log.info("Scraping Ekantipur...")
    html, captured = scrape_with_playwright(
        EKANTIPUR_BASE + "/?lng=eng",
        wait_selector="table, .constituency, [class*='result'], [class*='Result']",
        intercept_json=True,
        timeout=50000,
    )
    if captured:
        for payload in captured:
            try:
                normalised = [normalize_ec_record(r) for r in payload]
                if normalised:
                    log.info(f"Ekantipur (intercepted JSON): {len(normalised)} records")
                    return normalised
            except Exception:
                pass
    if not html:
        return []
    result = parse_ekantipur_html(html)
    log.info(f"Ekantipur (parsed HTML): {len(result)} records")
    return result


def scrape_chunab_org():
    """Scrape chunab.org as an additional fallback."""
    log.info("Scraping chunab.org...")
    try:
        r = requests.get(CHUNAB_BASE + "/results", headers=HEADERS, timeout=20)
        if not r.ok:
            r = requests.get(CHUNAB_BASE, headers=HEADERS, timeout=20)
        if r.ok:
            result = parse_ec_html(r.text)   # generic table parser
            if result:
                for rec in result:
                    rec["_source"] = "chunab_org"
                log.info(f"chunab.org: {len(result)} records")
                return result
    except Exception as e:
        log.warning(f"chunab.org failed: {e}")

    # Try with Playwright
    html, captured = scrape_with_playwright(
        CHUNAB_BASE,
        wait_selector="table, tr",
        intercept_json=True,
        timeout=40000,
    )
    if captured:
        for payload in captured:
            try:
                normalised = [normalize_ec_record(r) for r in payload]
                if normalised:
                    log.info(f"chunab.org (intercepted JSON): {len(normalised)} records")
                    return normalised
            except Exception:
                pass
    if html:
        result = parse_ec_html(html)
        if result:
            log.info(f"chunab.org (parsed): {len(result)} records")
            return result
    return []


# ─────────────────────────────────────────────────────────────
# SCRAPER — OnlineKhabar (PRIMARY)
# URL pattern: election.onlinekhabar.com/<province-slug>/<district><N>
# The results table on each constituency page is server-side rendered
# (WordPress), so plain requests works — no Playwright needed.
# We also try their wp-json custom endpoint first.
# ─────────────────────────────────────────────────────────────

# Mapping: MASTER constituency name → OnlineKhabar URL slug
# Derived from the live site's navigation (seen in fetched HTML)
OK_SLUGS = {
    # Province slugs observed: koshi-chetra, madhesh-chetra, central-chetra,
    # gandaki-chetra, lumbini-chetra, karnali-chetra, sudurpashchim-chetra
    # District+number slug pattern: districtname+number (Nepali digits stripped, latin only)
    "Morang - 1":          ("koshi-chetra",         "morang1"),
    "Morang - 2":          ("koshi-chetra",         "morang2"),
    "Morang - 3":          ("koshi-chetra",         "morang3"),
    "Morang - 4":          ("koshi-chetra",         "morang4"),
    "Morang - 5":          ("koshi-chetra",         "morang5"),
    "Morang - 6":          ("koshi-chetra",         "morang6"),
    "Jhapa - 1":           ("koshi-chetra",         "jhapa1"),
    "Jhapa - 2":           ("koshi-chetra",         "jhapa2"),
    "Jhapa - 3":           ("koshi-chetra",         "jhapa3"),
    "Jhapa - 4":           ("koshi-chetra",         "jhapa4"),
    "Jhapa - 5":           ("koshi-chetra",         "jhapa5"),
    "Sunsari - 1":         ("koshi-chetra",         "sunsari1"),
    "Sunsari - 2":         ("koshi-chetra",         "sunsari2"),
    "Sunsari - 3":         ("koshi-chetra",         "sunsari3"),
    "Sunsari - 4":         ("koshi-chetra",         "sunsari4"),
    "Ilam - 1":            ("koshi-chetra",         "ilam1"),
    "Ilam - 2":            ("koshi-chetra",         "ilam2"),
    "Udayapur - 1":        ("koshi-chetra",         "udayapur1"),
    "Udayapur - 2":        ("koshi-chetra",         "udayapur2"),
    "Taplejung":           ("koshi-chetra",         "taplejung1"),
    "Panchthar":           ("koshi-chetra",         "panchthar1"),
    "Sankhuwasabha":       ("koshi-chetra",         "sankhuwasabha1"),
    "Tehrathum":           ("koshi-chetra",         "tehrathum1"),
    "Bhojpur":             ("koshi-chetra",         "bhojpur1"),
    "Dhankuta":            ("koshi-chetra",         "dhankuta1"),
    "Solukhumbu":          ("koshi-chetra",         "solukhumbu1"),
    "Khotang":             ("koshi-chetra",         "khotang1"),
    "Okhaldhunga":         ("koshi-chetra",         "okhaldhunga1"),
    "Saptari - 1":         ("madhesh-chetra",       "saptari1"),
    "Saptari - 2":         ("madhesh-chetra",       "saptari2"),
    "Saptari - 3":         ("madhesh-chetra",       "saptari3"),
    "Saptari - 4":         ("madhesh-chetra",       "saptari4"),
    "Siraha - 1":          ("madhesh-chetra",       "siraha1"),
    "Siraha - 2":          ("madhesh-chetra",       "siraha2"),
    "Siraha - 3":          ("madhesh-chetra",       "siraha3"),
    "Siraha - 4":          ("madhesh-chetra",       "siraha4"),
    "Dhanusha - 1":        ("madhesh-chetra",       "dhanusha1"),
    "Dhanusha - 2":        ("madhesh-chetra",       "dhanusha2"),
    "Dhanusha - 3":        ("madhesh-chetra",       "dhanusha3"),
    "Dhanusha - 4":        ("madhesh-chetra",       "dhanusha4"),
    "Mahottari - 1":       ("madhesh-chetra",       "mahottari1"),
    "Mahottari - 2":       ("madhesh-chetra",       "mahottari2"),
    "Mahottari - 3":       ("madhesh-chetra",       "mahottari3"),
    "Mahottari - 4":       ("madhesh-chetra",       "mahottari4"),
    "Sarlahi - 1":         ("madhesh-chetra",       "sarlahi1"),
    "Sarlahi - 2":         ("madhesh-chetra",       "sarlahi2"),
    "Sarlahi - 3":         ("madhesh-chetra",       "sarlahi3"),
    "Sarlahi - 4":         ("madhesh-chetra",       "sarlahi4"),
    "Rautahat - 1":        ("madhesh-chetra",       "rautahat1"),
    "Rautahat - 2":        ("madhesh-chetra",       "rautahat2"),
    "Rautahat - 3":        ("madhesh-chetra",       "rautahat3"),
    "Rautahat - 4":        ("madhesh-chetra",       "rautahat4"),
    "Bara - 1":            ("madhesh-chetra",       "bara1"),
    "Bara - 2":            ("madhesh-chetra",       "bara2"),
    "Bara - 3":            ("madhesh-chetra",       "bara3"),
    "Bara - 4":            ("madhesh-chetra",       "bara4"),
    "Parsa - 1":           ("madhesh-chetra",       "parsa1"),
    "Parsa - 2":           ("madhesh-chetra",       "parsa2"),
    "Parsa - 3":           ("madhesh-chetra",       "parsa3"),
    "Parsa - 4":           ("madhesh-chetra",       "parsa4"),
    "Kathmandu - 1":       ("central-chetra",       "kathmandu1"),
    "Kathmandu - 2":       ("central-chetra",       "kathmandu2"),
    "Kathmandu - 3":       ("central-chetra",       "kathmandu3"),
    "Kathmandu - 4":       ("central-chetra",       "kathmandu4"),
    "Kathmandu - 5":       ("central-chetra",       "kathmandu5"),
    "Kathmandu - 6":       ("central-chetra",       "kathmandu6"),
    "Kathmandu - 7":       ("central-chetra",       "kathmandu7"),
    "Kathmandu - 8":       ("central-chetra",       "kathmandu8"),
    "Kathmandu - 9":       ("central-chetra",       "kathmandu9"),
    "Kathmandu - 10":      ("central-chetra",       "kathmandu10"),
    "Chitwan - 1":         ("central-chetra",       "chitwan1"),
    "Chitwan - 2":         ("central-chetra",       "chitwan2"),
    "Chitwan - 3":         ("central-chetra",       "chitwan3"),
    "Lalitpur - 1":        ("central-chetra",       "lalitpur1"),
    "Lalitpur - 2":        ("central-chetra",       "lalitpur2"),
    "Lalitpur - 3":        ("central-chetra",       "lalitpur3"),
    "Kavrepalanchok - 1":  ("central-chetra",       "kavre1"),
    "Kavrepalanchok - 2":  ("central-chetra",       "kavre2"),
    "Sindhupalchok - 1":   ("central-chetra",       "sindhupalchok1"),
    "Sindhupalchok - 2":   ("central-chetra",       "sindhupalchok2"),
    "Makwanpur - 1":       ("central-chetra",       "makwanpur1"),
    "Makwanpur - 2":       ("central-chetra",       "makwanpur2"),
    "Nuwakot - 1":         ("central-chetra",       "nuwakot1"),
    "Nuwakot - 2":         ("central-chetra",       "nuwakot2"),
    "Dhading - 1":         ("central-chetra",       "dhading1"),
    "Dhading - 2":         ("central-chetra",       "dhading2"),
    "Bhaktapur - 1":       ("central-chetra",       "bhaktapur1"),
    "Bhaktapur - 2":       ("central-chetra",       "bhaktapur2"),
    "Dolakha":             ("central-chetra",       "dolakha1"),
    "Ramechhap":           ("central-chetra",       "ramechhap1"),
    "Sindhuli - 1":        ("central-chetra",       "sindhuli1"),
    "Sindhuli - 2":        ("central-chetra",       "sindhuli2"),
    "Rasuwa":              ("central-chetra",       "rasuwa1"),
    "Kaski - 1":           ("gandaki-chetra",       "kaski1"),
    "Kaski - 2":           ("gandaki-chetra",       "kaski2"),
    "Kaski - 3":           ("gandaki-chetra",       "kaski3"),
    "Tanahun - 1":         ("gandaki-chetra",       "tanahun1"),
    "Tanahun - 2":         ("gandaki-chetra",       "tanahun2"),
    "Syangja - 1":         ("gandaki-chetra",       "syangja1"),
    "Syangja - 2":         ("gandaki-chetra",       "syangja2"),
    "Baglung - 1":         ("gandaki-chetra",       "baglung1"),
    "Baglung - 2":         ("gandaki-chetra",       "baglung2"),
    "Nawalpur - 1":        ("gandaki-chetra",       "nawalpur1"),
    "Nawalpur - 2":        ("gandaki-chetra",       "nawalpur2"),
    "Gorkha - 1":          ("gandaki-chetra",       "gorkha1"),
    "Gorkha - 2":          ("gandaki-chetra",       "gorkha2"),
    "Lamjung":             ("gandaki-chetra",       "lamjung1"),
    "Manang":              ("gandaki-chetra",       "manang1"),
    "Mustang":             ("gandaki-chetra",       "mustang1"),
    "Myagdi":              ("gandaki-chetra",       "myagdi1"),
    "Parbat":              ("gandaki-chetra",       "parbat1"),
    "Rupandehi - 1":       ("lumbini-chetra",       "rupandehi1"),
    "Rupandehi - 2":       ("lumbini-chetra",       "rupandehi2"),
    "Rupandehi - 3":       ("lumbini-chetra",       "rupandehi3"),
    "Rupandehi - 4":       ("lumbini-chetra",       "rupandehi4"),
    "Rupandehi - 5":       ("lumbini-chetra",       "rupandehi5"),
    "Dang - 1":            ("lumbini-chetra",       "dang1"),
    "Dang - 2":            ("lumbini-chetra",       "dang2"),
    "Dang - 3":            ("lumbini-chetra",       "dang3"),
    "Kapilvastu - 1":      ("lumbini-chetra",       "kapilvastu1"),
    "Kapilvastu - 2":      ("lumbini-chetra",       "kapilvastu2"),
    "Kapilvastu - 3":      ("lumbini-chetra",       "kapilvastu3"),
    "Banke - 1":           ("lumbini-chetra",       "banke1"),
    "Banke - 2":           ("lumbini-chetra",       "banke2"),
    "Banke - 3":           ("lumbini-chetra",       "banke3"),
    "Gulmi - 1":           ("lumbini-chetra",       "gulmi1"),
    "Gulmi - 2":           ("lumbini-chetra",       "gulmi2"),
    "Palpa - 1":           ("lumbini-chetra",       "palpa1"),
    "Palpa - 2":           ("lumbini-chetra",       "palpa2"),
    "Bardiya - 1":         ("lumbini-chetra",       "bardiya1"),
    "Bardiya - 2":         ("lumbini-chetra",       "bardiya2"),
    "Nawalparasi West - 1":("lumbini-chetra",       "nawalparasi1"),
    "Nawalparasi West - 2":("lumbini-chetra",       "nawalparasi2"),
    "Arghakhanchi":        ("lumbini-chetra",       "arghakhanchi1"),
    "Pyuthan":             ("lumbini-chetra",       "pyuthan1"),
    "Rolpa":               ("lumbini-chetra",       "rolpa1"),
    "Rukum East":          ("lumbini-chetra",       "rukumpurba1"),
    "Surkhet - 1":         ("karnali-chetra",       "surkhet1"),
    "Surkhet - 2":         ("karnali-chetra",       "surkhet2"),
    "Dailekh - 1":         ("karnali-chetra",       "dailekh1"),
    "Dailekh - 2":         ("karnali-chetra",       "dailekh2"),
    "Rukum West":          ("karnali-chetra",       "rukumpashchim1"),
    "Salyan":              ("karnali-chetra",       "salyan1"),
    "Jajarkot":            ("karnali-chetra",       "jajarkot1"),
    "Dolpa":               ("karnali-chetra",       "dolpa1"),
    "Jumla":               ("karnali-chetra",       "jumla1"),
    "Kalikot":             ("karnali-chetra",       "kalikot1"),
    "Mugu":                ("karnali-chetra",       "mugu1"),
    "Humla":               ("karnali-chetra",       "humla1"),
    "Kailali - 1":         ("sudurpashchim-chetra", "kailali1"),
    "Kailali - 2":         ("sudurpashchim-chetra", "kailali2"),
    "Kailali - 3":         ("sudurpashchim-chetra", "kailali3"),
    "Kailali - 4":         ("sudurpashchim-chetra", "kailali4"),
    "Kailali - 5":         ("sudurpashchim-chetra", "kailali5"),
    "Kanchanpur - 1":      ("sudurpashchim-chetra", "kanchanpur1"),
    "Kanchanpur - 2":      ("sudurpashchim-chetra", "kanchanpur2"),
    "Kanchanpur - 3":      ("sudurpashchim-chetra", "kanchanpur3"),
    "Achham - 1":          ("sudurpashchim-chetra", "achham1"),
    "Achham - 2":          ("sudurpashchim-chetra", "achham2"),
    "Bajura":              ("sudurpashchim-chetra", "bajura1"),
    "Bajhang":             ("sudurpashchim-chetra", "bajhang1"),
    "Doti":                ("sudurpashchim-chetra", "doti1"),
    "Darchula":            ("sudurpashchim-chetra", "darchula1"),
    "Baitadi":             ("sudurpashchim-chetra", "baitadi1"),
    "Dadeldhura":          ("sudurpashchim-chetra", "dadeldhura1"),
}


def parse_ok_constituency_page(html, constituency_name):
    """
    Parse a single OnlineKhabar constituency result page.
    The vote table looks like:
      | S.N. | Candidate (Party) | Votes |
    Votes column is empty until counting starts, then fills with numbers.
    """
    import re
    soup = BeautifulSoup(html, "html.parser")
    parties = []

    # Find the result table — it has columns: S.N. | उम्मेदवार | पार्टी | प्राप्त मत
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) < 3:
                continue

            # Candidate cell (index 1) contains name + party text
            cand_cell = cells[1].get_text(" ", strip=True)
            # Party cell may be separate (index 2) or embedded
            party_cell = cells[2].get_text(strip=True) if len(cells) > 2 else ""
            # Votes cell (last)
            votes_text = cells[-1].get_text(strip=True)
            votes = _extract_number(votes_text) if votes_text else 0

            # Extract candidate name (first line of cell)
            lines = [l.strip() for l in cand_cell.split("\n") if l.strip()]
            cand_name = lines[0] if lines else "—"

            # Identify party — look in dedicated party cell or candidate cell
            party = ""
            for text in [party_cell, cand_cell]:
                for kw in ["Congress","UML","Maoist","Swatantra","Prajatantra",
                           "Independent","Janamat","Samajwadi","Communist",
                           "Unmukti","कांग्रेस","एमाले","माओवादी","स्वतन्त्र",
                           "Rastriya","Nepali","CPN","NCP"]:
                    if kw.lower() in text.lower():
                        # use the party cell text if available, otherwise keyword
                        party = party_cell if party_cell else kw
                        break
                if party:
                    break

            if cand_name and cand_name != "S.N." and not cand_name.isdigit():
                parties.append({
                    "party":     party or "Unknown",
                    "candidate": cand_name,
                    "votes":     votes,
                    "status":    "trailing",
                })

    if not parties:
        return None

    parties.sort(key=lambda x: x["votes"], reverse=True)
    if parties and parties[0]["votes"] > 0:
        parties[0]["status"] = "leading"

    votes_counted = sum(p["votes"] for p in parties)
    status = "counting" if votes_counted > 0 else "pending"

    return {
        "name":          constituency_name,
        "status":        status,
        "votes_counted": votes_counted,
        "total_votes":   50000,
        "parties":       parties,
        "_source":       "onlinekhabar",
    }


def scrape_onlinekhabar_one(name):
    """Fetch and parse a single OnlineKhabar constituency page. Returns result dict or None."""
    slug_info = OK_SLUGS.get(name)
    if not slug_info:
        log.debug(f"No OK slug for: {name}")
        return None
    prov_slug, const_slug = slug_info
    url = f"{ONLINEKHABAR_BASE}/{prov_slug}/{const_slug}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if not r.ok:
            log.debug(f"OK {name}: HTTP {r.status_code}")
            return None
        result = parse_ok_constituency_page(r.text, name)
        if result:
            log.info(f"✓ {name} — {result['votes_counted']} votes ({result['status']})")
        return result
    except Exception as e:
        log.debug(f"OK fetch failed for {name}: {e}")
        return None


def rolling_scrape_loop():
    """
    Continuously scrapes OnlineKhabar one constituency at a time, forever.
    After each fetch the cache is updated immediately so the dashboard
    always shows the freshest data possible.

    Sequence: constituency 1 → 2 → 3 → ... → 165 → 1 → 2 → ...
    A short delay between each request avoids hammering the server.
    """
    DELAY_BETWEEN = 5   # seconds between each constituency fetch
    DELAY_ON_ERROR = 10 # seconds to wait after a failed fetch

    names = [m["name"] for m in MASTER]
    log.info(f"Rolling scraper started — {len(names)} constituencies, {DELAY_BETWEEN}s delay each")
    log.info(f"Full cycle time ≈ {len(names) * DELAY_BETWEEN // 60} min {len(names) * DELAY_BETWEEN % 60}s")

    round_num = 0
    while True:
        round_num += 1
        log.info(f"━━━ Round {round_num} starting ━━━")
        success_count = 0

        for i, name in enumerate(names, 1):
            result = scrape_onlinekhabar_one(name)

            if result:
                success_count += 1
                # Merge this single result into the cache immediately
                with cache_lock:
                    for j, region in enumerate(cache["regions"]):
                        if region["name"] == name:
                            cache["regions"][j] = {
                                **region,
                                "status":        result.get("status", region["status"]),
                                "votes_counted": result.get("votes_counted", region["votes_counted"]),
                                "total_votes":   result.get("total_votes", region["total_votes"]),
                                "parties":       result.get("parties", region["parties"]),
                            }
                            break
                    cache["last_updated"] = datetime.now().isoformat()
                    cache["status"]       = "ok"
                    cache["source"]       = "onlinekhabar_rolling"
                    cache["error"]        = None

                # Keep hero votes fresh
                with cache_lock:
                    update_hero_votes(cache["regions"])

                time.sleep(DELAY_BETWEEN)
            else:
                time.sleep(DELAY_ON_ERROR)

        log.info(f"━━━ Round {round_num} done — {success_count}/{len(names)} fetched ━━━")


def scrape_onlinekhabar_all():
    """
    One-shot batch fetch of all 165 pages (used only at startup for the
    initial cache fill before the rolling loop takes over).
    Uses a thread pool so startup is fast.
    """
    import concurrent.futures

    log.info("Startup batch: fetching all 165 OnlineKhabar pages in parallel...")
    results = []
    names = [m["name"] for m in MASTER]

    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as pool:
        futures = {pool.submit(scrape_onlinekhabar_one, name): name for name in names}
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                results.append(result)

    live = [r for r in results if r and r.get("status") != "pending"]
    log.info(f"Startup batch done: {len(live)} live / {len(results)} fetched")
    return results


def scrape_onlinekhabar_summary():
    """
    Fast path: scrape the OnlineKhabar homepage which shows a party seat
    summary and any highlighted results — used as a quick sanity check.
    Also tries the WordPress REST API for any custom election endpoint.
    """
    # Try WordPress custom REST endpoint first
    ok_api_endpoints = [
        "/wp-json/election/v1/results",
        "/wp-json/election/v1/constituencies",
        "/wp-json/ok-election/v1/results",
        "/wp-json/wp/v2/election-result",
        "/wp-json/election-api/v1/all",
    ]
    for ep in ok_api_endpoints:
        try:
            url = ONLINEKHABAR_BASE + ep
            r = requests.get(url, headers=HEADERS, timeout=10)
            if r.ok and "json" in r.headers.get("Content-Type", ""):
                data = r.json()
                if isinstance(data, list) and len(data) > 5:
                    log.info(f"OnlineKhabar REST API hit: {ep} — {len(data)} records")
                    return data  # raw, caller normalises
                if isinstance(data, dict):
                    for key in ("data", "results", "constituencies"):
                        inner = data.get(key, [])
                        if isinstance(inner, list) and len(inner) > 5:
                            log.info(f"OnlineKhabar REST API hit: {ep} key={key}")
                            return inner
        except Exception:
            pass
    return None


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

    # Try multiple URL patterns
    url_patterns = [
        f"{NEPSEBAJAR_BASE}/en/pratinidhi/{nb_id}/{slug}-election-result-live-election-2082",
        f"{NEPSEBAJAR_BASE}/en/pratinidhi/{nb_id}/{slug}",
        f"{NEPSEBAJAR_BASE}/en/constituency/{nb_id}",
        f"{NEPSEBAJAR_BASE}/en/result/{nb_id}",
    ]

    for url in url_patterns:
        log.info(f"NepseBajar try: {url}")
        try:
            # Try plain requests first (much faster)
            r = requests.get(url, headers=HEADERS, timeout=12)
            html = r.text if r.ok and len(r.text) > 500 else None

            if not html:
                pw_html, _ = scrape_with_playwright(url, wait_selector=".candidate, img", timeout=20000)
                html = pw_html

            if not html:
                continue

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
            log.warning(f"NepseBajar failed for {constituency_name} ({url}): {e}")

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
    """
    Full scrape cycle.
    Priority:
      1. OnlineKhabar REST API (fastest if available)
      2. OnlineKhabar per-constituency pages (parallel, reliable)
      3. EC REST API
      4. EC HTML + XHR intercept
      5. Ekantipur
      6. chunab.org
    Always produces exactly 165 regions by merging live data into MASTER.
    """
    log.info("Starting scrape cycle...")
    live_regions = []
    source_used  = "none"

    # ── Strategy 1: OnlineKhabar WordPress REST API (instant if present) ──
    ok_api_data = scrape_onlinekhabar_summary()
    if ok_api_data:
        try:
            live_regions = [normalize_ec_record(r) for r in ok_api_data]
            source_used  = "onlinekhabar_api"
            log.info(f"Strategy 1 (OK REST API): {len(live_regions)} records")
        except Exception as e:
            log.warning(f"OK API normalise failed: {e}")
            live_regions = []

    # ── Strategy 2: OnlineKhabar per-page scrape (parallel HTTP) ──────────
    if not live_regions:
        ok_pages = scrape_onlinekhabar_all()
        if ok_pages:
            live_regions = ok_pages
            source_used  = "onlinekhabar_pages"
            log.info(f"Strategy 2 (OK pages): {len(live_regions)} records")

    # ── Strategy 3: EC REST API ────────────────────────────────────────────
    if not live_regions:
        ec_data = try_ec_api()
        if ec_data:
            live_regions = [normalize_ec_record(r) for r in ec_data]
            source_used  = "ec_api"
            log.info(f"Strategy 3 (EC API): {len(live_regions)} records")

    # ── Strategy 4: EC HTML + XHR intercept ───────────────────────────────
    if not live_regions:
        live_regions = scrape_ec_html()
        if live_regions:
            source_used = "ec_html"
        log.info(f"Strategy 4 (EC HTML): {len(live_regions)} records")

    # ── Strategy 5: Ekantipur ──────────────────────────────────────────────
    if not live_regions:
        live_regions = scrape_ekantipur()
        if live_regions:
            source_used = "ekantipur"
        log.info(f"Strategy 5 (Ekantipur): {len(live_regions)} records")

    # ── Strategy 6: chunab.org ─────────────────────────────────────────────
    if not live_regions:
        live_regions = scrape_chunab_org()
        if live_regions:
            source_used = "chunab_org"
        log.info(f"Strategy 6 (chunab.org): {len(live_regions)} records")

    # Always produce full 165-region list
    regions = merge_live_into_master(live_regions)

    update_hero_votes(regions)
    with cache_lock:
        cache["regions"]      = regions
        cache["last_updated"] = datetime.now().isoformat()
        cache["source"]       = source_used
        cache["status"]       = "ok" if live_regions else "pending"
        cache["error"]        = (
            None if live_regions
            else "All sources failed or counting has not started yet."
        )
    log.info(f"Cache updated: {len(regions)} regions | live: {len(live_regions)} | source: {source_used}")


def background_loop():
    """
    Startup sequence:
      1. Quick initial batch fill (parallel) so the dashboard isn't empty
      2. Launch the rolling one-by-one loop in a separate thread
      3. This thread then falls back to EC/Ekantipur if OnlineKhabar fails
    """
    # ── Step 1: fast initial fill via batch scrape ──
    log.info("=== Startup: running initial batch scrape ===")
    try:
        ok_pages = scrape_onlinekhabar_all()
        if ok_pages:
            regions = merge_live_into_master(ok_pages)
            update_hero_votes(regions)
            with cache_lock:
                cache["regions"]      = regions
                cache["last_updated"] = datetime.now().isoformat()
                cache["status"]       = "ok"
                cache["source"]       = "onlinekhabar_startup"
                cache["error"]        = None
            log.info(f"=== Initial batch done: {len(ok_pages)} regions loaded ===")
        else:
            log.warning("Initial batch returned nothing — trying EC fallback...")
            scrape_all()  # full fallback chain
    except Exception as e:
        log.error(f"Startup batch error: {e}")
        try:
            scrape_all()
        except Exception as e2:
            log.error(f"Fallback scrape also failed: {e2}")

    # ── Step 2: launch the rolling loop in a background thread ──
    rolling_thread = threading.Thread(target=rolling_scrape_loop, daemon=True)
    rolling_thread.start()
    log.info("Rolling scraper thread launched.")

    # ── Step 3: this thread periodically runs the full fallback chain
    # in case OnlineKhabar goes down (every 10 minutes) ──
    FALLBACK_INTERVAL = 600
    while True:
        time.sleep(FALLBACK_INTERVAL)
        with cache_lock:
            src = cache.get("source", "")
        if "onlinekhabar" not in src:
            log.info("Rolling scraper appears stalled — running full fallback chain...")
            try:
                scrape_all()
            except Exception as e:
                log.error(f"Fallback loop error: {e}")


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
            "source":       cache.get("source", "unknown"),
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
