"""Testa estratégias em histórico real com taxa + escorregão.
Divide o tempo em 2 partes: TREINO (escolhe parâmetro) e PROVA (dados que a estratégia nunca viu).
Só vale o resultado da PROVA."""
import os, glob, itertools, numpy as np, pandas as pd

PASTA = os.path.join(os.path.dirname(__file__), "data")
CUSTO = 0.001 + 0.0005  # taxa 0,1% + escorregão 0,05% por lado
BARRAS_ANO = 6 * 365     # velas de 4h
CORTE = "2025-01-01"     # antes = treino, depois = prova


def carregar():
    d = {}
    for f in glob.glob(os.path.join(PASTA, "*_4h.csv")):
        s = os.path.basename(f).split("_")[0]
        d[s] = pd.read_csv(f, index_col=0, parse_dates=True)
    return d


def metricas(eq):
    eq = eq.dropna()
    if len(eq) < 10:
        return dict(cagr=np.nan, dd=np.nan, sharpe=np.nan, final=np.nan)
    r = eq.pct_change().fillna(0)
    anos = len(eq) / BARRAS_ANO
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / anos) - 1
    dd = (eq / eq.cummax() - 1).min()
    sh = r.mean() / (r.std() + 1e-12) * np.sqrt(BARRAS_ANO)
    return dict(cagr=cagr, dd=dd, sharpe=sh, final=eq.iloc[-1] / eq.iloc[0])


def rodar_posicao(c, pos):
    """pos = exposição (0..1) decidida no FECHAMENTO da vela; executa na próxima."""
    pos = pos.shift(1).fillna(0)
    r = c.pct_change().fillna(0)
    giro = pos.diff().abs().fillna(0)
    return (1 + pos * r - giro * CUSTO).cumprod()


# ---------- estratégias de 1 moeda ----------
def ema_cross(df, f, s):
    c = df.c
    return (c.ewm(span=f).mean() > c.ewm(span=s).mean()).astype(float)


def donchian(df, n, m):
    """Rompimento (tartaruga): compra na máxima de n velas, sai na mínima de m."""
    hi = df.h.rolling(n).max().shift(1)
    lo = df.l.rolling(m).min().shift(1)
    pos = pd.Series(np.nan, index=df.index)
    pos[df.c > hi] = 1
    pos[df.c < lo] = 0
    return pos.ffill().fillna(0)


def rsi_rev(df, n, entra, filtro):
    c = df.c
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n).mean()
    rsi = 100 - 100 / (1 + up / (dn + 1e-12))
    tend = c > c.rolling(filtro).mean()
    pos = pd.Series(np.nan, index=df.index)
    pos[(rsi < entra) & tend] = 1
    pos[rsi > 60] = 0
    pos[~tend] = 0
    return pos.ffill().fillna(0)


def vol_alvo(df, pos, alvo=0.6):
    """Ajusta o tamanho pela volatilidade (agente RISCO)."""
    vol = df.c.pct_change().rolling(42).std() * np.sqrt(BARRAS_ANO)
    return (pos * (alvo / vol).clip(upper=1)).fillna(0)


# ---------- carteira: rotação por força (momentum) ----------
def rotacao(dados, look, topn, filtro_btc):
    close = pd.DataFrame({s: d.c for s, d in dados.items()}).dropna(how="all")
    mom = close.pct_change(look)
    btc_ok = close["BTC"] > close["BTC"].rolling(filtro_btc).mean()
    rank = mom.rank(axis=1, ascending=False)
    w = ((rank <= topn) & (mom > 0)).astype(float)
    w = w.div(topn)
    w[~btc_ok] = 0
    # rebalanceia 1x por dia (a cada 6 velas)
    w = w.iloc[::6].reindex(close.index).ffill().fillna(0)
    w = w.shift(1).fillna(0)
    r = close.pct_change().fillna(0)
    giro = w.diff().abs().sum(axis=1).fillna(0)
    return (1 + (w * r).sum(axis=1) - giro * CUSTO).cumprod()


def corta(eq, prova):
    eq = eq[eq.index >= CORTE] if prova else eq[eq.index < CORTE]
    return eq / eq.iloc[0]


def main():
    dados = carregar()
    linhas = []
    grades = {
        "EMA": (ema_cross, list(itertools.product([10, 20, 50], [100, 200, 300]))),
        "Rompimento": (donchian, list(itertools.product([20, 55, 120], [10, 20, 55]))),
        "RSI_volta": (rsi_rev, list(itertools.product([14], [25, 30, 35], [200, 600]))),
    }
    for s, df in dados.items():
        bh = df.c / df.c.iloc[0]
        linhas.append(dict(estrat="Segurar (comparação)", moeda=s, param="-",
                           **{"treino_" + k: v for k, v in metricas(corta(bh, False)).items()},
                           **{"prova_" + k: v for k, v in metricas(corta(bh, True)).items()}))
        for nome, (fn, grade) in grades.items():
            for usa_vol in (False, True):
                melhor = None
                for p in grade:
                    pos = fn(df, *p)
                    if usa_vol:
                        pos = vol_alvo(df, pos)
                    eq = rodar_posicao(df.c, pos)
                    mt = metricas(corta(eq, False))
                    if melhor is None or (mt["sharpe"] > melhor[1]["sharpe"]):
                        melhor = (p, mt, eq)
                p, mt, eq = melhor
                linhas.append(dict(estrat=nome + ("+vol" if usa_vol else ""), moeda=s, param=str(p),
                                   **{"treino_" + k: v for k, v in mt.items()},
                                   **{"prova_" + k: v for k, v in metricas(corta(eq, True)).items()}))
    # carteira
    melhor = None
    for look, topn, fb in itertools.product([42, 126, 180], [1, 2, 3], [120, 300]):
        eq = rotacao(dados, look, topn, fb)
        mt = metricas(corta(eq, False))
        if melhor is None or mt["sharpe"] > melhor[1]["sharpe"]:
            melhor = ((look, topn, fb), mt, eq)
    p, mt, eq = melhor
    linhas.append(dict(estrat="Rotação carteira", moeda="10 moedas", param=str(p),
                       **{"treino_" + k: v for k, v in mt.items()},
                       **{"prova_" + k: v for k, v in metricas(corta(eq, True)).items()}))
    res = pd.DataFrame(linhas)
    res.to_csv(os.path.join(os.path.dirname(__file__), "resultado.csv"), index=False)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 200)
    cols = ["estrat", "moeda", "param", "treino_cagr", "treino_dd", "prova_cagr", "prova_dd", "prova_sharpe", "prova_final"]
    print(res[cols].round(2).to_string(index=False))
    print("\nMÉDIA NA PROVA por estratégia:")
    print(res.groupby("estrat")[["prova_cagr", "prova_dd", "prova_sharpe"]].mean().round(2).sort_values("prova_sharpe", ascending=False))


if __name__ == "__main__":
    main()
