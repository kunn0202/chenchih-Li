import pandas as pd, requests
from io import StringIO

UA = {"User-Agent": "Mozilla/5.0"}
YEAR, MONTH = 115, 7

for kind in ["sii", "otc"]:
    url = f"https://mopsov.twse.com.tw/nas/t21/{kind}/t21sc03_{YEAR}_{MONTH}_0.html"
    try:
        r = requests.get(url, headers=UA, timeout=30)
        r.encoding = "big5"
        tables = pd.read_html(StringIO(r.text))
        big = max(tables, key=len)
        print(f"\n=== {kind}：{len(tables)} 個表格，最大表 {len(big)} 列 ===")
        print("欄位:", list(big.columns))
        print(big.head(3).to_string()[:800])
    except Exception as e:
        print(f"{kind} 失敗: {type(e).__name__}: {e}")