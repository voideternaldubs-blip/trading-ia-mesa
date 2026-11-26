"""PLACAR DA PROVA (até 30/11): mede, com dados reais do papel, o que cada robô acerta.
Retorno, operações fechadas, % de acerto, ganho médio x perda média, maior queda. Saída: data/prova.json"""
import os, csv, json
from datetime import datetime, timezone

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(RAIZ, "data")
FIM = "2026-11-30"


def ler(p, padrao):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return padrao


def queda(valores):
    topo, pior = None, 0.0
    for v in valores:
        topo = v if topo is None else max(topo, v)
        pior = min(pior, v / topo - 1) if topo else pior
    return pior


def resumo(nome, inicial, hist, resultados):
    vals = [h["valor"] for h in hist if h.get("valor") is not None]
    ganhos = [r for r in resultados if r > 0]; perdas = [r for r in resultados if r <= 0]
    atual = vals[-1] if vals else inicial
    return {"robo": nome, "inicial": inicial, "atual": round(atual, 2), "retorno_pct": round((atual / inicial - 1) * 100, 2),
            "operacoes": len(resultados), "acerto_pct": round(100 * len(ganhos) / len(resultados), 1) if resultados else None,
            "ganho_medio": round(sum(ganhos) / len(ganhos), 2) if ganhos else None, "perda_media": round(sum(perdas) / len(perdas), 2) if perdas else None,
            "maior_queda_pct": round(queda(vals) * 100, 2) if vals else 0.0}


def main():
    out = []
    f = ler(os.path.join(D, "foguete2.json"), {})
    res = []
    t = os.path.join(D, "foguete2_trades.csv")
    if os.path.exists(t):
        for r in csv.DictReader(open(t, encoding="utf-8")):
            if r["acao"] in ("FECHA", "REDUZ") and r["resultado"] not in ("", None):
                res.append(float(r["resultado"]))
    out.append(resumo("Foguete v2 (Binance demo)", 100.0, f.get("hist", []), res))
    c = ler(os.path.join(D, "carteira.json"), {})
    out.append(resumo("Tendência cripto", 100.0, [{"valor": h["valor"]} for h in c.get("historico", [])], []))
    a = ler(os.path.join(RAIZ, "acoes", "carteira_acoes.json"), {})
    out.append(resumo("Ações EUA (Alpaca)", 100.0, a.get("hist", []), []))
    ia = ler(os.path.join(D, "ia_pura.json"), {})
    out.append(resumo("IA pura (manual)", 100.0, ia.get("hist", []), [x["resultado"] for x in ia.get("fechadas", [])]))
    cp = ler(os.path.join(D, "carteira_predio.json"), {})
    out.insert(0, resumo("Carteira do Prédio", 100.0, cp.get("hist", []), [x["resultado"] for x in cp.get("fechadas", [])]))
    ro = ler(os.path.join(RAIZ, "acoes", "carteira_rotacao.json"), {})
    out.append(resumo("Foguete de ações (Alpaca)", 100.0, ro.get("hist", []), []))
    hoje = datetime.now(timezone.utc).date()
    dias = (datetime.fromisoformat(FIM).date() - hoje).days
    json.dump({"gerado": datetime.now(timezone.utc).isoformat()[:16], "fim": FIM, "dias_restantes": dias, "robos": out},
              open(os.path.join(D, "prova.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for r in out:
        print(f"{r['robo']:28} {r['atual']:8.2f} ({r['retorno_pct']:+.2f}%) | {r['operacoes']} ops | acerto {r['acerto_pct']}% | queda {r['maior_queda_pct']}%")
    print(f"faltam {dias} dias para 30/11")


if __name__ == "__main__":
    main()
