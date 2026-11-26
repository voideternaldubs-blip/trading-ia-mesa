"""FOGUETE DE AÇÕES — rotação entre ETFs alavancados de setores diferentes (Alpaca PAPEL, orçamento 100 USD).
Regra (testada): toda segunda-feira, fica nos 3 ETFs com maior alta de 20 pregões, só se estiverem acima da média de 50 dias.
Sem nenhum em alta → caixa. Prova 2023-26: +55%/ano; 2015-22: -9%/ano (depende do mercado subindo)."""
import os, json, time
from datetime import datetime, timezone
from yahoo import historico

AQUI = os.path.dirname(os.path.abspath(__file__))
EST = os.path.join(AQUI, "carteira_rotacao.json")
DIARIO = os.path.join(os.path.dirname(AQUI), "diario")
UNIVERSO = ["TECL", "FAS", "LABU", "TNA", "NUGT", "NVDL", "TSLL", "ERX", "DPST"]  # sem TQQQ/SOXL/UPRO (já usados no outro robô)
K, CUSTO = 3, 0.001


def main():
    agora = datetime.now(timezone.utc)
    e = json.load(open(EST)) if os.path.exists(EST) else {"caixa": 100.0, "pos": {}, "hist": [], "ultimo_rebal": ""}
    px, sc = {}, {}
    for t in UNIVERSO:
        try:
            c = historico(t, "1y")["c"]
            px[t] = float(c.iloc[-1])
            if c.iloc[-1] > c.rolling(50).mean().iloc[-1]:
                sc[t] = float(c.iloc[-1] / c.iloc[-21] - 1)
        except Exception:
            pass
        time.sleep(0.2)
    total = e["caixa"] + sum(q * px.get(t, 0) for t, q in e["pos"].items())
    log = []
    semana = agora.strftime("%G-%V")
    if e["ultimo_rebal"] != semana or not e["pos"]:  # rebalanceia 1x por semana; em caixa, confere todo dia
        top = [t for t, v in sorted(sc.items(), key=lambda x: -x[1])[:K] if v > 0]
        alvo = {t: total / K for t in top}
        for t in set(e["pos"]) | set(alvo):
            atual = e["pos"].get(t, 0) * px.get(t, 0)
            dif = alvo.get(t, 0) - atual
            if abs(dif) < 1 or t not in px:
                continue
            e["pos"][t] = e["pos"].get(t, 0) + dif / px[t]
            e["caixa"] -= dif + abs(dif) * CUSTO
            if abs(e["pos"][t] * px[t]) < 0.5:
                e["pos"].pop(t)
            log.append(f"- {'COMPRA' if dif > 0 else 'VENDE'} {t} {abs(dif):.2f} USD (alta de 20 dias {sc.get(t, 0):+.1%})")
        e["ultimo_rebal"] = semana if e["pos"] else ""
        # espelha na Alpaca de papel
        try:
            import alpaca
            if alpaca.chaves() and all(alpaca.chaves().values()) and alpaca.relogio()["is_open"]:
                atuais = alpaca.posicoes()
                for t in UNIVERSO:
                    a = e["pos"].get(t, 0) * px.get(t, 0); d = a - atuais.get(t, 0)
                    if abs(d) >= 1:
                        (alpaca.zera(t) if a == 0 and t in atuais else alpaca.ordem_valor(t, d))
                        log.append(f"- ALPACA: {t} {'compra' if d > 0 else 'venda'} {abs(d):.2f} USD")
        except Exception as ex:
            log.append(f"- ALPACA: {str(ex)[:100]}")
    total = e["caixa"] + sum(q * px.get(t, 0) for t, q in e["pos"].items())
    e["hist"].append({"dia": agora.isoformat()[:16], "valor": round(total, 2)})
    json.dump(e, open(EST, "w"), indent=1)
    os.makedirs(DIARIO, exist_ok=True)
    txt = f"## {agora:%Y-%m-%d %H:%M} | rotação de ações: {total:.2f} USD ({total / 100 - 1:+.1%}) | {', '.join(e['pos']) or 'caixa'}\n" + "\n".join(log) + "\n\n"
    open(os.path.join(DIARIO, f"rotacao_{agora:%Y-%m}.md"), "a", encoding="utf-8").write(txt)
    print(txt)


if __name__ == "__main__":
    main()
