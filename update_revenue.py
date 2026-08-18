import pandas as pd, requests, os, time
from io import StringIO
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE_DIR, "revenue_data")
UA = {"User-Agent": "Mozilla/5.0"}
BACK_MONTHS = 3          # 往回檢查最近幾個月

os.makedirs(OUT_DIR, exist_ok=True)

def fetch_month(year_roc, month):
    """回傳 {stock_id: 當月營收(元)}"""
    out = {}
    for kind in ["sii", "otc"]:
        url = (f"https://mopsov.twse.com.tw/nas/t21/{kind}/"
               f"t21sc03_{year_roc}_{month}_0.html")
        try:
            r = requests.get(url, headers=UA, timeout=30)
            if r.status_code != 200:
                print(f"    {kind} 狀態碼 {r.status_code}")
                continue
            r.encoding = "big5"
            tables = pd.read_html(StringIO(r.text))
        except Exception as e:
            print(f"    {kind} 失敗: {type(e).__name__}")
            continue

        for t in tables:
            cols = [str(c[-1]) if isinstance(c, tuple) else str(c) for c in t.columns]
            if "公司 代號" not in cols or "當月營收" not in cols:
                continue
            t.columns = cols
            for _, row in t.iterrows():
                sid = str(row["公司 代號"]).strip()
                if not sid.isdigit():
                    continue
                try:
                    rev = float(str(row["當月營收"]).replace(",", "")) * 1000
                except Exception:
                    continue
                out[sid] = rev
        time.sleep(3)
    return out


def roc_ym(dt):
    return dt.year - 1911, dt.month


today = datetime.now()
targets = []
y, m = today.year, today.month
for _ in range(BACK_MONTHS):
    m -= 1
    if m == 0:
        m = 12
        y -= 1
    targets.append((y, m))
targets.reverse()

buf = {}
for y, m in targets:
    print(f"抓取 {y}/{m:02d} 營收…")
    data = fetch_month(y - 1911, m)
    print(f"  取得 {len(data)} 檔")
    if not data:
        continue
    # FinMind 格式：date = 公布月份的 1 號（營收月 + 1）
    py, pm = (y + 1, 1) if m == 12 else (y, m + 1)
    iso = f"{py:04d}-{pm:02d}-01"
    for sid, rev in data.items():
        buf.setdefault(sid, []).append({
            "date": iso, "stock_id": sid, "country": "Taiwan",
            "revenue": int(rev), "revenue_month": m, "revenue_year": y,
        })

updated = 0
for sid, recs in buf.items():
    path = os.path.join(OUT_DIR, f"{sid}.csv")
    if not os.path.exists(path):
        continue
    try:
        old = pd.read_csv(path, dtype={"stock_id": str})
    except Exception:
        continue
    df = pd.concat([old, pd.DataFrame(recs)], ignore_index=True)
    df = df.drop_duplicates(subset=["date", "stock_id"], keep="last").sort_values("date")
    df.to_csv(path, index=False, encoding="utf-8-sig")
    updated += 1

print(f"\n更新 {updated} 檔")