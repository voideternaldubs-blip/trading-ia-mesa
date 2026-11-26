import numpy as np, pandas as pd, time
from yahoo import historico
T=["SPY","QQQ","EFA","AGG","BIL","XLK","XLF","XLE","XLV","XLY","XLP","XLI","XLB","XLU"]
P=pd.DataFrame({t:historico(t,"max")["adj"] for t in T}).dropna(how="all"); R=P.pct_change()
def met(r,ini="2010-01-01"):
    r=r[ini:].dropna();eq=(1+r).cumprod();a=len(r)/252
    per=lambda x,y:(1+r[x:y]).prod()-1
    return f"{eq.iloc[-1]**(1/a)-1:6.1%}/ano | queda máx {(eq/eq.cummax()-1).min():6.1%} | 2022 {per('2022','2022'):+5.0%} | 2025-26 {per('2025','2026'):+5.0%}"
datas=sorted({P.index[P.index<=d][-1] for d in P.resample("ME").last().index if (P.index<=d).any()})
def mensal(fn):
    linhas={}
    for d in datas:
        w=fn(d)
        if w: linhas[d]=pd.Series(w)
    W=pd.DataFrame(linhas).T.reindex(columns=P.columns).fillna(0).reindex(P.index).ffill().fillna(0)
    return (W.shift(1)*R).sum(axis=1)-W.diff().abs().sum(axis=1)*0.0005
def dual(d):
    m=P.loc[:d].iloc[-252:]
    if len(m)<252: return None
    r=m.iloc[-1]/m.iloc[0]-1
    if r["SPY"]>r["BIL"]: return {("SPY" if r["SPY"]>=r["EFA"] else "EFA"):1.0}
    return {"AGG":1.0}
SET=["XLK","XLF","XLE","XLV","XLY","XLP","XLI","XLB","XLU"]
def setor(d):
    m=P.loc[:d,SET].iloc[-126:]
    if len(m)<126: return None
    r=(m.iloc[-1]/m.iloc[0]-1).dropna().sort_values(ascending=False); return {s:1/3 for s in r.index[:3]}
if __name__=="__main__":
    print("SPY segurar        :", met(R["SPY"])); print("QQQ segurar        :", met(R["QQQ"]))
    print("1 Dual momentum    :", met(mensal(dual))); print("2 Rotação setores  :", met(mensal(setor)))
    c=P["SPY"]; d=c.diff(); up=d.clip(lower=0).ewm(alpha=.5).mean(); dn=(-d.clip(upper=0)).ewm(alpha=.5).mean(); rsi=100-100/(1+up/dn)
    pos=pd.Series(np.nan,index=c.index); pos[(rsi<10)&(c>c.rolling(200).mean())]=1; pos[rsi>70]=0; pos=pos.ffill().fillna(0)
    print("3 RSI(2) SPY       :", met(pos.shift(1)*R["SPY"]-pos.diff().abs()*0.0005), f"| investido {pos['2010':].mean():.0%} do tempo")
    v=R["QQQ"].rolling(20).std()*np.sqrt(252); lev=(0.20/v).clip(upper=2).shift(1)
    print("4 Vol-alvo QQQ 0-2x:", met(lev*R["QQQ"]-lev.diff().abs()*0.0005-(lev-1).clip(lower=0)*0.05/252))
    s=P["QQQ"]; on=(s>s.rolling(200).mean()).shift(1).fillna(False)
    print("ATUAL TQQQ+MM200   :", met(R["QQQ"]*3*on-0.0095/252-on.astype(int).diff().abs()*0.0005))
    lev2=((0.20/v).clip(upper=2)*on).shift(1)
    print("5 Vol-alvo+MM200   :", met(lev2*R["QQQ"]-lev2.diff().abs()*0.0005-(lev2-1).clip(lower=0)*0.05/252))
