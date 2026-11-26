"""AGENTE CALENDÁRIO: agenda econômica da semana (Fed, inflação, emprego, PIB) + balanços das empresas que a mesa olha.
Saída: data/calendario.json. Avisa o robô quando hoje tem evento de alto impacto."""
import os, json, requests
from datetime import datetime, timezone, timedelta

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAIDA = os.path.join(RAIZ, "data", "calendario.json")
UA = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
OLHO = ["NVDA", "AAPL", "MSFT", "TSLA", "AMD", "META", "GOOGL", "AMZN", "AVGO", "TSM", "NFLX", "PLTR", "MU", "ORCL", "COIN", "MSTR"]

TRADUZ = {
    "FOMC": ("Decisão de juros do Fed", "O Banco Central dos EUA decide os juros. É o evento que mais mexe com bolsa e cripto no mundo."),
    "Federal Funds Rate": ("Taxa de juros do Fed", "A decisão de juros em si. Surpresa aqui move tudo."),
    "CPI": ("Inflação ao consumidor (CPI)", "Mede quanto os preços subiram. Inflação alta = juros altos por mais tempo = pressão nas ações."),
    "Core PCE": ("Inflação PCE (a preferida do Fed)", "O índice de inflação que o Fed mais olha para decidir os juros."),
    "PPI": ("Inflação ao produtor (PPI)", "Preços cobrados pelas fábricas. Costuma antecipar a inflação ao consumidor."),
    "Non-Farm": ("Relatório de empregos (Payroll)", "Quantos empregos os EUA criaram. Emprego forte demais pode atrasar o corte de juros."),
    "Unemployment": ("Taxa de desemprego", "Desemprego subindo indica economia esfriando."),
    "GDP": ("PIB", "O tamanho da economia. Crescimento fraco assusta; forte demais pode manter juros altos."),
    "Retail Sales": ("Vendas no varejo", "Mostra se o consumidor americano está gastando."),
    "Jobless Claims": ("Pedidos de seguro-desemprego", "Termômetro semanal do mercado de trabalho."),
    "Powell": ("Discurso do presidente do Fed", "Uma frase dele pode mexer no mercado inteiro."),
    "ISM": ("Índice ISM (indústria/serviços)", "Mostra se as empresas estão crescendo (acima de 50) ou encolhendo."),
}


def traduz(titulo):
    for k, (pt, ex) in TRADUZ.items():
        if k.lower() in titulo.lower():
            return pt, ex
    return titulo, "Indicador econômico dos EUA. Impacto conforme a surpresa em relação ao esperado."


def main():
    eventos = []
    try:
        for x in requests.get("https://nfs.faireconomy.media/ff_calendar_thisweek.json", headers=UA, timeout=20).json():
            if x.get("country") != "USD" or x.get("impact") not in ("High", "Medium"):
                continue
            pt, ex = traduz(x["title"])
            eventos.append({"quando": x["date"][:16], "titulo": x["title"], "nome": pt, "explica": ex, "impacto": "alto" if x["impact"] == "High" else "médio",
                            "previsto": x.get("forecast", ""), "anterior": x.get("previous", "")})
    except Exception as e:
        print("calendário econômico falhou:", e)
    balancos = []
    hoje = datetime.now(timezone.utc).date()
    for d in range(0, 8):
        dia = hoje + timedelta(days=d)
        try:
            rows = requests.get(f"https://api.nasdaq.com/api/calendar/earnings?date={dia}", headers=UA, timeout=20).json()["data"]["rows"] or []
        except Exception:
            rows = []
        for r in rows:
            if r.get("symbol") in OLHO:
                balancos.append({"dia": str(dia), "ticker": r["symbol"], "empresa": r.get("name", ""), "hora": r.get("time", ""),
                                 "previsao_lucro": r.get("epsForecast", "")})
    hoje_s = str(hoje)
    alerta = [e for e in eventos if e["impacto"] == "alto" and e["quando"][:10] == hoje_s]
    out = {"gerado": datetime.now(timezone.utc).isoformat()[:16], "eventos": eventos, "balancos": balancos,
           "hoje_alto_impacto": [e["nome"] for e in alerta],
           "aviso": ("Hoje tem " + ", ".join(e["nome"] for e in alerta) + ": dia de mercado nervoso.") if alerta else "Sem evento de alto impacto hoje."}
    json.dump(out, open(SAIDA, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"CALENDÁRIO: {len(eventos)} eventos | {len(balancos)} balanços na mira | {out['aviso']}")


if __name__ == "__main__":
    main()
