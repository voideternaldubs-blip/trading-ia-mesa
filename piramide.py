"""Piramidação estilo Tartarugas sobre o rompimento: 1 unidade na entrada, +1 a cada +0,5/1 ATR a favor (máx N),
stop de todas as unidades a 2 ATR da última entrada; saída também no canal contrário de n/2."""
import numpy as np, pandas as pd
from motores import carregar, escala, simular, vol, met, PER

def atr(H, L, C, n=20*6):
    tr = pd.concat([H - L, (H - C.shift()).abs(), (L - C.shift()).abs()]).groupby(level=0).max()
    return tr.reindex(C.index).rolling(n).mean()

def piramide(C, H, L, n=120, passo=1.0, maxu=4, stop_atr=2.0):
    A = atr(H, L, C)
    hi, lo = H.rolling(n).max().shift(1), L.rolling(n).min().shift(1)
    hs, ls = H.rolling(n // 2).max().shift(1), L.rolling(n // 2).min().shift(1)
    out = pd.DataFrame(0.0, index=C.index, columns=C.columns)
    for m in C.columns:
        c, a, h1, l1, h2, l2 = (x[m].values for x in (C, A, hi, lo, hs, ls))
        u = 0; lado = 0; ult = 0.0; stop = 0.0; res = np.zeros(len(c))
        for i in range(len(c)):
            if np.isnan(c[i]) or np.isnan(a[i]) or np.isnan(h1[i]):
                res[i] = 0; continue
            if lado == 0:
                if c[i] > h1[i]: lado, u, ult = 1, 1, c[i]
                elif c[i] < l1[i]: lado, u, ult = -1, 1, c[i]
                stop = ult - lado * stop_atr * a[i]
            else:
                sair = (lado == 1 and (c[i] < l2[i] or c[i] < stop)) or (lado == -1 and (c[i] > h2[i] or c[i] > stop))
                if sair:
                    lado, u = 0, 0
                elif u < maxu and lado * (c[i] - ult) >= passo * a[i]:
                    u += 1; ult = c[i]; stop = ult - lado * stop_atr * a[i]
            res[i] = lado * u / maxu
        out[m] = res
    return out / vol(C) / C.notna().sum(axis=1).values[:, None]

if __name__ == "__main__":
    import warnings; warnings.filterwarnings("ignore")
    C, H, L, Q, FU = carregar()
    from motores import m_tendencia
    base = escala(sum(m_tendencia(C, H, L, n) for n in [80, 120, 200]) / 3, C, 0.30)
    rb = simular(base, C, FU)
    print("BASE ensemble       ", {p: round(met(rb, *PER[p])["sharpe"], 2) for p in PER})
    for passo, maxu in [(0.5, 4), (1.0, 4), (1.0, 6)]:
        W = escala(sum(piramide(C, H, L, n, passo, maxu) for n in [80, 120, 200]) / 3, C, 0.30)
        r = simular(W, C, FU); r2 = simular(W, C, FU, 0.002)
        rr = {p: met(r, *PER[p]) for p in PER}
        print(f"PIRÂMIDE passo {passo} ATR máx {maxu}", {p: round(v["sharpe"], 2) for p, v in rr.items()},
              "| prova CAGR", round(rr["prova"]["cagr"], 2), "DD", round(rr["prova"]["dd"], 2), "| custo2x", round(met(r2, *PER["prova"])["sharpe"], 2),
              "| assimetria diária", round(r.resample("1D").sum().skew(), 2), "vs base", round(rb.resample("1D").sum().skew(), 2))
        r.to_csv(f"serie_piramide_{passo}_{maxu}.csv")
