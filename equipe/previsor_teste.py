"""PREVISOR v0 — teste honesto: dá para prever se um ETF sobe nos próximos 5 dias?
Walk-forward anual (treina só com o passado, com embargo de 5 dias), regressão logística.
Mede: acerto geral, calibração (Brier) e PRECISÃO quando o modelo está muito confiante."""
import os, sys, numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "acoes"))
from yahoo import historico
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline

H = 5
ATIVOS = ["SPY", "QQQ", "IWM", "DIA", "XLK", "XLF", "XLE", "XLV", "SMH", "GLD", "TLT", "EFA", "EEM"]


def feats(c):
    r = c.pct_change()
    f = pd.DataFrame(index=c.index)
    for n in (5, 20, 60, 120):
        f[f"ret{n}"] = c.pct_change(n)
    f["dist200"] = c / c.rolling(200).mean() - 1
    f["dist50"] = c / c.rolling(50).mean() - 1
    f["vol20"] = r.rolling(20).std()
    f["vol_ratio"] = r.rolling(20).std() / r.rolling(120).std()
    for n in (20, 55, 120):
        f[f"don{n}"] = (c - c.rolling(n).min()) / (c.rolling(n).max() - c.rolling(n).min() + 1e-12)
    d = c.diff(); up = d.clip(lower=0).ewm(alpha=1 / 14).mean(); dn = (-d.clip(upper=0)).ewm(alpha=1 / 14).mean()
    f["rsi14"] = 100 - 100 / (1 + up / (dn + 1e-12))
    return f


linhas = []
for t in ATIVOS:
    c = historico(t, "max")["adj"]
    f = feats(c)
    f["y"] = (c.shift(-H) / c - 1 > 0).astype(float)
    f["fut"] = c.shift(-H) / c - 1
    f["ativo"] = t
    linhas.append(f.dropna())
D = pd.concat(linhas).sort_index()
X = [x for x in D.columns if x not in ("y", "fut", "ativo")]

prev = []
for ano in range(2012, 2027):
    ini = pd.Timestamp(f"{ano}-01-01")
    treino = D[D.index < ini - pd.Timedelta(days=H * 2)]  # embargo: não deixa o futuro vazar
    teste = D[(D.index >= ini) & (D.index < pd.Timestamp(f"{ano + 1}-01-01"))]
    if len(teste) == 0:
        continue
    m = make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=500)).fit(treino[X], treino["y"])
    p = m.predict_proba(teste[X])[:, 1]
    prev.append(teste.assign(p=p))
P = pd.concat(prev)

base = P["y"].mean()
acc = ((P["p"] > .5) == (P["y"] == 1)).mean()
brier = ((P["p"] - P["y"]) ** 2).mean()
brier_base = ((base - P["y"]) ** 2).mean()
print(f"Previsões fora da amostra: {len(P):,} (2012-2026, {len(ATIVOS)} ETFs, horizonte {H} dias)")
print(f"Sobe em {base:.1%} das vezes (só 'chutar alta' acerta isso) | acerto do modelo {acc:.1%}")
print(f"Brier modelo {brier:.4f} vs chute constante {brier_base:.4f} (menor = melhor)\n")
print("Quando o modelo está CONFIANTE (abstém nos outros casos):")
for lim in (.55, .60, .65, .70, .75, .80):
    s = P[P["p"] >= lim]
    if len(s) < 30:
        print(f"  P(alta) >= {lim:.2f}: poucos casos ({len(s)})"); continue
    print(f"  P(alta) >= {lim:.2f}: acerta {s['y'].mean():.1%} | erra {1 - s['y'].mean():.1%} | usa {len(s) / len(P):.1%} dos dias | retorno médio 5d {s['fut'].mean():+.2%}")
print("\nCalibração (diz X% → acontece Y%):")
P["faixa"] = pd.cut(P["p"], [0, .4, .5, .55, .6, .65, .7, 1])
print(P.groupby("faixa", observed=True)["y"].agg(["mean", "count"]).rename(columns={"mean": "aconteceu", "count": "casos"}).round(3).to_string())
