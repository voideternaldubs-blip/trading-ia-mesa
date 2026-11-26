"""GERENTE DE CARTEIRA — confere stop/alvo minuto a minuto e marca o valor ao vivo.
Uso: python ia_pura.py [data/carteira_predio.json]  (sem argumento = IA pura manual).
A cada rodada: confere minuto a minuto desde a última vez; fecha no stop ou no alvo; em +5% sobe o stop para a entrada."""
import os, sys, json, requests
from datetime import datetime, timezone
import binance_demo as b

AQUI = os.path.dirname(os.path.abspath(__file__))
EST = os.path.join(AQUI, sys.argv[1]) if len(sys.argv) > 1 else os.path.join(AQUI, "data", "ia_pura.json")
NOME = "CARTEIRA DO PRÉDIO" if "predio" in EST else "IA PURA (manual)"
DIARIO = os.path.join(AQUI, "diario")


def main():
    e = json.load(open(EST, encoding="utf-8"))
    log, agora = [], datetime.now(timezone.utc)
    for s, p in list(e["posicoes"].items()):
        ini = int(datetime.fromisoformat(p.get("conferido_ate", p["em"])).replace(tzinfo=timezone.utc).timestamp() * 1000)
        k = requests.get(b.BASE + "/fapi/v1/klines", params={"symbol": s, "interval": "1m", "startTime": ini, "limit": 1000}, timeout=20).json()
        saida = None
        for x in k:
            o, h, l = float(x[1]), float(x[2]), float(x[3])
            fav = (h - p["entrada"]) if p["lado"] > 0 else (p["entrada"] - l)
            if fav / p["entrada"] >= 0.05 and p["lado"] * (p["entrada"] - p["stop"]) > 0:
                p["stop"] = p["entrada"]; log.append(f"- 🔒 {s}: +5%, stop subiu para a entrada ({p['entrada']:g})")
            if p["lado"] > 0:
                if l <= p["stop"]:
                    saida = (min(o, p["stop"]), "stop"); break
                if h >= p["alvo"]:
                    saida = (max(o, p["alvo"]), "alvo"); break
            else:
                if h >= p["stop"]:
                    saida = (max(o, p["stop"]), "stop"); break
                if l <= p["alvo"]:
                    saida = (min(o, p["alvo"]), "alvo"); break
        if k:
            p["conferido_ate"] = datetime.fromtimestamp(int(k[-1][0]) / 1000, timezone.utc).isoformat()[:16]
        if saida:
            try:
                b.ordem(s, -p["lado"] * p["qtd"], reduz=True)
            except Exception as ex:
                log.append(f"- ⚠️ {s}: ordem de saída falhou ({str(ex)[:80]})")
            res = p["lado"] * p["qtd"] * (saida[0] - p["entrada"]) - p["qtd"] * saida[0] * 0.0005 * 2
            e["caixa"] += res
            e["fechadas"].append({"simbolo": s, "entrada": p["entrada"], "saida": saida[0], "motivo": saida[1], "resultado": round(res, 2), "quando": agora.isoformat()[:16]})
            log.append(f"- {'🟢' if res >= 0 else '🔴'} {NOME} fechou {s} no {saida[1]}: {res:+.2f} USD")
            del e["posicoes"][s]
    # valor ao vivo
    aberto = 0.0
    for s, p in e["posicoes"].items():
        px = float(requests.get(b.BASE + "/fapi/v1/ticker/price", params={"symbol": s}, timeout=10).json()["price"])
        p["atual"] = px; aberto += p["lado"] * p["qtd"] * (px - p["entrada"])
    total = e["caixa"] + aberto
    e.setdefault("hist", []).append({"quando": agora.isoformat()[:16], "valor": round(total, 2)})
    e["hist"] = e["hist"][-2000:]
    json.dump(e, open(EST, "w", encoding="utf-8"), indent=1)
    if log:
        os.makedirs(DIARIO, exist_ok=True)
        open(os.path.join(DIARIO, f"{os.path.basename(EST)[:-5]}_{agora:%Y-%m}.md"), "a", encoding="utf-8").write(f"## {agora:%Y-%m-%d %H:%M} UTC | {NOME} {total:.2f} USD\n" + "\n".join(log) + "\n\n")
    print(f"{NOME} {agora:%H:%M} | {total:.2f} USD ({total / e['inicial'] - 1:+.1%}) | abertas: {', '.join(f'{s} {p.get(chr(97)+chr(116)+chr(117)+chr(97)+chr(108), 0):g}' for s, p in e['posicoes'].items()) or 'nenhuma'}")
    print("\n".join(log))


if __name__ == "__main__":
    main()
