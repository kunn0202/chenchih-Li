import requests, pandas as pd, os, time, ssl
from datetime import datetime, timedelta
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR  = os.path.join(BASE_DIR, "inst_data")
REF_FILE = os.path.join(OUT_DIR, "2330.csv")
UA = {"User-Agent": "Mozilla/5.0"}

FORCE_FROM = ""

class LaxAdapter(HTTPAdapter):
    def init_poolmanager(self, *a, **kw):
        ctx = create_urllib3_context()
        ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
        kw["ssl_context"] = ctx
        return super().init_poolmanager(*a, **kw)

SESSION = requests.Session()
SESSION.mount("https://", LaxAdapter())

def num(v):
    try:
        return int(float(str(v).replace(",", "").strip()))
    except Exception:
        return 0

def get(url):
    for att in range(3):
        try:
            return SESSION.get(url, headers=UA, timeout=30).json()
        except Exception as e:
            print(f"    重試 {att+1}/3: {type(e).__name__}")
            time.sleep(5)
    return None

def fetch_twse(d, iso):
    j = get("https://www.twse.com.tw/fund/T86"
            f"?response=json&date={d.strftime('%Y%m%d')}&selectType=ALLBUT0999")
    if not j or j.get("stat") != "OK":
        return {}
    idx = {n: i for i, n in enumerate(j.get("fields", []))}
    need = ["外陸資買進股數(不含外資自營商)", "外陸資賣出股數(不含外資自營商)",
            "投信買進股數", "投信賣出股數",
            "自營商買進股數(自行買賣)", "自營商賣出股數(自行買賣)",
            "自營商買進股數(避險)", "自營商賣出股數(避險)"]
    if any(k not in idx for k in need):
        print("    警告：證交所欄位名稱有變，跳過")
        return {}
    out = {}
    for r in j.get("data", []):
        sid = str(r[idx["證券代號"]]).strip()
        dsb = num(r[idx["自營商買進股數(自行買賣)"]]) + num(r[idx["自營商買進股數(避險)"]])
        dss = num(r[idx["自營商賣出股數(自行買賣)"]]) + num(r[idx["自營商賣出股數(避險)"]])
        out[sid] = [
            {"date": iso, "stock_id": sid, "buy": num(r[idx["外陸資買進股數(不含外資自營商)"]]),
             "name": "Foreign_Investor", "sell": num(r[idx["外陸資賣出股數(不含外資自營商)"]])},
            {"date": iso, "stock_id": sid, "buy": num(r[idx["投信買進股數"]]),
             "name": "Investment_Trust", "sell": num(r[idx["投信賣出股數"]])},
            {"date": iso, "stock_id": sid, "buy": dsb,
             "name": "Dealer_self", "sell": dss},
        ]
    return out

def fetch_tpex(d, iso):
    j = get("https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade"
            f"?type=Daily&sect=EW&date={d.strftime('%Y/%m/%d')}&response=json")
    if not j:
        return {}
    rows = []
    for t in j.get("tables", []):
        if t.get("data"):
            rows = t["data"]
            break
    out = {}
    for r in rows:
        if len(r) < 23:
            continue
        sid = str(r[0]).strip()
        out[sid] = [
            {"date": iso, "stock_id": sid, "buy": num(r[8]),
             "name": "Foreign_Investor", "sell": num(r[9])},
            {"date": iso, "stock_id": sid, "buy": num(r[11]),
             "name": "Investment_Trust", "sell": num(r[12])},
            {"date": iso, "stock_id": sid, "buy": num(r[20]),
             "name": "Dealer_self", "sell": num(r[21])},
        ]
    return out

last = FORCE_FROM or str(pd.read_csv(REF_FILE, dtype={"stock_id": str})["date"].max())
print(f"目前資料到: {last}")

d = datetime.strptime(last, "%Y-%m-%d") + timedelta(days=1)
today = datetime.now()
buf = {}

while d.date() <= today.date():
    if d.weekday() < 5:
        iso = d.strftime("%Y-%m-%d")
        a = fetch_twse(d, iso)
        time.sleep(5)
        b = fetch_tpex(d, iso)
        time.sleep(5)
        print(f"  {iso} 上市 {len(a)} 檔，上櫃 {len(b)} 檔")
        for src in (a, b):
            for sid, recs in src.items():
                buf.setdefault(sid, []).extend(recs)
    d += timedelta(days=1)

updated = 0
for sid, recs in buf.items():
    path = os.path.join(OUT_DIR, f"{sid}.csv")
    if not os.path.exists(path):
        continue
    old = pd.read_csv(path, dtype={"stock_id": str})
    df = pd.concat([old, pd.DataFrame(recs)], ignore_index=True)
    df = df.drop_duplicates(subset=["date", "name"], keep="last").sort_values(["date", "name"])
    df.to_csv(path, index=False, encoding="utf-8-sig")
    updated += 1

print(f"\n更新 {updated} 檔")