import requests, pandas as pd, os, time
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR  = os.path.join(BASE_DIR, "stock_data")
REF_FILE = os.path.join(OUT_DIR, "2330.csv")
UA = {"User-Agent": "Mozilla/5.0"}

COLMAP = {"成交股數":"Trading_Volume", "成交金額":"Trading_money",
          "開盤價":"open", "最高價":"max", "最低價":"min",
          "收盤價":"close", "成交筆數":"Trading_turnover"}

def num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except Exception:
        return None

def fetch_day(d):
    url = ("https://www.twse.com.tw/exchangeReport/MI_INDEX"
           f"?response=json&date={d.strftime('%Y%m%d')}&type=ALLBUT0999")
    j = requests.get(url, headers=UA, timeout=30).json()
    if j.get("stat") != "OK":
        return None
    tabs = j.get("tables") or []
    if not tabs:
        for k in list(j.keys()):
            if k.startswith("data") and ("fields" + k[4:]) in j:
                tabs.append({"fields": j["fields" + k[4:]], "data": j[k]})
    for t in tabs:
        f = t.get("fields", [])
        if "證券代號" in f and "收盤價" in f:
            return f, t.get("data", [])
    return None

def to_records(fields, rows, iso):
    idx = {n: i for i, n in enumerate(fields)}
    out = {}
    for r in rows:
        sid = str(r[idx["證券代號"]]).strip()
        close = num(r[idx["收盤價"]])
        if close is None or close == 0:
            continue
        rec = {"date": iso, "stock_id": sid}
        for zh, en in COLMAP.items():
            rec[en] = num(r[idx[zh]]) if zh in idx else None
        sp = num(r[idx["漲跌價差"]]) if "漲跌價差" in idx else None
        sign = str(r[idx["漲跌(+/-)"]]) if "漲跌(+/-)" in idx else ""
        if sp is not None and "-" in sign:
            sp = -sp
        rec["spread"] = sp
        out[sid] = rec
    return out

FORCE_FROM = ""  # 補洞用，平常留空字串 ""
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