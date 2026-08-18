import pandas as pd
import os
import glob
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REV_DIR = os.path.join(BASE_DIR, "revenue_data")
FIN_DIR = os.path.join(BASE_DIR, "fin_data")
OUT_DIR = os.path.join(BASE_DIR, "fundamentals")

os.makedirs(OUT_DIR, exist_ok=True)

ids = [os.path.basename(f).replace(".csv", "")
       for f in glob.glob(os.path.join(REV_DIR, "*.csv"))]
print("待處理:", len(ids))

done = 0
for sid in ids:
    out = {"revenue": [], "fin": []}

    rev_path = os.path.join(REV_DIR, f"{sid}.csv")
    if os.path.exists(rev_path):
        try:
            df = pd.read_csv(rev_path)
            if not df.empty and "revenue" in df.columns:
                df = df.sort_values(["revenue_year", "revenue_month"]).drop_duplicates(
                    subset=["revenue_year", "revenue_month"], keep="last")
                df = df.reset_index(drop=True)

                # 算年增率：本月營收 vs 去年同月營收
                lookup = {(int(r.revenue_year), int(r.revenue_month)): r.revenue
                          for r in df.itertuples()}

                recent = df.tail(24)
                for r in recent.itertuples():
                    y, m = int(r.revenue_year), int(r.revenue_month)
                    last_year_rev = lookup.get((y - 1, m))
                    yoy = None
                    if last_year_rev and last_year_rev > 0:
                        yoy = round((r.revenue - last_year_rev) / last_year_rev * 100, 2)
                    out["revenue"].append({
                        "y": y, "m": m,
                        "rev": float(r.revenue),
                        "yoy": yoy,
                    })
        except Exception:
            pass

    fin_path = os.path.join(FIN_DIR, f"{sid}.csv")
    if os.path.exists(fin_path):
        try:
            df = pd.read_csv(fin_path)
            if not df.empty and "type" in df.columns:
                df["date"] = pd.to_datetime(df["date"])
                piv = df.pivot_table(index="date", columns="type", values="value", aggfunc="last")
                piv = piv.sort_index().tail(12)
                for dt, row in piv.iterrows():
                    rev = row.get("Revenue", None)
                    gp = row.get("GrossProfit", None)
                    op = row.get("OperatingIncome", None)
                    gm = round(gp / rev * 100, 2) if pd.notna(rev) and pd.notna(gp) and rev != 0 else None
                    om = round(op / rev * 100, 2) if pd.notna(rev) and pd.notna(op) and rev != 0 else None
                    out["fin"].append({
                        "date": dt.strftime("%Y-%m-%d"),
                        "gross_margin": gm,
                        "op_margin": om,
                    })
        except Exception:
            pass

    if out["revenue"] or out["fin"]:
        with open(os.path.join(OUT_DIR, f"{sid}.json"), "w") as fp:
            json.dump(out, fp, separators=(",", ":"))
        done += 1

print(f"完成 {done} 檔")