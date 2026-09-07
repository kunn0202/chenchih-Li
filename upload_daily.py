import os, glob, json, re, subprocess
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DAILY_DIR = os.path.join(BASE_DIR, "daily")
KEEP_DAYS = 90

os.makedirs(DAILY_DIR, exist_ok=True)

# 收集所有 YYYY-MM-DD.(png|jpg|jpeg|webp) 檔案
pat = re.compile(r"^(\d{4}-\d{2}-\d{2})\.(png|jpg|jpeg|webp)$", re.I)
items = []
for p in glob.glob(os.path.join(DAILY_DIR, "*")):
    name = os.path.basename(p)
    m = pat.match(name)
    if m:
        items.append((m.group(1), name))

if not items:
    print("daily 資料夾裡沒有圖片")
    print("檔名要像 2026-09-08.png 這樣")
    raise SystemExit

items.sort(reverse=True)

# 刪除超過保留天數的舊圖
cutoff = (datetime.now() - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
removed = 0
keep = []
for d, name in items:
    if d < cutoff:
        try:
            os.remove(os.path.join(DAILY_DIR, name))
            removed += 1
        except Exception:
            pass
    else:
        keep.append({"date": d, "file": name})

# 寫索引檔
with open(os.path.join(DAILY_DIR, "index.json"), "w", encoding="utf-8") as fp:
    json.dump({"updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
               "items": keep}, fp, ensure_ascii=False, separators=(",", ":"))

print(f"共 {len(keep)} 張，最新 {keep[0]['date']}")
if removed:
    print(f"清除 {removed} 張超過 {KEEP_DAYS} 天的舊圖")

# 推上 GitHub
def run(cmd):
    r = subprocess.run(cmd, shell=True, cwd=BASE_DIR,
                       capture_output=True, text=True, encoding="utf-8", errors="ignore")
    return r.returncode, (r.stdout or "") + (r.stderr or "")

print("\n上傳中…")
run("git pull --no-rebase -X ours")
run("git add -A")
code, out = run(f'git commit -m "盤前分析 {keep[0]["date"]}"')
if "nothing to commit" in out:
    print("沒有新的變更")
    raise SystemExit
code, out = run("git push")
if code == 0:
    print("完成，2 分鐘後就能在網站上看到")
else:
    print("推送失敗：")
    print(out[-500:])
