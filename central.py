"""MESA GERAL: junta todos os robôs num placar e num painel HTML (painel.html, atualiza sozinho).
Robôs: tendência cripto (futuros), ações EUA (ETFs 3x + MM200), memecoins Solana (rigoroso e solto).
Cada robô opera 100 USD de mentira com preço real. Total = soma das mesas."""
import os, json, csv, html
from datetime import datetime

AQUI = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(AQUI, "data")


def ler(p, padrao=None):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return padrao


def mesas():
    out = []
    c = ler(os.path.join(D, "carteira.json"))
    if c and c.get("historico"):
        h = c["historico"]
        out.append({"nome": "Tendência cripto", "mercado": "Futuros Binance · 10 moedas", "valor": h[-1]["valor"],
                    "posicoes": [f"{m} {'comprado' if p['qtd'] > 0 else 'vendido'}" for m, p in c["pos"].items()],
                    "curva": [x["valor"] for x in h[-120:]], "quando": h[-1]["quando"]})
    a = ler(os.path.join(AQUI, "acoes", "carteira_acoes.json"))
    if a and a.get("hist"):
        out.append({"nome": "Ações EUA", "mercado": "TQQQ · SOXL · UPRO (filtro média 200)", "valor": a["hist"][-1]["valor"],
                    "posicoes": list(a["pos"]) or ["caixa (mercado abaixo da média 200)"],
                    "curva": [x["valor"] for x in a["hist"][-120:]], "quando": a["hist"][-1]["dia"]})
    r = ler(os.path.join(AQUI, "acoes", "carteira_rotacao.json"))
    if r and r.get("hist"):
        out.append({"nome": "Foguete de ações", "mercado": "ETFs alavancados · 9 setores · Alpaca", "valor": r["hist"][-1]["valor"],
                    "posicoes": list(r.get("pos", {})) or ["caixa (nenhum setor em alta)"], "curva": [x["valor"] for x in r["hist"][-120:]], "quando": r["hist"][-1]["dia"]})
    cp = ler(os.path.join(D, "carteira_predio.json"))
    if cp and cp.get("hist"):
        out.append({"nome": "Carteira do Prédio", "mercado": "diretoria + 30 analistas de IA · Binance demo", "valor": cp["hist"][-1]["valor"],
                    "posicoes": [s.replace("USDT", "") + (" C" if p["lado"] > 0 else " V") for s, p in cp.get("posicoes", {}).items()] or ["sem posição"],
                    "curva": [x["valor"] for x in cp["hist"][-120:]], "quando": cp["hist"][-1]["quando"]})
    ia = ler(os.path.join(D, "ia_pura.json"))
    if ia and ia.get("hist"):
        out.append({"nome": "IA pura (manual)", "mercado": "operações manuais · Binance demo", "valor": ia["hist"][-1]["valor"],
                    "posicoes": [f"{s.replace('USDT', '')} C" for s in ia.get("posicoes", {})] or ["sem posição"],
                    "curva": [x["valor"] for x in ia["hist"][-120:]], "quando": ia["hist"][-1]["quando"]})
    fg = ler(os.path.join(D, "foguete2.json"))
    if fg and fg.get("hist"):
        h = fg["hist"][-1]
        out.append({"nome": "Foguete v2 (CPPI)", "mercado": "até 12 moedas · alavancagem CPPI · cofre separado", "valor": h["valor"],
                    "posicoes": [f"{s.replace('USDT', '')} {'C' if p['lado'] > 0 else 'V'}" for s, p in fg["posicoes"].items()] or [fg["conta"]["status"]],
                    "curva": [x["valor"] for x in fg["hist"][-120:]], "quando": h["quando"],
                    "extra": f"foguete {h.get('foguete', 0):.2f} + cofre {fg['conta']['cofre']:.2f} · exposição {h.get('exposicao', 0):.0f}"})
    for modo in ("rigoroso", "solto"):
        e = ler(os.path.join(D, f"meme_{modo}.json"))
        if not e:
            continue
        custo_aberto = sum(p["qtd"] * p["preco"] for p in e["abertas"].values())
        vendas = []
        t = os.path.join(D, f"meme_trades_{modo}.csv")
        if os.path.exists(t):
            vendas = [r for r in csv.DictReader(open(t, encoding="utf-8")) if r["acao"] == "VENDA"]
        ganhos = sum(1 for r in vendas if float(r["resultado_pct"] or 0) > 0)
        out.append({"nome": f"Memecoin {modo}", "mercado": "Solana · moedas novas", "valor": round(e["caixa"] + custo_aberto, 2),
                    "posicoes": [p["nome"] for p in e["abertas"].values()] or ["nenhuma"],
                    "extra": f"{len(vendas)} fechadas · {ganhos} ganhos", "curva": [], "quando": "a cada 3 min"})
    return out


def sparkline(v, w=220, h=44):
    if len(v) < 2:
        return ""
    lo, hi = min(v), max(v)
    rng = (hi - lo) or 1
    pts = " ".join(f"{i * w / (len(v) - 1):.1f},{h - (x - lo) / rng * h:.1f}" for i, x in enumerate(v))
    cor = "#16a34a" if v[-1] >= v[0] else "#dc2626"
    return f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}"><polyline fill="none" stroke="{cor}" stroke-width="2" points="{pts}"/></svg>'


def painel(ms):
    total = sum(m["valor"] for m in ms)
    base = 100 * len(ms)
    cards = ""
    for m in ms:
        pct = m["valor"] / 100 - 1
        cards += f"""<div class="c"><div class="t">{html.escape(m['nome'])}</div><div class="s">{html.escape(m['mercado'])}</div>
<div class="v {'up' if pct >= 0 else 'dn'}">{m['valor']:.2f} USD <span>{pct:+.1%}</span></div>{sparkline(m['curva'])}
<div class="p">{html.escape(', '.join(m['posicoes'])[:160])}</div><div class="s">{html.escape(m.get('extra', ''))} · {html.escape(str(m['quando']))}</div></div>"""
    return f"""<!doctype html><html lang="pt-br"><meta charset="utf-8"><meta http-equiv="refresh" content="60">
<title>Mesa geral · {total:.2f} USD</title><style>
body{{font:15px system-ui;background:#0b0d10;color:#e6e6e6;margin:0;padding:32px}}h1{{font-size:44px;margin:0}}
.sub{{color:#8a8f98;margin:6px 0 28px}}.g{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:16px}}
.c{{background:#14171c;border:1px solid #23272e;border-radius:12px;padding:18px}}.t{{font-weight:700;font-size:17px}}
.s{{color:#8a8f98;font-size:13px;margin-top:4px}}.v{{font-size:26px;font-weight:700;margin:12px 0 6px}}.v span{{font-size:15px}}
.up{{color:#22c55e}}.dn{{color:#ef4444}}.p{{font-size:13px;margin-top:8px;color:#c9ccd1}}</style>
<h1 class="{'up' if total >= base else 'dn'}">{total:.2f} USD</h1>
<div class="sub">Mesa geral · {len(ms)} robôs · começou com {base} USD (papel, preço real) · {total / base - 1:+.1%} · atualizado {datetime.now():%d/%m %H:%M}</div>
<div class="g">{cards}</div></html>"""


if __name__ == "__main__":
    ms = mesas()
    open(os.path.join(AQUI, "painel.html"), "w", encoding="utf-8").write(painel(ms))
    for m in ms:
        print(f"{m['nome']:18} {m['valor']:8.2f} USD ({m['valor'] / 100 - 1:+.1%}) | {', '.join(m['posicoes'])[:70]}")
    t = sum(m["valor"] for m in ms)
    print(f"{'TOTAL':18} {t:8.2f} USD de {100 * len(ms)} ({t / (100 * len(ms)) - 1:+.1%}) | painel: {os.path.join(AQUI, 'painel.html')}")
