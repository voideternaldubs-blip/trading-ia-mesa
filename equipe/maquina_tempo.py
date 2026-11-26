"""MÁQUINA DO TEMPO (inspirada no trader-timemachine): para cada posição aberta da IA pura, sorteia 10.000 futuros
a partir dos candles de 15 min reais dos últimos 60 dias (blocos de 1h para manter o 'jeito' do mercado) e mede a chance
de bater o ALVO antes do STOP até o prazo. Saída: data/probabilidades.json (lido pelo site)."""
import os, json, time, random, requests
from datetime import datetime, timezone
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIM = datetime(2026, 11, 30, 23, 59, tzinfo=timezone.utc)
def velas(s, dias=60):
    fim = int(time.time() * 1000); ini = fim - dias * 86400000; out = []
    while ini < fim:
        r = requests.get("https://data-api.binance.vision/api/v3/klines", params={"symbol": s, "interval": "15m", "startTime": ini, "limit": 1000}, timeout=30).json()
        if not r: break
        out += r; ini = r[-1][0] + 1
    return [(float(x[1]), float(x[2]), float(x[3]), float(x[4])) for x in out]
def simula(v, preco, stop, alvo, lado, passos, n=10000, bloco=4):
    rel = [(o / pc, h / pc, l / pc, c / pc) for (_, _, _, pc), (o, h, l, c) in zip(v, v[1:])]
    alvo_n = stop_n = 0; finais = []
    for _ in range(n):
        p = preco; res = None; k = 0
        while k < passos and res is None:
            i = random.randrange(len(rel) - bloco)
            for ro, rh, rl, rc in rel[i:i + bloco]:
                h, l = p * rh, p * rl
                bate_stop = (l <= stop) if lado > 0 else (h >= stop)
                bate_alvo = (h >= alvo) if lado > 0 else (l <= alvo)
                if bate_stop: res = "stop"; break   # conservador: stop antes do alvo no mesmo candle
                if bate_alvo: res = "alvo"; break
                p = p * rc; k += 1
        alvo_n += res == "alvo"; stop_n += res == "stop"; finais.append(p)
    finais.sort()
    return alvo_n / n, stop_n / n, finais[n // 2]
def main():
    e = {"posicoes": {}}
    for _f in ("carteira_predio.json", "ia_pura.json"):
        try: e["posicoes"].update(json.load(open(os.path.join(RAIZ, "data", _f), encoding="utf-8")).get("posicoes", {}))
        except Exception: pass
    passos = max(1, int((FIM - datetime.now(timezone.utc)).total_seconds() // 900))
    out = {"gerado": datetime.now(timezone.utc).isoformat()[:16], "prazo": FIM.isoformat()[:16], "posicoes": {}}
    ganho_esp = 0
    for s, p in e["posicoes"].items():
        v = velas(s); preco = v[-1][3]
        pa, ps, med = simula(v, preco, p["stop"], p["alvo"], p["lado"], passos)
        g = p["qtd"] * abs(p["alvo"] - preco); r = p["qtd"] * abs(preco - p["stop"])
        ev = pa * g - ps * r + (1 - pa - ps) * p["lado"] * p["qtd"] * (med - preco)
        ganho_esp += ev
        out["posicoes"][s] = {"preco": preco, "chance_alvo": round(pa, 3), "chance_stop": round(ps, 3), "nenhum": round(1 - pa - ps, 3), "valor_esperado": round(ev, 2)}
        print(f"{s:9} preço {preco:<9g} ALVO {pa:5.1%} | STOP {ps:5.1%} | nenhum {1-pa-ps:5.1%} | valor esperado {ev:+.2f} USD")
    out["valor_esperado_total"] = round(ganho_esp, 2)
    json.dump(out, open(os.path.join(RAIZ, "data", "probabilidades.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"valor esperado da carteira até {FIM:%d/%m}: {ganho_esp:+.2f} USD ({passos} candles de 15 min pela frente)")
if __name__ == "__main__":
    main()
