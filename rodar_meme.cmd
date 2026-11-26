@echo off
cd /d C:\Users\Administrator\trading-ia
set PYTHONIOENCODING=utf-8
set MODO=rigoroso
python atirador.py >> data\meme_rigoroso.log 2>&1
set MODO=solto
python atirador.py >> data\meme_solto.log 2>&1
cd /d C:\Users\Administrator\trading-ia
python central.py >> data\central.log 2>&1
