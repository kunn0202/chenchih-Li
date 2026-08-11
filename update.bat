@echo off
chcp 65001 >nul
cd /d D:\stock_system

echo ===== 1/4 抓取原始資料 =====
python backfill_all.py
if errorlevel 1 goto fail

echo ===== 2/4 執行選股 =====
python screener.py
if errorlevel 1 goto fail

echo ===== 3/4 匯出圖表 =====
python export_charts.py
if errorlevel 1 goto fail

echo ===== 4/4 匯出財報 =====
python export_fundamentals.py
if errorlevel 1 goto fail

echo ===== 上傳 GitHub =====
git add .
git commit -m "資料更新 %date%"
git push

echo.
echo ===== 完成 =====
pause
exit

:fail
echo.
echo ===== 中途失敗，沒有上傳 =====
pause