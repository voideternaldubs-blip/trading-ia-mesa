"""AGENTE FILLS: confere cada ordem executada na Alpaca (papel) contra o preço que o robô esperava.
Escorregão alto demais = o backtest está otimista e precisa de ajuste. Saída: data/fills.json"""
import os, sys, json
from datetime import datetime, timezone

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "acoes"))
REF = os.path.join(RAIZ, "acoes", "ordens.json")
SAIDA = os.path.join(RAIZ, "data", "fills.json")
LIMITE = 0.002  # 0,2%: acima disso, alerta


def main():
    import alpaca
    refs = json.load(open(REF, encoding="utf-8")) if os.path.exists(REF) else {}
    if not (alpaca.chaves() and all(alpaca.chaves().values())):
        print("FILLS: sem chaves"); return
    ordens = alpaca._req("GET", "/orders", params={"status": "closed", "limit": 100, "direction": "desc"})
    linhas, alertas = [], 0
    for o in ordens:
        if o.get("status") != "filled":
            continue
        pref = refs.get(o["id"], {}).get("preco_ref")
        px = float(o["filled_avg_price"])
        esc = None
        if pref:
            esc = (px / pref - 1) * (1 if o["side"] == "buy" else -1)  # positivo = pagou pior que o esperado
            alertas += esc > LIMITE
        linhas.append({"quando": o["filled_at"][:16], "ativo": o["symbol"], "lado": "compra" if o["side"] == "buy" else "venda",
                       "valor_usd": round(float(o.get("filled_qty", 0)) * px, 2), "preco": px, "preco_esperado": pref,
                       "escorregao_pct": round(esc * 100, 3) if esc is not None else None})
    medio = [l["escorregao_pct"] for l in linhas if l["escorregao_pct"] is not None]
    out = {"gerado": datetime.now(timezone.utc).isoformat()[:16], "execucoes": linhas, "alertas": int(alertas),
           "escorregao_medio_pct": round(sum(medio) / len(medio), 3) if medio else None}
    json.dump(out, open(SAIDA, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"FILLS: {len(linhas)} execuções | escorregão médio {out['escorregao_medio_pct']}% | alertas {alertas}")


if __name__ == "__main__":
    main()
