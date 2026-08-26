import requests, pandas as pd, os, glob, time
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "stock_data")
OUT_DIR  = os.path.join(BASE_DIR, "tdcc_data")
URL = "https://api.finmindtrade.com/api/v4/data"

TOKEN = os.environ.get("FINMIND_TOKEN") or open(
    os.path.join(BASE_DIR, "token.txt"), encoding="utf-8").read().strip()

START = "2024-01-01"          # 要補多久，可自行往前調
SLEEP = 6                     # 每檔間隔秒數，避免被限流

BIG_LV = {"400,001-600,000", "600,001-800,000",
          "800,001-1,000,000", "more than 1,000,001"}
SML_LV = {"1-999", "1,000-5,000"}

os.makedirs(OUT_DIR,