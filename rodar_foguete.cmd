@echo off
cd /d C:\Users\Administrator\trading-ia
set PYTHONIOENCODING=utf-8
python foguete2.py >> data\foguete2.log 2>&1
python central.py >> data\central.log 2>&1
