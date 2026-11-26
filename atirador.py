"""ATIRADOR DE MEMECOINS (Solana) — PAPEL, 100 USD de mentira, preços reais.
Uma rodada por execução (agendado a cada 2 min). Estado em data/meme.json, registro em data/meme_trades.csv.

SCAN   -> GeckoTerminal: pools novos de Solana (5 a 90 min de vida)
VET    -> filtros de qualidade: liquidez, compradores x vendedores, volume, momentum
RUG    -> RugCheck: sem permissão de cunhar/congelar, sem riscos 'danger', concentração de donos
SNIPER -> "compra" 10 USD por moeda (máx 8 abertas), com taxa + escorregão realistas
EXIT   -> vende metade em 2x, resto com stop móvel de 35% do topo; stop -40%; tempo máx 12h;
          liquidez caiu 60%+ = puxaram o tapete -> recupera só 5%
CHIEF  -> placar e diário
"""
import os, json, time, csv, requests
from datetime import datetime, timezone

AQUI = os.path.dirname(os.path.abspath(__file__))
MODO = os.environ.get("MODO", "rigoroso")  # rigoroso | solto
EST = os.path.join(AQUI, "data", f"meme_{MODO}.json")
TRADES = os.path.join(AQUI, "data", f"meme_trades_{MODO}.csv")
DIARIO = os.path.join(AQUI, "diario")
UA = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

INICIAL, APOSTA, MAX_ABERTAS = 100.0, 10.0, 8
CUSTO = 0.03          # por lado: taxa de swap + prioridade + escorregão em moeda pequena (~3%)
TP, STOP, TRAIL, HORAS = 2.0, -0.40, 0.35, 12
SOL_MINT = "So11111111111111111111111111111111111111112"


def agora():
    return datetime.now(timezone.utc)


def carregar():
    if os.path.exists(EST):
        return json.load(open(EST, encoding="utf-8"))
    return {"caixa": INICIAL, "abertas": {}, "vistas": [], "inicio": agora().isoformat()}


def salvar(e):
    e["vistas"] = e["vistas"][-3000:]
    json.dump(e, open(EST, "w", encoding="utf-8"), indent=1)


def registrar(linha):
    novo = not os.path.exists(TRADES)
    with open(TRADES, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if novo:
            w.writerow(["quando", "moeda", "mint", "acao", "preco", "usd", "resultado_pct", "motivo"])
        w.writerow(linha)


def precos(mints):
    """DexScreener em lotes de 30: preço e liquidez do par mais líquido de cada moeda."""
    out = {}
    for i in range(0, len(mints), 30):
        try:
            r = requests.get("https://api.dexscreener.com/latest/dex/tokens/" + ",".join(mints[i:i + 30]), headers=UA, timeout=20).json()
        except Exception:
            continue
        for p in r.get("pairs") or []:
            m = p["baseToken"]["address"]
            liq = (p.get("liquidity") or {}).get("usd") or 0
            if m not in out or liq > out[m]["liq"]:
                out[m] = {"preco": float(p.get("priceUsd") or 0), "liq": liq}
    return out


def rugcheck(mint):
    try:
        r = requests.get(f"https://api.rugcheck.xyz/v1/tokens/{mint}/report/summary", headers=UA, timeout=15).json()
    except Exception:
        return False, "rugcheck falhou"
    riscos = r.get("risks") or []
    perigo = [x.get("name") for x in riscos if x.get("level") == "danger" and not (MODO == "solto" and "LP Unlocked" in (x.get("name") or ""))]
    if perigo:
        return False, "perigo: " + ", ".join(perigo)[:80]
    nomes = " ".join((x.get("name") or "").lower() for x in riscos)
    if "mint authority" in nomes or "freeze authority" in nomes:
        return False, "pode cunhar/congelar"
    if "top 10 holders" in nomes or "single holder" in nomes:
        return False, "donos concentrados"
    return True, f"score {r.get('score_normalised')}"


def scan(e):
    cands = []
    for pg in (1, 2, 3):
        try:
            d = requests.get(f"https://api.geckoterminal.com/api/v2/networks/solana/new_pools?page={pg}", headers=UA, timeout=20).json()["data"]
        except Exception:
            break
        for p in d:
            a = p["attributes"]
            base = p["relationships"]["base_token"]["data"]["id"].split("_", 1)[1]
            quote = p["relationships"]["quote_token"]["data"]["id"].split("_", 1)[1]
            if base == SOL_MINT:
                base, quote = quote, base
            if base in e["vistas"] or base in e["abertas"]:
                continue
            idade = (agora() - datetime.fromisoformat(a["pool_created_at"].replace("Z", "+00:00"))).total_seconds() / 60
            liq = float(a.get("reserve_in_usd") or 0)
            t5, t1h = a["transactions"]["m5"], a["transactions"]["h1"]
            vol1h = float((a.get("volume_usd") or {}).get("h1") or 0)
            ch5 = float((a["price_change_percentage"] or {}).get("m5") or 0)
            ch1h = float((a["price_change_percentage"] or {}).get("h1") or 0)
            # VET
            if not (5 <= idade <= 90): continue
            if liq < 15000 or vol1h < 20000: continue
            if t1h["buyers"] < 60 or t1h["buys"] < 1.2 * max(t1h["sells"], 1): continue
            if not (0 < ch5 < 60) or ch1h < 20: continue
            cands.append((vol1h / liq, base, a["name"], idade, liq, vol1h, ch1h))
        time.sleep(2.2)
    cands.sort(reverse=True)
    return cands


def main():
    e = carregar()
    log = []
    # ---- EXIT: gerencia as abertas
    pr = precos(list(e["abertas"]))
    for m, pos in list(e["abertas"].items()):
        q = pr.get(m)
        horas = (agora() - datetime.fromisoformat(pos["quando"])).total_seconds() / 3600
        if not q or q["preco"] <= 0:
            if horas > 1:  # sumiu do mapa = morreu
                registrar([agora().isoformat(), pos["nome"], m, "VENDA", 0, 0, -100, "sumiu"])
                log.append(f"- 💀 {pos['nome']}: sumiu (-100%)"); del e["abertas"][m]
            continue
        p = q["preco"]
        pos["topo"] = max(pos["topo"], p)
        mult = p / pos["preco"]
        motivo = None
        if q["liq"] < 0.4 * pos["liq"]:
            motivo, p = "tapete puxado", pos["preco"] * min(mult, 1) * 0.05
        elif mult - 1 <= STOP: motivo = "stop -40%"
        elif pos["metade"] and p <= pos["topo"] * (1 - TRAIL): motivo = "stop móvel"
        elif horas > HORAS: motivo = "tempo"
        if not pos["metade"] and mult >= TP and not motivo:
            usd = pos["qtd"] / 2 * p * (1 - CUSTO)
            e["caixa"] += usd; pos["qtd"] /= 2; pos["metade"] = True
            registrar([agora().isoformat(), pos["nome"], m, "VENDA 1/2", p, round(usd, 2), round((mult - 1) * 100), "2x"])
            log.append(f"- 💰 {pos['nome']}: 2x! vendeu metade (+{usd:.2f}$)")
        if motivo:
            usd = pos["qtd"] * p * (1 - CUSTO)
            e["caixa"] += usd
            registrar([agora().isoformat(), pos["nome"], m, "VENDA", p, round(usd, 2), round((p / pos["preco"] - 1) * 100), motivo])
            log.append(f"- {'🟢' if p > pos['preco'] else '🔴'} {pos['nome']}: {motivo} ({(p / pos['preco'] - 1):+.0%})")
            del e["abertas"][m]
    # ---- SCAN + VET + RUG + SNIPER
    if len(e["abertas"]) < MAX_ABERTAS and e["caixa"] >= APOSTA:
        for score, m, nome, idade, liq, vol, ch in scan(e)[:6]:
            e["vistas"].append(m)
            ok, porque = rugcheck(m)
            if not ok:
                log.append(f"- 🚫 {nome}: barrada ({porque})"); continue
            q = precos([m]).get(m)
            if not q or q["preco"] <= 0: continue
            p = q["preco"] * (1 + CUSTO)
            e["abertas"][m] = {"nome": nome, "preco": p, "qtd": APOSTA / p, "topo": p, "liq": q["liq"],
                               "quando": agora().isoformat(), "metade": False}
            e["caixa"] -= APOSTA
            registrar([agora().isoformat(), nome, m, "COMPRA", p, APOSTA, "", f"{idade:.0f}min liq {liq:.0f} vol1h {vol:.0f} +{ch:.0f}%/h"])
            log.append(f"- 🎯 COMPRA {nome}: 10$ ({idade:.0f} min de vida, liquidez {liq/1000:.0f}k, +{ch:.0f}% na hora)")
            if len(e["abertas"]) >= MAX_ABERTAS or e["caixa"] < APOSTA: break
    # ---- placar
    pr = precos(list(e["abertas"]))
    aberto = sum(pos["qtd"] * pr.get(m, {}).get("preco", 0) for m, pos in e["abertas"].items())
    total = e["caixa"] + aberto
    salvar(e)
    if log:
        os.makedirs(DIARIO, exist_ok=True)
        with open(os.path.join(DIARIO, f"meme_{MODO}_" + agora().strftime("%Y-%m-%d") + ".md"), "a", encoding="utf-8") as f:
            f.write(f"## {agora():%H:%M} UTC | carteira {total:.2f} USD ({total / INICIAL:.2f}x)\n" + "\n".join(log) + "\n\n")
    print(f"[{MODO}] {agora():%H:%M} carteira {total:.2f} USD ({total / INICIAL:.2f}x) | caixa {e['caixa']:.2f} | abertas {len(e['abertas'])}")
    print("\n".join(log))


if __name__ == "__main__":
    main()
