"""Testa se o índice de Medo/Ganância melhora o robô (dados diários desde 2018)."""
import requests, numpy as np, pandas as pd
from testador import carregar, metricas, corta
from testador_ls import rodar, vol_ajuste, donch_ls

fng = requests.get("https://api.alternative.me/fng/?limit=0", timeout=30).json()["data"]
fng = pd.Series({pd.Timestamp(int(d["timestamp"]), unit="s", tz="UTC"): int(d["value"]) for d in fng}).sort_index()
fng.to_csv("data/medo_ganancia.csv")

dados = carregar()
res = []
for nome, regra in {
    "Rompimento puro": lambda p, f: p,
    "sem vender no medo extremo": lambda p, f: p.where(~((p < 0) & (f < 20)), 0),
    "sem comprar na ganância extrema": lambda p, f: p.where(~((p > 0) & (f > 80)), 0),
    "os dois filtros": lambda p, f: p.where(~(((p < 0) & (f < 20)) | ((p > 0) & (f > 80))), 0),
    "contrário: compra medo<15, sai >50": None,
}.items():
    eqs = []
    for s, df in dados.items():
        f = fng.reindex(df.index, method="ffill").shift(6)  # só usa o valor do dia anterior
        if regra is None:
            pos = pd.Series(np.nan, index=df.index)
            pos[f < 15] = 1
            pos[f > 50] = 0
            pos = pos.ffill().fillna(0)
        else:
            pos = regra(donch_ls(df, 120), f)
        eqs.append(rodar(df.c, vol_ajuste(df.c, pos, 0.5)))
    eq = (1 + pd.concat(eqs, axis=1).ffill().pct_change().mean(axis=1).fillna(0)).cumprod()
    t, p = metricas(corta(eq, False)), metricas(corta(eq, True))
    res.append(dict(regra=nome, treino_cagr=t["cagr"], treino_dd=t["dd"], prova_cagr=p["cagr"],
                    prova_dd=p["dd"], prova_sharpe=p["sharpe"]))
print(pd.DataFrame(res).round(3).to_string(index=False))
