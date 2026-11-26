"""ROBÔ DE AÇÕES (EUA) — PAPEL, 100 USD de mentira, preços reais da Yahoo.
Roda 1x por dia útil depois do fechamento de Nova York.
Regra (testada 2010-2026): cada terço da carteira fica no ETF 3x quando o índice-base fecha ACIMA da média de 200 dias;
abaixo dela, vai pro caixa. TQQQ (Nasdaq), SOXL (chips), UPRO (S&P 500).
"""
import os, json
from datetime import datetime, timezone
from yahoo import historico

AQUI = os.path.dirname(os.path.abspath(__file__))
EST = os.path.join(AQUI, "carteira_acoes.json")
DIARIO = os.path.join(os.path.dirname(AQUI), "diario")
PARES = {"TQQQ": "QQQ", "SOXL": "SOXX", "UPRO": "SPY"}
CUSTO = 0.0005  # spread + escorregão por lado


def main():
    e = json.load(open(EST)) if os.path.exists(EST) else {"caixa": 100.0, "pos": {}, "hist": []}
    px = {t: historico(t, "2y")["c"] for t in list(PARES) + list(PARES.values())}
    preco = {t: float(px[t].iloc[-1]) for t in PARES}
    total = e["caixa"] + sum(q * preco[t] for t, q in e["pos"].items())
    log = []
    for etf, base in PARES.items():
        s = px[base]
        mm = float(s.rolling(200).mean().iloc[-1])
        acima = float(s.iloc[-1]) > mm
        alvo_usd = total / len(PARES) if acima else 0.0
        atual = e["pos"].get(etf, 0.0) * preco[etf]
        dif = alvo_usd - atual
        if abs(dif) < max(1.0, 0.05 * total / len(PARES)):  # só rebalanceia se mudou de verdade
            log.append(f"- {etf}: mantém ({'acima' if acima else 'abaixo'} da média 200 de {base}: {s.iloc[-1]:.2f} vs {mm:.2f})")
            continue
        q = dif / preco[etf]
        e["pos"][etf] = e["pos"].get(etf, 0.0) + q
        e["caixa"] -= dif + abs(dif) * CUSTO
        if abs(e["pos"][etf] * preco[etf]) < 0.5:
            e["pos"].pop(etf)
        log.append(f"- {'COMPRA' if dif > 0 else 'VENDE'} {etf} {abs(dif):.2f} USD a {preco[etf]:.2f} ({base} {'acima' if acima else 'abaixo'} da média 200)")
    total = e["caixa"] + sum(q * preco[t] for t, q in e["pos"].items())
    # ---- EXECUTOR: espelha a carteira na conta PAPER da Alpaca (orçamento = valor da carteira simulada)
    try:
        import alpaca
        if alpaca.chaves() and all(alpaca.chaves().values()):
            if alpaca.relogio()["is_open"]:
                atuais = alpaca.posicoes()
                for etf in PARES:
                    alvo = e["pos"].get(etf, 0.0) * preco[etf]
                    dif = alvo - atuais.get(etf, 0.0)
                    if abs(dif) >= 1.0:
                        if alvo == 0 and etf in atuais:
                            alpaca.zera(etf)
                        else:
                            o = alpaca.ordem_valor(etf, dif)
                            refs_f = os.path.join(AQUI, "ordens.json")
                            refs = json.load(open(refs_f)) if os.path.exists(refs_f) else {}
                            refs[o["id"]] = {"ativo": etf, "preco_ref": preco[etf], "usd": round(dif, 2), "dia": datetime.now(timezone.utc).isoformat()[:16]}
                            json.dump(refs, open(refs_f, "w"), indent=1)
                        log.append(f"- ALPACA: ordem {'compra' if dif > 0 else 'venda'} {etf} {abs(dif):.2f} USD enviada")
            else:
                log.append("- ALPACA: bolsa fechada, sincroniza na próxima rodada")
    except Exception as ex:
        log.append(f"- ALPACA: erro {str(ex)[:120]}")
    hoje =datetime.now(timezone.utc).strftime("%Y-%m-%d")
    e["hist"].append({"dia": hoje, "valor": round(total, 2)})
    json.dump(e, open(EST, "w"), indent=1)
    os.makedirs(DIARIO, exist_ok=True)
    txt = f"## {hoje} | ações: {total:.2f} USD ({total / 100 - 1:+.1%})\n" + "\n".join(log) + "\n\n"
    open(os.path.join(DIARIO, f"acoes_{hoje[:7]}.md"), "a", encoding="utf-8").write(txt)
    print(txt)


if __name__ == "__main__":
    main()
