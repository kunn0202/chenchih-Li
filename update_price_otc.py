import requests, pandas as pd, os, time, ssl
from datetime import datetime, timedelta
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

class LaxAdapter(HTTPAdapter):
    def init_poolmanager(self, *a, **kw):
        ctx = create_urllib3_context()
        ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
        kw["ssl_context"] = ctx
        return super().init_poolmanager(*a, **kw)

SESSION = requests.Session()
SESSION.mount("https://", LaxAdapter())

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR  = os.path.join(BASE_DIR, "stock_data")
REF_FILE = os.path.join(OUT_DIR, "6488.csv")
UA = {"User-Agent": "Mozilla/5.0"}

FORCE_FROM = ""

COLMAP = {"成交股數":"Trading_Volume", "成交金額(元)":"Trading_money",
          "開盤":"open", "最高":"max", "最低":"min",
          "收盤":"close", "成交筆數":"Trading_turnover", "漲跌":"spread"}

def num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except Exception:
        return None

def fetch_day(d):
    url = ("https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes"
           f"?response=json&date={d.strftime('%Y/%m/%d')}")
    j = None
    for att in range(3):
        try:
            j = SESSION.get(url, headers=UA, timeout=30).json()
            break
        except Exception as e:
            print(f"    重試 {att+1}/3: {type(e).__name__}")
            time.sleep(5)
    if j is None:
        return None
    for t in j.get("tables", []):
        f = t.get("fields", [])
        if "代號" in f and "收盤" in f:
            rows = t.get("data", [])
            return (f, rows) if rows else None
    return None

def to_records(fields, rows, iso):
    idx = {n: i for i, n in enumerate(fields)}
    out = {}
    for r in rows:
        sid = str(r[idx["代號"]]).strip()
        close = num(r[idx["收盤"]])
        if close is None or close == 0:
            continue
        rec = {"date": iso, "stock_id": sid}
        for zh, en in COLMAP.items():
            rec[en] = num(r[idx[zh]]) if zh in idx else None
        out[sid] = rec
    return out

last = FORCE_FROM or str(pd.read_csv(REF_FILE, dtype={"stock_id": str})["date"].max())
print(f"目前資料到: {last}")

d = datetime.strptime(last, "%Y-%m-%d") + timedelta(days=1)
today = datetime.now()
buf = {}

while d.date() <= today.date():
    if d.weekday() < 5:
        iso = d.strftime("%Y-%m-%d")
        try:
            res = fetch_day(d)
        except Exception as e:
            print(f"  {iso} 連線失敗: {e}")
            res = None
        if res:
            recs = to_records(res[0], res[1], iso)
            print(f"  {iso} 取得 {len(recs)} 檔")
            for sid, rec in recs.items():
                buf.setdefault(sid, []).append(rec)
        else:
            print(f"  {iso} 無資料（休市或尚未公布）")
        time.sleep(5)
    d += timedelta(days=1)

updated = 0
for sid, recs in buf.items():
    path = os.path.join(OUT_DIR, f"{sid}.csv")
    if not os.path.exists(path):
        continue
    old = pd.read_csv(path, dtype={"stock_id": str})
    df = pd.concat([old, pd.DataFrame(recs)], ignore_index=True)
    df = df.drop_duplicates(subset=["date"], keep="last").sort_values("date")
    df.to_csv(path, index=False, encoding="utf-8-sig")
    updated += 1

print(f"\n更新 {updated} 檔")