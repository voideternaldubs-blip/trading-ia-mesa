"""AGENTE SENTINELA: vigia se cada agente trabalhou no tempo certo. Se algum parar, acende alerta no painel.
Saída: data/sentinela.json"""
import os, json
from datetime import datetime, timezone

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(RAIZ, "data")


def idade_horas(iso):
    try:
        t = datetime.fromisoformat(iso.replace(" UTC", "").replace("Z", "").strip()[:16])
        return (datetime.now(timezone.utc).replace(tzinfo=None) - t).total_seconds() / 3600
    except Exception:
        return None


def ler(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def main():
    checks = []
    def chk(nome, quando, limite_h, oque):
        h = idade_horas(quando) if quando else None
        ok = h is not None and h <= limite_h
        checks.append({"agente": nome, "ok": ok, "ultima_vez": quando, "horas": round(h, 1) if h is not None else None,
                       "esperado": f"a cada {limite_h}h", "o_que_faz": oque})
    r = ler(os.path.join(D, "relatorio_aranha.json")) or {}
    chk("ARANHA", (r.get("gerado") or "").replace(" ", "T"), 3, "coleta e explica notícias do mundo")
    c = ler(os.path.join(D, "carteira.json")) or {}
    chk("TENDÊNCIA CRIPTO", (c.get("historico") or [{}])[-1].get("quando", "").replace(" UTC", "").replace(" ", "T"), 6, "robô de futuros cripto")
    a = ler(os.path.join(RAIZ, "acoes", "carteira_acoes.json")) or {}
    dia = (a.get("hist") or [{}])[-1].get("dia", "")
    chk("AÇÕES", (dia + "T21:00") if dia else "", 80, "robô de ETFs + Alpaca (dias úteis)")
    k = ler(os.path.join(D, "calendario.json")) or {}
    chk("CALENDÁRIO", k.get("gerado", ""), 3, "agenda do Fed, inflação e balanços")
    s = ler(os.path.join(D, "sec.json")) or {}
    chk("SEC", s.get("gerado", ""), 3, "documentos oficiais e compras de diretores")
    ok = all(x["ok"] for x in checks)
    out = {"gerado": datetime.now(timezone.utc).isoformat()[:16], "tudo_ok": ok, "checks": checks,
           "resumo": "Todos os agentes trabalhando." if ok else "ATENÇÃO: " + ", ".join(x["agente"] for x in checks if not x["ok"]) + " atrasado(s)."}
    json.dump(out, open(os.path.join(D, "sentinela.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("SENTINELA:", out["resumo"])


if __name__ == "__main__":
    main()
