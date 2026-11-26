"""MOTOR RÁPIDO — roda dentro da nuvem sem parar por N minutos.
A cada ciclo (~2 min): ARANHA coleta (todas as fontes em paralelo) + explica, as carteiras conferem stop/alvo,
CHEFE e PROVA atualizam o placar, o site recebe os dados novos (via GitHub, sem gastar publicação da Vercel).
A cada 5 min: FOGUETE v2 (ciclo de risco). A cada 15 min: MÁQUINA DO TEMPO.
Uso: python motor.py --minutos 40"""
import os, sys, time, subprocess
from datetime import datetime, timezone

AQUI = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
SALVAR = ["data/relatorio_aranha.json", "data/carteira.json", "data/prova.json", "data/foguete2.json", "data/ia_pura.json", "data/carteira_predio.json",
          "data/probabilidades.json", "data/predio.json", "data/cotas_ia.json", "data/foguete2_trades.csv", "data/foguete2_exec.json", "data/sentinela.json", "diario", "site"]


def roda(nome, args, cwd=AQUI, limite=240):
    t = time.time()
    try:
        r = subprocess.run([PY] + args, cwd=cwd, capture_output=True, text=True, timeout=limite)
        fim = (r.stdout or r.stderr or "").strip().splitlines()[-1:] or [""]
        print(f"  {nome:14} {time.time() - t:5.1f}s  {fim[0][:110]}", flush=True)
    except Exception as ex:
        print(f"  {nome:14} FALHOU {str(ex)[:100]}", flush=True)


def salva(extra=()):
    g = lambda *a: subprocess.run(["git"] + list(a), cwd=AQUI, capture_output=True, text=True)
    for f in SALVAR + list(extra):
        if os.path.exists(os.path.join(AQUI, f)):
            g("add", f)
    if g("diff", "--cached", "--quiet").returncode == 0:
        return
    g("commit", "-q", "-m", f"motor: {datetime.now(timezone.utc):%Y-%m-%dT%H:%M}Z")
    for _ in range(3):
        if g("pull", "-q", "--rebase", "--autostash", "-X", "theirs").returncode == 0 and g("push", "-q").returncode == 0:
            print("  salvo e publicado", flush=True); return
        time.sleep(4)
    print("  não consegui salvar nesta volta (tento na próxima)", flush=True)


def main(minutos):
    fim = time.time() + minutos * 60
    n = 0
    ult_fog = ult_maq = 0
    ult_pred = 0; proc_pred = None
    while time.time() < fim:
        n += 1
        t0 = time.time()
        print(f"[ciclo {n}] {datetime.now(timezone.utc):%H:%M:%S} UTC", flush=True)
        roda("ARANHA", ["-c", "import aranha; c=aranha.db(); print('notícias novas', aranha.noticias(c)); c.commit()"])
        roda("EXPLICADOR", ["explicador.py"], cwd=os.path.join(AQUI, "mesa"))
        if time.time() - ult_fog >= 290:
            roda("FOGUETE v2", ["foguete2.py"]); ult_fog = time.time()
        # PRÉDIO: 30+ analistas (um por moeda) em paralelo, a cada 30 min, sem segurar o motor
        if proc_pred is not None and proc_pred.poll() is not None:
            print(f"  PRÉDIO         terminou: {(proc_pred.stdout.read() or '').strip().splitlines()[-1:]}", flush=True)
            proc_pred = None
            roda("DIRETORIA", ["predio.py", "--so-diretoria"])   # na sequência, antes do gerente da carteira
        if proc_pred is None and time.time() - ult_pred >= 1790:
            proc_pred = subprocess.Popen([PY, "predio.py", "--sem-diretoria"], cwd=AQUI, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            ult_pred = time.time(); print("  PRÉDIO         começou (roda em paralelo)", flush=True)
        roda("CARTEIRA PRÉDIO", ["ia_pura.py", "data/carteira_predio.json"])
        roda("IA MANUAL", ["ia_pura.py"])
        if time.time() - ult_maq >= 890:
            roda("MÁQUINA TEMPO", [os.path.join("equipe", "maquina_tempo.py")]); ult_maq = time.time()
        roda("PROVA", ["prova.py"], cwd=os.path.join(AQUI, "equipe"))
        roda("CHEFE", ["central.py"])
        roda("SITE", [os.path.join("mesa", "exportar_site.py")])
        salva()
        espera = 120 - (time.time() - t0)
        if espera > 0 and time.time() + espera < fim:
            time.sleep(espera)
    salva(["data/aranha.db"])  # o banco grande só no fim da rodada (não inchar o repositório)


if __name__ == "__main__":
    main(float(sys.argv[sys.argv.index("--minutos") + 1]) if "--minutos" in sys.argv else 40)
