import requests, pandas as pd, os, time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN = open(os.path.join(BASE_DIR, "token.txt"), encoding="utf-8").read().strip()
OUT_DIR = os.path.join(BASE_DIR, "fin_data")
LIST_PATH = os.path.join(BASE_DIR, "stock_list.csv")
URL = "https://api.finmindtrade.com/api/v4/data"
SLEEP = 6.5

os.makedirs(OUT_DIR, exist_ok=True)
ids = pd.read_csv(LIST_PATH, dtype={"stock_id": str})["stock_id"].tolist()


def last_date(path):
    try:
        df = pd.read_csv(path, dtype={"stock_id": str})
        return str(df["date"].max()) if "date" in df.columns and len(df) else None
    except Exception:
        return None


def fetch(sid, sdate):
    p = {"dataset": "TaiwanStockFinancialStatements", "data_id": sid,
         "start_date": sdate, "end_date": "2030-12-31", "token": TOKEN}
    for att in range(3):
        try:
            j = requests.get(URL, params=p, timeout=30).json()
        except Exception as e:
            print(f"    連線失敗 {att+1}/3: {type(e).__name__}")
            time.sleep(10); continue
        if j.get("status") == 200:
            return j.get("data", [])
        msg = str(j.get("msg", ""))
        if "402" in msg or "limit" in msg.lower():
            print("    額度用完，休息 61 分鐘…")
            time.sleep(3660); continue
        print(f"    API 錯誤 {sid}: {msg}")
        return None
    return None


probe = fetch("2330", "2026-01-01")
time.sleep(SLEEP)
if not probe:
    print("無法取得基準日"); raise SystemExit
newest = max(r["date"] for r in probe)
print(f"最新財報季度: {newest}")

done = skipped = 0
for i, sid in enumerate(ids, 1):
    path = os.path.join(OUT_DIR, f"{sid}.csv")
    ld = last_date(path)
    if ld and ld >= newest:
        skipped += 1
        continue

    rows = fetch(sid, ld if ld else "2023-01-01")
    time.sleep(SLEEP)
    if not rows:
        continue

    new = pd.DataFrame(rows)
    if os.path.exists(path):
        try:
            new = pd.concat([pd.read_csv(path, dtype={"stock_id": str}), new], ignore_index=True)
        except Exception:
            pass
    new = new.drop_duplicates(subset=["date", "stock_id", "type"], keep="last").sort_values(["date", "type"])
    new.to_csv(path, index=False, encoding="utf-8-sig")
    done += 1
    if done % 50 == 0:
        print(f"  [{i}/{len(ids)}] 已更新 {done}")

print(f"\n更新 {done}，已最新跳過 {skipped}")