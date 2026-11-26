"""Versão comprado + vendido (futuros perpétuos). Mesmo rigor: treino até 2025, prova depois.
Custo extra: taxa de financiamento média aproximada de 0,01% a cada 8h (~0,0033% por vela de 4h) sobre a posição."""
import itertools, numpy as np, pandas as pd
from testador import carregar, metricas, corta, CUSTO, BARRAS_ANO

FUND = 0.0001 / 2  # por vela de 4h (aprox.)


def rodar(c, pos):
    pos = pos.shift(1).fillna(0)
    r = c.pct_change().fillna(0)
    giro = pos.diff().abs().fillna(0)
    return (1 + pos * r - giro * CUSTO - pos.abs() * FUND).cumprod()


def vol_ajuste(c, pos, alvo):
    vol = c.pct_change().rolling(42).std() * np.sqrt(BARRAS_ANO)
    return (pos * (alvo / vol).clip(upper=1)).fillna(0)


def ema_ls(df, f, s):
    c = df.c
    return np.sign(c.ewm(span=f).mean() - c.ewm(span=s).mean())


def donch_ls(df, n):
    hi = df.h.rolling(n).max().shift(1)
    lo = df.l.rolling(n).min().shift(1)
    mid = (hi + lo) / 2
    pos = pd.Series(np.nan, index=df.index)
    pos[df.c > hi] = 1
    pos[df.c < lo] = -1
    # sai quando cruza o meio do canal
    sair = ((pos.ffill() == 1) & (df.c < mid)) | ((pos.ffill() == -1) & (df.c > mid))
    pos[sair & pos.isna()] = 0
    return pos.ffill().fillna(0)


def tsmom(df, look):
    """Momentum de série temporal: sinal do retorno das últimas N velas."""
    return np.sign(df.c.pct_change(look)).fillna(0)


def main():
    dados = carregar()
    grades = {
        "EMA_ls": (ema_ls, list(itertools.product([10, 20, 50], [100, 200, 300]))),
        "Rompimento_ls": (donch_ls, [(n,) for n in [20, 55, 120, 240]]),
        "Momentum_ls": (tsmom, [(n,) for n in [42, 90, 180, 360]]),
    }
    linhas, curvas = [], {}
    for nome, (fn, grade) in grades.items():
        # escolhe UM parâmetro para todas as moedas (menos chance de sorte)
        melhor = None
        for p in grade:
            eqs = []
            for s, df in dados.items():
                eqs.append(rodar(df.c, vol_ajuste(df.c, fn(df, *p), 0.5)).rename(s))
            cart = pd.concat(eqs, axis=1).ffill().pct_change().mean(axis=1).fillna(0)
            eq = (1 + cart).cumprod()
            mt = metricas(corta(eq, False))
            if melhor is None or mt["sharpe"] > melhor[1]["sharpe"]:
                melhor = (p, mt, eq, eqs)
        p, mt, eq, eqs = melhor
        curvas[nome] = eq
        pr = metricas(corta(eq, True))
        linhas.append(dict(estrat=nome + " (carteira 10)", param=p, treino_cagr=mt["cagr"], treino_dd=mt["dd"],
                           prova_cagr=pr["cagr"], prova_dd=pr["dd"], prova_sharpe=pr["sharpe"], prova_final=pr["final"]))
        for e in eqs:
            pr = metricas(corta(e, True))
            linhas.append(dict(estrat="  " + nome, param=e.name, prova_cagr=pr["cagr"], prova_dd=pr["dd"],
                               prova_sharpe=pr["sharpe"], prova_final=pr["final"]))
    res = pd.DataFrame(linhas)
    pd.set_option("display.width", 250)
    print(res.round(2).to_string(index=False))
    pd.DataFrame(curvas).to_csv("curvas_ls.csv")


if __name__ == "__main__":
    main()
