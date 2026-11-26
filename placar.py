"""Placar geral: robô de tendência + os dois atiradores de memecoin."""
import os, json, csv
AQUI = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(AQUI, "data")

c = json.load(open(os.path.join(D, "carteira.json"), encoding="utf-8"))
h = c["historico"][-1]
print(f"TENDÊNCIA (futuros): {h['valor']:.2f} USD ({h['valor']/100-1:+.1%}) em {h['quando']} | posições: {len(c['pos'])}")

for modo in ("rigoroso", "solto"):
    f = os.path.join(D, f"meme_{modo}.json")
    if not os.path.exists(f):
        continue
    e = json.load(open(f, encoding="utf-8"))
    vendas, ganhos, perdas, melhor = 0, 0, 0, None
    t = os.path.join(D, f"meme_trades_{modo}.csv")
    if os.path.exists(t):
        for r in csv.DictReader(open(t, encoding="utf-8")):
            if r["acao"] == "VENDA":
                vendas += 1
                pct = float(r["resultado_pct"] or 0)
                ganhos += pct > 0; perdas += pct <= 0
                if melhor is None or pct > melhor[1]:
                    melhor = (r["moeda"], pct)
    aberto = sum(p["qtd"] * p["preco"] for p in e["abertas"].values())  # a preço de compra
    print(f"MEMECOIN {modo:8}: caixa {e['caixa']:.2f} + {len(e['abertas'])} abertas (~{aberto:.2f} pelo custo) | "
          f"fechadas {vendas} ({ganhos} ganhos / {perdas} perdas) | melhor: {melhor}")
print("\nDiário detalhado em", os.path.join(AQUI, "diario"))
