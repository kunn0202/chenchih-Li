import requests, pandas as pd, os, io, glob, ssl, time
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "stock_data")
OUT_DIR  = os.path.join(BASE_DIR, "tdcc_data")
URL = "https://opendata.tdcc.com.tw/getOD.ashx?id=1-5"
UA = {"User-Agent": "Mozilla/5.0"}

# 持股分級：12=400,001-600,000 / 13=600,001-800,000
#           14=800,001-1,000,000 / 15=1,000,001以上  → 400張以上大戶
BIG_LV = {12, 13, 14, 15}
# 1=1-999 / 2=1,000-5,000 → 5張以下散戶
SML_LV = {1, 2}


class LaxAdapter(HTTPAdapter):
    def init_poolmanager(self, *a, **kw):
        ctx = create_urllib3_context()
        ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
        kw["ssl_context"] = ctx
        return super().init_poolmanager(*a, **kw)


SESSION = requests.Session()
SESSION.mount("https://", LaxAdapter())
os.makedirs(OUT_DIR, exist_ok=True)


def fetch():
    for att in range(3):
        try:
            r = SESSION.get(URL, headers=UA, timeout=180)
            r.encoding = "utf-8-sig"
            return pd.read_csv(io.StringIO(r.text), dtype=str)
        except Exception as e:
            print(f"  重試 {att+1}/3: {type(e).__name__}")
            time.sleep(10)
    return None


# 只處理有股價資料的股票，避免產生一堆公債/權證檔案
valid = {os.path.basename(f)[:-4]
         for f in glob.glob(os.path.join(DATA_DIR, "*.csv"))}
print(f"股票清單: {len(valid)} 檔")

df = fetch()
if df is None or df.empty:
    print("下載失敗")
    raise SystemExit

df.columns = [c.strip() for c in df.columns]
date_col = df.columns[0]

# 官方偶爾會用「佔」而非「占」
pct_col = next((c for c in df.columns if "集保庫存數比例" in c), None)
if pct_col is None or "證券代號" not in df.columns or "持股分級" not in df.columns:
    print("警告：集保欄位名稱有變，跳過")
    print("實際欄位:", list(df.columns))
    raise SystemExit

iso = datetime.strptime(str(df[date_col].iloc[0]).strip(),
                        "%Y%m%d").strftime("%Y-%m-%d")
print(f"資料日期: {iso}")

df["sid"] = df["證券代號"].astype(str).str.strip()
df = df[df["sid"].isin(valid)]
df["lv"] = pd.to_numeric(df["持股分級"], errors="coerce")
df["pct"] = pd.to_numeric(df[pct_col], errors="coerce").fillna(0)

big = df[df["lv"].isin(BIG_LV)].groupby("sid")["pct"].sum()
sml = df[df["lv"].isin(SML_LV)].groupby("sid")["pct"].sum()

updated = 0
for sid in big.index:
    row = pd.DataFrame([{
        "date": iso,
        "big": round(float(big.get(sid, 0)), 2),
        "sml": round(float(sml.get(sid, 0)), 2),
    }])
    path = os.path.join(OUT_DIR, f"{sid}.csv")
    if os.path.exists(path):
        old = pd.read_csv(path)
        row = pd.concat([old, row], ignore_index=True)
    row = row.drop_duplicates(subset=["date"], keep="last").sort_values("date")
    row.to_csv(path, index=False, encoding="utf-8-sig")
    updated += 1

print(f"\n更新 {updated} 檔 → {OUT_DIR}")