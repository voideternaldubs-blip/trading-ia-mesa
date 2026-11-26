"""LABORATÓRIO DOS 3 MOTORES (futuros perpétuos, 30 moedas, financiamento REAL).
Períodos: TREINO 2021-2023 | VALIDAÇÃO 2024 | PROVA 2025+ (só olhar no fim).
Custo: 0,10%/lado (taxa taker 0,05% + escorregão 0,05%). Teste extra com custo 2x.
"""
import os, glob, sys, numpy as np, pandas as pd

AQUI = os.path.dirname(os.path.abspath(__file__))
FUT = os.path.join(AQUI, "data", "fut")
BA = 6 * 365
PER = {"treino": ("2021-01-01", "2024-01-01"), "valid": ("2024-01-01", "2025-01-01"), "prova": ("2025-01-01", "2030-01-01")}


def carregar():
    C, H, L, Q, FU = {}, {}, {}, {}, {}
    for f in glob.glob(os.path.join(FUT, "*_4h.csv")):
        s = os.path.basename(f)[:-7]
        d = pd.read_csv(f, index_col=0, parse_dates=True)
        C[s], H[s], L[s], Q[s] = d.c, d.h, d.l, d.q
        fu = pd.read_csv(os.path.join(FUT, s + "_fund.csv"), index_col=0, parse_dates=True).iloc[:, 0]
        # soma o financiamento pago dentro de cada vela de 4h
        FU[s] = fu.resample("4h", label="left", closed="left").sum()
    C = pd.DataFrame(C).sort_index()
    idx = C.index
    return C, pd.DataFrame(H).reindex(idx), pd.DataFrame(L).reindex(idx), pd.DataFrame(Q).reindex(idx), pd.DataFrame(FU).reindex(idx).fillna(0)


def simular(W, C, FU, custo=0.001):
    """W = pesos decididos no fechamento da vela t (executa na t+1). Positivo comprado, negativo vendido."""
    W = W.reindex(C.index).fillna(0).shift(1).fillna(0)
    r = C.pct_change(fill_method=None).fillna(0)
    giro = W.diff().abs().sum(axis=1).fillna(0)
    ret = (W * r).sum(axis=1) - giro * custo - (W * FU).sum(axis=1)
    return ret


def met(ret, ini, fim):
    r = ret[(ret.index >= ini) & (ret.index < fim)]
    if len(r) < 50:
        return dict(cagr=np.nan, dd=np.nan, sharpe=np.nan)
    eq = (1 + r).cumprod()
    return dict(cagr=eq.iloc[-1] ** (BA / len(r)) - 1, dd=(eq / eq.cummax() - 1).min(), sharpe=r.mean() / (r.std() + 1e-12) * np.sqrt(BA))


def vol(C, n=42):
    return C.pct_change(fill_method=None).rolling(n).std() * np.sqrt(BA)


def escala(W, C, alvo):
    """Ajusta a carteira inteira para volatilidade-alvo anual (agente RISCO)."""
    r = C.pct_change(fill_method=None).fillna(0)
    rp = (W.shift(1).fillna(0) * r).sum(axis=1)
    v = rp.rolling(126).std() * np.sqrt(BA)
    k = (alvo / v).clip(upper=3).shift(1).fillna(0)
    return W.mul(k, axis=0)


# ---------------- MOTOR 1: tendência (Donchian comprado/vendido) ----------------
def m_tendencia(C, H, L, n):
    hi, lo = H.rolling(n).max().shift(1), L.rolling(n).min().shift(1)
    mid = (hi + lo) / 2
    sig = pd.DataFrame(np.nan, index=C.index, columns=C.columns)
    sig[C > hi] = 1
    sig[C < lo] = -1
    s = sig.ffill()
    sig[(s == 1) & (C < mid) & sig.isna()] = 0
    sig[(s == -1) & (C > mid) & sig.isna()] = 0
    sig = sig.ffill().fillna(0)
    w = sig / vol(C)
    w = w.div(C.notna().sum(axis=1), axis=0)
    return w.where(C.notna(), 0).fillna(0)


# ---------------- MOTOR 2: momentum relativo L/S ----------------
def m_relativo(C, look_dias, pula_dias=1, k=3, reb=6):
    look, pula = look_dias * 6, pula_dias * 6
    mom = C.shift(pula) / C.shift(pula + look) - 1
    ok = C.notna() & mom.notna() & (C.notna().rolling(look + pula).sum() >= look + pula)
    mom = mom.where(ok)
    rk = mom.rank(axis=1)
    n = ok.sum(axis=1)
    longo = rk.gt(n - k, axis=0)
    curto = rk.le(k, axis=0)
    iv = 1 / vol(C)
    w = (longo * iv).div((longo * iv).sum(axis=1), axis=0).fillna(0) * 0.5 - (curto * iv).div((curto * iv).sum(axis=1), axis=0).fillna(0) * 0.5
    w[n < 2 * k + 2] = 0
    return w.iloc[::reb].reindex(C.index).ffill().fillna(0)


# ---------------- MOTOR 3: financiamento ----------------
def m_financiamento(C, FU, k=3, janela_dias=7, reb=6):
    """Contrário: vende as k com financiamento médio mais ALTO (multidão alavancada comprada),
    compra as k com financiamento mais BAIXO. Além do preço, recebe/paga o próprio financiamento."""
    f = FU.rolling(janela_dias * 6).sum()
    ok = C.notna() & (C.notna().rolling(janela_dias * 6).sum() >= janela_dias * 6)
    f = f.where(ok)
    rk = f.rank(axis=1)
    n = ok.sum(axis=1)
    alto = rk.gt(n - k, axis=0)
    baixo = rk.le(k, axis=0)
    iv = 1 / vol(C)
    w = (baixo * iv).div((baixo * iv).sum(axis=1), axis=0).fillna(0) * 0.5 - (alto * iv).div((alto * iv).sum(axis=1), axis=0).fillna(0) * 0.5
    w[n < 2 * k + 2] = 0
    return w.iloc[::reb].reindex(C.index).ffill().fillna(0)


def m_relativo_beta(C, look_dias=28, pula_dias=2, k_ent=3, k_sai=6, reb=6, beta_dias=60):
    """Spec Claude: resíduo por beta vs BTC + banda de histerese (entra top k_ent, sai fora do top k_sai)."""
    r = C.pct_change(fill_method=None)
    b = r["BTCUSDT"]
    bw = beta_dias * 6
    beta = r.rolling(bw, min_periods=bw // 2).cov(b).div(b.rolling(bw, min_periods=bw // 2).var(), axis=0)
    look, pula = look_dias * 6, pula_dias * 6
    ri = C.shift(pula) / C.shift(pula + look) - 1
    rb = ri["BTCUSDT"]
    res = ri - beta.mul(rb, axis=0)
    res = res.drop(columns="BTCUSDT")
    ok = res.notna()
    iv = 1 / vol(C).drop(columns="BTCUSDT")
    pos = pd.Series(0, index=res.columns, dtype=float)
    linhas = []
    idxs = res.index[::reb]
    for t in idxs:
        x = res.loc[t][ok.loc[t]]
        if len(x) < 2 * k_sai:
            pos[:] = 0; linhas.append(pos.copy()); continue
        rk_d = x.rank(ascending=False)  # 1 = mais forte
        rk_a = x.rank()                # 1 = mais fraca
        novo = pos.copy()
        for m in pos.index:
            if pos[m] > 0 and (m not in rk_d or rk_d[m] > k_sai): novo[m] = 0
            if pos[m] < 0 and (m not in rk_a or rk_a[m] > k_sai): novo[m] = 0
        for m in rk_d[rk_d <= k_ent].index: novo[m] = 1
        for m in rk_a[rk_a <= k_ent].index: novo[m] = -1
        pos = novo
        linhas.append(pos.copy())
    S = pd.DataFrame(linhas, index=idxs).reindex(C.index).ffill().fillna(0)
    lg = (S > 0) * iv; sh = (S < 0) * iv
    w = lg.div(lg.sum(axis=1), axis=0).fillna(0) * 0.5 - sh.div(sh.sum(axis=1), axis=0).fillna(0) * 0.5
    return w.reindex(columns=C.columns).fillna(0)


def m_tendencia_saida(C, H, L, n_ent=120, n_sai=60):
    """Spec do ChatGPT: entra no rompimento de n_ent, sai no canal de n_sai."""
    hi, lo = H.rolling(n_ent).max().shift(1), L.rolling(n_ent).min().shift(1)
    hs, ls = H.rolling(n_sai).max().shift(1), L.rolling(n_sai).min().shift(1)
    sig = pd.DataFrame(np.nan, index=C.index, columns=C.columns)
    sig[C > hi] = 1
    sig[C < lo] = -1
    s = sig.ffill()
    sig[(s == 1) & (C < ls) & sig.isna()] = 0
    sig[(s == -1) & (C > hs) & sig.isna()] = 0
    sig = sig.ffill().fillna(0)
    w = (sig / vol(C)).div(C.notna().sum(axis=1), axis=0)
    return w.where(C.notna(), 0).fillna(0)


def carry(C, FU, custo=0.001, max_pares=3, hold_max_dias=14):
    """MOTOR CARRY: comprado à vista + vendido no perpétuo (preço se anula), recebe o financiamento.
    Entra se financ. 7d > 0, > percentil 80 dos últimos 90d e metade dele > 2x o custo das 4 pernas.
    Sai se cair abaixo do p50 ou passar 14 dias. Retorno = financiamento recebido - custos (base ignorada)."""
    f7 = FU.rolling(42).sum()
    p80 = f7.rolling(540, min_periods=200).quantile(0.8)
    p50 = f7.rolling(540, min_periods=200).quantile(0.5)
    custo4 = 4 * custo
    ret = pd.Series(0.0, index=C.index)
    aberto = {}  # moeda -> vela de entrada
    idx = C.index
    for i in range(1, len(idx)):
        t = idx[i - 1]
        # recebe financiamento da vela atual nas posições abertas (vendido recebe f>0)
        if aberto:
            ret.iloc[i] += sum(FU.iloc[i][m] for m in aberto) / max_pares
        # saídas
        for m in list(aberto):
            if f7.at[t, m] < p50.at[t, m] or (i - aberto[m]) > hold_max_dias * 6:
                ret.iloc[i] -= (custo4 / 2) / max_pares
                del aberto[m]
        # entradas
        if len(aberto) < max_pares:
            cand = f7.loc[t][(f7.loc[t] > 0) & (f7.loc[t] > p80.loc[t]) & (0.5 * f7.loc[t] > 2 * custo4)]
            for m in cand.sort_values(ascending=False).index:
                if m in aberto or len(aberto) >= max_pares:
                    continue
                aberto[m] = i
                ret.iloc[i] -= (custo4 / 2) / max_pares
    return ret


def linha(nome, ret, ret2=None):
    d = {"motor": nome}
    for p, (a, b) in PER.items():
        m = met(ret, a, b)
        d[p + "_sharpe"], d[p + "_cagr"], d[p + "_dd"] = m["sharpe"], m["cagr"], m["dd"]
    if ret2 is not None:
        d["prova_sharpe_custo2x"] = met(ret2, *PER["prova"])["sharpe"]
    return d


def main():
    C, H, L, Q, FU = carregar()
    print("moedas:", C.shape[1], "| velas:", len(C), C.index[0].date(), "->", C.index[-1].date())
    linhas, series = [], {}
    ALVO = 0.30
    # Motor 1 com platô de parâmetros
    for n in [60, 80, 100, 120, 160, 200, 240]:
        W = escala(m_tendencia(C, H, L, n), C, ALVO)
        linhas.append(linha(f"1 tendência n={n}", simular(W, C, FU), simular(W, C, FU, 0.002)))
        if n == 120: series["tendencia"] = simular(W, C, FU)
    # Motor 2
    for look in [7, 14, 28]:
        for reb, nr in [(6, "diário"), (42, "semanal")]:
            W = escala(m_relativo(C, look, 1, 3, reb), C, ALVO)
            linhas.append(linha(f"2 relativo {look}d {nr}", simular(W, C, FU), simular(W, C, FU, 0.002)))
            if look == 14 and reb == 42: series["relativo"] = simular(W, C, FU)
    # Motor 3
    for jan in [3, 7, 14]:
        for reb, nr in [(6, "diário"), (42, "semanal")]:
            W = escala(m_financiamento(C, FU, 3, jan, reb), C, ALVO)
            linhas.append(linha(f"3 financ. {jan}d {nr}", simular(W, C, FU), simular(W, C, FU, 0.002)))
            if jan == 7 and reb == 42: series["financ"] = simular(W, C, FU)
    W = escala(m_tendencia_saida(C, H, L, 120, 60), C, ALVO)
    linhas.append(linha("1b tendência 120 / saída 60", simular(W, C, FU), simular(W, C, FU, 0.002)))
    for nm, mom_reb in [("2b relativo 28d semanal", (28, 1, 3, 42))]:
        W = escala(m_relativo(C, *mom_reb), C, ALVO)
        linhas.append(linha(nm, simular(W, C, FU), simular(W, C, FU, 0.002)))
    for nm, reb in [("2c relativo BETA 28d semanal", 42), ("2d relativo BETA 28d diário+banda", 6)]:
        W = escala(m_relativo_beta(C, reb=reb), C, ALVO)
        linhas.append(linha(nm, simular(W, C, FU), simular(W, C, FU, 0.002)))
        if reb == 6: series["relativo_beta"] = simular(W, C, FU)
    cr = carry(C, FU)
    linhas.append(linha("4 CARRY financiamento (neutro)", cr, carry(C, FU, 0.002)))
    series["carry"] = cr
    # Carteira: 1/3 de risco em cada
    S = pd.DataFrame(series).fillna(0)
    linhas.append(linha("CARTEIRA 3 motores (1/3 cada)", S.mean(axis=1)))
    res = pd.DataFrame(linhas)
    pd.set_option("display.width", 250)
    print(res.round(2).to_string(index=False))
    print("\nCorrelação diária entre motores (treino+valid):")
    d = S[S.index < "2025-01-01"].resample("1D").sum()
    print(d.corr().round(2))
    res.to_csv(os.path.join(AQUI, "resultado_motores.csv"), index=False)
    S.to_csv(os.path.join(AQUI, "series_motores.csv"))


if __name__ == "__main__":
    main()
