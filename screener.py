import pandas as pd
import numpy as np
import os
import glob
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "stock_data")
INST_DIR = os.path.join(BASE_DIR, "inst_data")
SHARE_DIR = os.path.join(BASE_DIR, "share_data")

files = glob.glob(os.path.join(DATA_DIR, "*.csv"))
print("讀取檔案數:", len(files))

info = pd.read_csv(os.path.join(BASE_DIR, "stock_list.csv"), dtype={"stock_id": str})
names = info.set_index("stock_id")["stock_name"].to_dict()
inds = info.set_index("stock_id")["industry_category"].to_dict()

def get_inst_flags(sid):
    """回傳 (外資買超, 投信買超)"""
    path = os.path.join(INST_DIR, f"{sid}.csv")
    if not os.path.exists(path):
        return False, False
    try:
        df = pd.read_csv(path)
    except Exception:
        return False, False
    if df.empty or "date" not in df.columns:
        return False, False
    last_date = df["date"].max()
    today = df[df["date"] == last_date]

    foreign = today[today["name"] == "Foreign_Investor"]
    trust = today[today["name"] == "Investment_Trust"]

    f_buy = bool(len(foreign) and (foreign["buy"].sum() - foreign["sell"].sum()) > 0)
    t_buy = bool(len(trust) and (trust["buy"].sum() - trust["sell"].sum()) > 0)
    return f_buy, t_buy

def get_foreign_high(sid):
    """外資持股比例是否為近一季(60個交易日)新高"""
    path = os.path.join(SHARE_DIR, f"{sid}.csv")
    if not os.path.exists(path):
        return False
    try:
        df = pd.read_csv(path)
    except Exception:
        return False
    if df.empty or "ForeignInvestmentSharesRatio" not in df.columns:
        return False
    df = df.sort_values("date")
    ratio = df["ForeignInvestmentSharesRatio"].dropna()
    if len(ratio) < 5:
        return False
    recent = ratio.tail(60)
    return bool(ratio.iloc[-1] >= recent.max())

results = []

for f in files:
    sid = os.path.basename(f).replace(".csv", "")
    df = pd.read_csv(f)
    if len(df) < 210:
        continue

    df = df.sort_values("date").reset_index(drop=True)
    df = df[df["close"] > 0].reset_index(drop=True)
    if len(df) < 210:
        continue

    close = df["close"]
    last = close.iloc[-1]

    ma5 = close.rolling(5).mean()
    ma10 = close.rolling(10).mean()
    ma24 = close.rolling(24).mean()
    ma72 = close.rolling(72).mean()
    ma200 = close.rolling(200).mean()

    c3 = ma5.iloc[-1] > ma10.iloc[-1] > ma24.iloc[-1]
    c4 = ma24.iloc[-1] > ma72.iloc[-1] > ma200.iloc[-1]

    d5 = last > close.iloc[-6]
    d10 = last > close.iloc[-11]
    d24 = last > close.iloc[-25]
    d72 = last > close.iloc[-73]

    cross = bool(ma5.iloc[-2] <= ma24.iloc[-2] and ma5.iloc[-1] > ma24.iloc[-1])

    df["date"] = pd.to_datetime(df["date"])
    last_date = df["date"].iloc[-1]

    prev_month = (last_date.replace(day=1) - pd.Timedelta(days=1)).to_period("M")
    pm = df[df["date"].dt.to_period("M") == prev_month]
    pm_high = pm["max"].max() if len(pm) else np.nan
    c2 = bool(len(pm) > 0 and last >= pm_high * 0.95)
    over_month = bool(len(pm) > 0 and last > pm_high)

    this_monday = last_date - pd.Timedelta(days=last_date.weekday())
    prev_monday = this_monday - pd.Timedelta(days=7)
    prev_friday = this_monday - pd.Timedelta(days=3)
    pw = df[(df["date"] >= prev_monday) & (df["date"] <= prev_friday)]
    pw_high = pw["max"].max() if len(pw) else np.nan
    over_week = bool(len(pw) > 0 and last > pw_high)

    vol20 = df["Trading_Volume"].tail(20).mean() / 1000

    def ret(n1, n2):
        if len(close) <= n2:
            return np.nan
        a, b = close.iloc[-n2 - 1], close.iloc[-n1 - 1]
        return (b - a) / a if a > 0 else np.nan

    rs_raw = (0.4 * ret(0, 63) + 0.2 * ret(63, 126)
              + 0.2 * ret(126, 189) + 0.2 * ret(189, 252))

    foreign_buy, trust_buy = get_inst_flags(sid)
    foreign_high = get_foreign_high(sid)

    results.append({
        "stock_id": sid,
        "stock_name": names.get(sid, ""),
        "industry": inds.get(sid, ""),
        "close": round(float(last), 2),
        "vol20": round(float(vol20), 1),
        "rs_raw": rs_raw,
        "c2": c2,
        "c3": bool(c3),
        "c4": bool(c4),
        "d5": bool(d5),
        "d10": bool(d10),
        "d24": bool(d24),
        "d72": bool(d72),
        "over_month": over_month,
        "over_week": over_week,
        "cross": cross,
        "foreign_buy": foreign_buy,
        "trust_buy": trust_buy,
        "foreign_high": foreign_high,
    })

res = pd.DataFrame(results).dropna(subset=["rs_raw"])
print("有效檔數:", len(res))

res["rs_score"] = (res["rs_raw"].rank(pct=True) * 100).round(1)
res["c1"] = res["rs_score"] > 90
res = res.drop(columns=["rs_raw"]).sort_values("rs_score", ascending=False)

data_date = str(last_date.date())
out = {"updated": data_date, "count": len(res), "stocks": res.to_dict(orient="records")}

json_path = os.path.join(BASE_DIR, "screener_data.json")
with open(json_path, "w", encoding="utf-8") as fp:
    json.dump(out, fp, ensure_ascii=False, separators=(",", ":"))

print(f"已輸出 {json_path}  ({os.path.getsize(json_path)/1024:.0f} KB)")

cols = ["c1", "c2", "c3", "c4", "d5", "d10", "d24", "d72",
        "over_month", "over_week", "cross",
        "foreign_buy", "trust_buy", "foreign_high"]
print("\n各條件符合檔數:")
for c in cols:
    print(f"  {c}: {res[c].sum()}")