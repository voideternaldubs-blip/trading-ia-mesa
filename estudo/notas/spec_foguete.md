

Mostrar menos
há 6 minutos



O Claude respondeu: Abaixo está a especificação completa do motor.
Definindo a regra de ordens e a banda de rebalanceamento

Definindo a regra de ordens e a banda de rebalanceamento

Pensou por 4min 12s

Planning a paper-trading engine spec.

Deciding whether to help with the spec.

Calculando a chance real de dobrar o capital.

Avaliando o teto de chance com piso de proteção.

Desenhando a estrutura de alocação e risco.

Definindo o tamanho de exposição por posição.

Separando a reserva em conta física fixa.

Estimando a chance de atingir a meta em prazo curto.

Estimando a chance de atingir a meta no prazo.

Ajustando escada de exposição pelo patrimônio do foguete.

Definindo a regra de saída por cruzamento do canal.

Definindo a rotação de lucros entre as moedas.

Definindo regras de proteção e circuito de parada.

Definindo salvaguardas de financiamento e dados.

Definindo o ciclo de execução e a gravação do estado.

Estimando probabilidades de resultado com a escada de exposição.

Ajustando a exposição para a chance máxima de meta.

Ajustando a exposição para a chance máxima de meta.

Ajustando a exposição da carteira de foguete por CPPI.

Calculando a chance de atingir o teto com CPPI.

Checando o tamanho da alavancagem e a liquidação.

Definindo o cofre progressivo e a trava de lucro.

Definindo a regra de realização parcial e o filtro de universo.

Definindo o filtro de liquidez e a lista de exclusões.

Calculando a exposição de cada horizonte e o limite de alavancagem.

Definindo métricas de fidelidade e critérios de desligamento.

Definindo métricas de fidelidade e critérios de desligamento.

Definindo o ciclo de execução e o replay minuto a minuto.

Definindo o cálculo do sinal por canal.

Definindo o cálculo de alvos e ordens.

Definindo a regra de ordens e a banda de rebalanceamento.

Abaixo está a especificação completa do motor. O dado mais importante vem primeiro: não existe desenho que passe de uns 4% de chance de 10x em 30 dias, e o melhor que dá para esperar na prática é 1 a 2%. A tabela abaixo mostra de onde vem esse teto.

0. Probabilidade honesta (leia antes de implementar)

Num jogo sem vantagem e sem custos, a chance de bater a meta antes do piso é (dinheiro em risco) / (distância até a meta). Nenhum desenho supera esse teto, só se aproxima dele.

Configuração	Teto teórico P(total ≥ 1000)	Expectativa realista (com custos)
100 tudo em risco, sem piso	10%	3-5%, com ~85% de chance de zerar
50 no cofre + 50 no foguete, piso de 15 no foguete	3,7%	1-2%
50 no cofre + 50 no foguete sem piso	5,3%	2-3%
O resultado mais provável em 30 dias é o total terminar entre 65 e 110 USD. O foguete deve bater no piso e se encerrar em uns 60 a 80% dos casos.
100 → 10.000 nos dois estágios: de 1 em 2.500 a 1 em 10.000.
Diversificar não aumenta a chance de 10x. O que move a chance é o multiplicador m (item 4). A carteira com várias moedas serve para preservar a vantagem da tendência e não depender do pavio de uma moeda só.
“Girar para a moeda mais forte” já falhou nos seus testes: concentrar nas 5 mais fortes deixou o Sharpe negativo e quebrou em 75% dos caminhos, e o momentum relativo trocou de sinal fora da amostra. Por isso, a rotação abaixo é uma inclinação dos pesos, não uma troca total.
Proteção física dos 100: o cofre de 50 USDT fica fora da carteira de futuros (subconta ou carteira spot). Assim, nem uma liquidação total do foguete encosta nele. É a única proteção que não depende de código funcionando.
1. Universo

Recalcule todo dia às 00:05 UTC:

Binance USDT-M com contractType == PERPETUAL, status == TRADING e quoteAsset == USDT.
onboardDate com pelo menos 180 dias.
Exclua stablecoins e moedas atreladas (USDC, FDUSD, TUSD, USDP, DAI, EUR), ouro e ações tokenizadas (PAXG, XAUT, perpétuos de ações) e índices (BTCDOM e similares).
Mediana do volume diário em USD dos últimos 30 dias ≥ 100 milhões.
Fique com as 30 primeiras por volume.
Filtro na hora da entrada: spread do bookTicker (ask - bid)/médio ≤ 0,05%.
Moeda que sai do universo não abre posição nova. A que já está aberta segue a regra de saída normal.
Leia minNotional, stepSize e tickSize do exchangeInfo, por moeda. Não use valores fixos.
2. Sinal e ranking

O ciclo de 5 minutos é só para risco. O sinal muda apenas no fechamento de cada vela de 4h: 4h é o único timeframe com evidência nos seus testes, e 15m ou 1h não foram testados.

Por moeda, para cada n ∈ {80, 120, 200} (velas de 4h fechadas):

Entra comprado (+1) se fechamento > máxima das n velas anteriores.
Sai do comprado (0) se fechamento < mínima das n/2 velas anteriores.
Vendido (-1) e saída do vendido são o espelho disso.
Recalcule o estado percorrendo as últimas 600 velas, para não depender de estado salvo.
Use exatamente a regra do seu backtest. Se ela for diferente desta, fique com a sua, porque foi ela que bateu os mercados embaralhados.

Agregação:

S = média dos 3 estados, que vai de -1 a +1 em passos de 1/3.
forca = ln(P_t / P_{t-180}) / (vol_4h × √180), o retorno de 30 dias em unidades de vol.
vol_4h = desvio-padrão dos retornos log das últimas 120 velas.
ATR = ATR(20) em 4h.

Ranking: entre os candidatos com S ≠ 0, ordene por |S| e depois por forca × sinal(S). As posições já abertas têm prioridade sobre as novas, para evitar troca de posição sem motivo.

3. Quantas moedas e como dividir
Máximo de 12 posições. Sem mínimo: se só 3 moedas tiverem sinal, o motor fica com 3.
Peso bruto: w_i = S_i × (1 + κ × rank_pct_i) / vol_i, com κ = 1. A moeda mais forte recebe até 2x o peso da mais fraca no mesmo nível de sinal. A rotação para a mais forte acontece aqui, como inclinação.
Normalize para Σ|w| = 1.
Teto por moeda: 25% de G. O excesso é redistribuído uma vez.
Posições abaixo do minNotional são removidas e o peso delas é redistribuído. Com 50 USD, algumas moedas vão ficar de fora, e a mais provável é o BTC, que costuma ter mínimo alto.
4. Alavancagem (CPPI com volatilidade ajustada)

C  = max(E_foguete - piso_foguete, 0)                 # colchão
G  = min( m × C × (σ_ref / σ_cesta),  lev_max × E_foguete )
piso_foguete = 15, m = 20, lev_max = 20, σ_ref = 2,5%/dia.
σ_cesta = vol diária da cesta com Σ|w| = 1, calculada pela covariância EWMA dos retornos de 4h (meia-vida de 30 velas, ×√6 para passar a diário).
Por que CPPI: quando ganha, a alavancagem sobe sozinha (é a sua “escada só com lucro” de forma contínua). Quando perde, encolhe antes do piso. Com 50 USD no foguete, a exposição inicial é 20 × 35 = 700 (14x).
Chance teórica antes dos custos, supondo σ_cesta = 2,5%/dia (meça a sua):
m	P(total ≥ 1000 em 30d)
10	~0,3%
15	~1,5%
20	~2,6%
25	~3,3%

m acima de 20 ganha pouco e aumenta muito o risco de um gap furar o piso.

Margem cruzada na carteira de futuros, que contém só os 50 do foguete.
5. Rotação de lucros

Três mecanismos, sem nada de “vender metade ao bater +X%”:

Ajuste por desvio de peso (no fechamento de 4h): se |notional_atual - alvo| / alvo > 25%, a posição volta ao alvo. A vencedora que cresceu demais é aparada e o lucro realizado vai automaticamente para os pesos novos, que estão inclinados para as mais fortes.
Ajuste do total (a cada 5 min): se |G_atual - G_alvo| / G_alvo > 15%, todas as posições são escaladas na mesma proporção.
Cofre por dobra: quando o total (foguete + cofre) dobrar em relação à última marca (200, 400, 800), transfira 25% do foguete para o cofre, reduzindo as posições proporcionalmente. Isso reduz a P(1000) em uns 30 a 40% relativos, mas aumenta muito a chance de terminar com pelo menos o dobro. Com COFRE_PCT = 0, você roda o foguete puro. Decida com o Monte Carlo.

Por que não realizar parcial em +X%: a tendência vive de poucos ganhos enormes, e realizar cedo corta exatamente esses ganhos. Se o dono insistir, use REALIZA_3R = True (realiza 25% da posição quando o lucro chega a 3 vezes o risco inicial e manda para o cofre), mas deixe desligado por padrão.

6. Proteções
Proteção	Regra
Saída do sinal	A regra do item 2, avaliada no fechamento de 4h
Stop de catástrofe por posição	4 × ATR(4h,20) a partir do melhor preço desde a entrada (stop móvel), checado nos candles de 1 minuto
Reentrada	Só depois de um novo rompimento do horizonte de 80 na mesma direção
Piso do foguete	E_foguete ≤ 15: fecha tudo e encerra (status FIM_PISO). O cofre fica intacto
Margem	Manutenção/E ≥ 50%: reduz tudo pela metade. ≥ 70%: fecha tudo e pausa 4h
Crash	BTC com queda ≥ 6% em 1h, ou mediana do universo com queda ≥ 10% em 1h: sem entradas novas por 4h (o CPPI já reduz a exposição)
Stop diário	Não use. O CPPI já faz isso de forma contínua, e um stop diário só reduz a chance de 10x
Funding	Não abre comprado se funding de 8h > 0,10%, nem vendido se < -0,10%. Se for acima de 0,15% contra a posição, reduz 50%
Dados velhos	Preço com mais de 2 min de atraso: nenhuma ordem nova. Mais de 30 min com posição aberta: fecha tudo
Meta	Total ≥ 1000: fecha tudo e encerra (FIM_META). O estágio 2 começa do zero
Processo único	Arquivo de trava com heartbeat. Só um processo escreve o estado: nada de GitHub Actions e PC rodando juntos
7. Piramidação

Sim, mas só a que já está no desenho:

Cada horizonte que rompe soma 1/3 ao S, então a posição aumenta em degraus conforme a tendência se confirma.
O CPPI aumenta o G conforme o colchão cresce, o que é piramidação no nível da carteira.
Não adicione regras extras de adição (estilo Turtle). Elas não foram testadas e concentram risco numa moeda.
8. Custos e simulação realista no papel
Item	Modelo
Taxa	0,05% do notional por lado (taker)
Slippage	BTC/ETH 0,02%; top 10 0,05%; resto 0,10%; +0,05% em stops; tudo 2x se ATR% > percentil 90
Execução de stop	Se o minuto abriu além do stop: preço de abertura do minuto. Senão: preço do stop. Aplicar slippage depois
Funding	Use a taxa real de premiumIndex em cada nextFundingTime (o intervalo pode variar por moeda). Comprado paga se a taxa for positiva
Arredondamento	Quantidade pelo stepSize. Notional abaixo do minNotional: não executa
Liquidação	A cada minuto, marque todas as posições no pior preço do minuto ao mesmo tempo (mínima nos comprados, máxima nos vendidos). Se o patrimônio nesse cenário ≤ Σ notional × 1%: o foguete vai a zero. É mais conservador que o preço de marcação da Binance, de propósito
9. Avaliação e desligamento

O lucro em 30 dias não prova nada, porque com esta configuração ele é quase pura sorte. Avalie se o motor faz o que o backtest diz.

Dia	Critério	Reprova se
7	Replay: o backtest rodado nos mesmos dados reproduz ≥ 95% dos trades do papel	Diferença de patrimônio > 3% do foguete
7	Vol realizada do colchão entre 0,7x e 1,3x de m × σ_ref	Fora dessa faixa
7	Nenhum bug crítico: posição sem stop, caixa negativo, estado voltando no tempo, ordem duplicada	Qualquer ocorrência
14	Patrimônio total entre o percentil 5 e o 95 do Monte Carlo do mesmo ponto de partida	Abaixo do p5 por 2 semanas seguidas (suspeita de bug ou regime diferente)
14	Custo + funding ≤ 1,3x o modelado	Acima disso
30	Todos os critérios de fidelidade aprovados	A decisão de colocar dinheiro real depende só da fidelidade

Desligamento imediato: FIM_PISO, liquidação, FIM_META, bug crítico ou estado corrompido.

10. Estado (JSON) e pseudocódigo

json
{
  "versao": 1,
  "ciclo_id": 0,
  "atualizado_em": "2026-11-26T03:05:10Z",
  "conta": {
    "caixa_foguete": 50.0, "cofre": 50.0, "piso_foguete": 15.0,
    "ultima_marca_dobra": 100.0, "pico_total": 100.0,
    "taxas_pagas": 0.0, "funding_pago": 0.0,
    "status": "ATIVO", "pausa_ate": null
  },
  "posicoes": {
    "SOLUSDT": {
      "lado": 1, "qtd": 0.85, "preco_entrada": 142.30, "entrada_em": "2026-11-26T00:00:10Z",
      "melhor_preco": 151.20, "stop": 131.60, "atr": 4.90,
      "pnl_realizado": 0.0, "funding_acum": -0.04, "taxas": 0.12
    }
  },
  "sinais": {
    "SOLUSDT": {"barra_4h": "2026-11-26T00:00:00Z", "estados": {"80": 1, "120": 1, "200": 0},
                "S": 0.667, "forca": 1.8, "vol_4h": 0.021, "atr": 4.90,
                "funding_8h": 0.0001, "proximo_funding": "2026-11-26T08:00:00Z"}
  },
  "universo": {"lista": ["BTCUSDT", "ETHUSDT", "SOLUSDT"], "atualizado_em": "2026-11-26T00:05:00Z"},
  "ultima_barra_4h": "2026-11-26T00:00:00Z",
  "ultimo_minuto": "2026-11-26T03:04:00Z",
  "metricas": {"inicio": "2026-11-26T00:00:00Z", "trades": 0, "turnover_usd": 0.0}
}

python
CFG = dict(
    horizontes=(80, 120, 200), max_pos=12, kappa=1.0,
    piso_foguete=15.0, m=20, lev_max=20, sigma_ref=0.025, cap_moeda=0.25,
    banda_G=0.15, banda_peso=0.25, stop_atr=4.0,
    taxa=0.0005, slip={"t1": 0.0002, "t2": 0.0005, "t3": 0.0010}, slip_stop=0.0005, mmr=0.01,
    funding_max=0.0010, funding_corte=0.0015,
    margem_reduz=0.50, margem_zera=0.70, crash_btc_1h=-0.06, crash_mediana_1h=-0.10,
    cofre_pct=0.25, meta_total=1000.0,
)

def ciclo():                                   # agendado a cada 5 min (:00, :05 ... + 10 s)
    with trava("foguete.lock", heartbeat_s=60):
        st = carregar()
        if st.conta.status != "ATIVO":
            return
        agora = utc()
        simbolos = set(st.posicoes) | {"BTCUSDT"}
        k1m = klines_1m(simbolos, desde=st.ultimo_minuto)          # só minutos FECHADOS
        if atraso(k1m, agora) > 120:
            log("DADOS_VELHOS")
            if atraso(k1m, agora) > 1800 and st.posicoes:
                fechar_tudo(st, ultimos_precos(simbolos), "SEM_DADOS")
            salvar(st); return

        # 1) replay minuto a minuto: liquidação -> stops -> funding
        for t in minutos(k1m):
            if liquidaria(st, k1m, t):
                zerar_foguete(st, t); st.conta.status = "LIQUIDADO"; break
            for sym, p in list(st.posicoes.items()):
                c = k1m[sym][t]
                atualizar_melhor_preco_e_stop(p, c, CFG["stop_atr"])
                if stop_atingido(p, c):

                    px = c.open if abriu_alem(p, c) else p.stop
                    fechar(st, sym, px, "STOP", slip_extra=CFG["slip_stop"])
            aplicar_funding_vencido(st, t)
        st.ultimo_minuto = ultimo(k1m)
        if st.conta.status != "ATIVO":
            salvar(st); return

        # 2) marcação e guardas
        px = ultimos_precos(simbolos)
        E = equity_foguete(st, px); T = E + st.conta.cofre
        if E <= CFG["piso_foguete"]:
            fechar_tudo(st, px, "PISO"); st.conta.status = "FIM_PISO"; salvar(st); return
        if T >= CFG["meta_total"]:
            fechar_tudo(st, px, "META"); st.conta.status = "FIM_META"; salvar(st); return
        mr = margem_manutencao(st, px) / E
        if mr >= CFG["margem_zera"]:
            fechar_tudo(st, px, "MARGEM"); st.conta.pausa_ate = agora + horas(4)
        elif mr >= CFG["margem_reduz"]:
            escalar_tudo(st, px, 0.5, "MARGEM")
        if ret_1h("BTCUSDT") <= CFG["crash_btc_1h"] or mediana_ret_1h(st.universo) <= CFG["crash_mediana_1h"]:
            st.conta.pausa_ate = agora + horas(4)

        # 3) cofre por dobra
        if T >= 2 * st.conta.ultima_marca_dobra and CFG["cofre_pct"] > 0:
            valor = CFG["cofre_pct"] * E
            reduzir_proporcional(st, px, valor)                    # vende posições para liberar caixa
            st.conta.caixa_foguete -= valor; st.conta.cofre += valor
            st.conta.ultima_marca_dobra *= 2

        # 4) fechou vela de 4h?
        nova = barra_4h_fechada_desde(st.ultima_barra_4h, agora)
        if nova:

            if passou_00h05_utc(st.universo.atualizado_em, agora):
                st.universo = montar_universo()
            for sym in set(st.universo.lista) | set(st.posicoes):
                st.sinais[sym] = calcular_sinal(sym, klines_4h(sym, 600))
            st.ultima_barra_4h = nova

        # 5) alvos e ordens
        E = equity_foguete(st, px)
        pode_entrar = nova and not pausado(st, agora)
        alvo = calcular_alvos(st, E, px, pode_entrar)
        for o in gerar_ordens(st, alvo, px, nova):
            executar_papel(st, o, px)
        registrar_eventos(st); salvar_atomico(st); publicar_painel(st)

def calcular_sinal(sym, k):
    estados = {n: estado_donchian(k, n, n // 2) for n in CFG["horizontes"]}
    S = sum(estados.values()) / 3
    vol = std(log_ret(k.close)[-120:])
    forca = ln(k.close[-1] / k.close[-181]) / (vol * sqrt(180))
    return dict(estados=estados, S=S, vol_4h=vol, forca=forca, atr=atr(k, 20),
                funding_8h=funding_atual(sym), barra_4h=k.time[-1])

def estado_donchian(k, n, n_saida):
    e = 0
    for t in range(n, len(k)):
        hi = max(k.high[t - n:t]); lo = min(k.low[t - n:t])
        hi_s = max(k.high[t - n_saida:t]); lo_s = min(k.low[t - n_saida:t])
        if e == 0:
            e = 1 if k.close[t] > hi else (-1 if k.close[t] < lo else 0)
        elif e == 1 and k.close[t] < lo_s:
            e = -1 if k.close[t] < lo else 0
        elif e == -1 and k.close[t] > hi_s:

            e = 1 if k.close[t] > hi else 0
    return e

def calcular_alvos(st, E, px, pode_entrar):
    cand = []
    for sym, s in st.sinais.items():
        if s.S == 0:
            continue
        aberta = sym in st.posicoes
        if not aberta and (not pode_entrar or sym not in st.universo.lista or not spread_ok(sym)):
            continue
        if not aberta and bloqueio_funding(s):
            continue
        cand.append(sym)
    cand = ordenar(cand, abertas_primeiro=True, chave=lambda x: (abs(st.sinais[x].S), st.sinais[x].forca * sinal(st.sinais[x].S)))[:CFG["max_pos"]]
    if not cand:
        return {}
    r = rank_pct({x: st.sinais[x].forca * sinal(st.sinais[x].S) for x in cand})
    w = {x: st.sinais[x].S * (1 + CFG["kappa"] * r[x]) / st.sinais[x].vol_4h for x in cand}
    w = normalizar_soma_abs(w)
    sig_cesta = vol_diaria_ewma(w, meia_vida=30)
    C = max(E - CFG["piso_foguete"], 0)
    G = min(CFG["m"] * C * CFG["sigma_ref"] / sig_cesta, CFG["lev_max"] * E)
    alvo = {x: w[x] * G for x in cand}
    alvo = aplicar_teto(alvo, CFG["cap_moeda"] * G)
    alvo = remover_abaixo_minimo(alvo)        # redistribui
    return alvo                               # notional com sinal, em USD

def gerar_ordens(st, alvo, px, nova_barra):
    ordens = []
    atual = {s: p.lado * p.qtd * px[s] for s, p in st.posicoes.items()}
    if nova_barra:

        for s in atual:                                   # 1) saídas e inversões primeiro
            if s not in alvo or sinal(alvo[s]) != sinal(atual[s]):
                ordens.append(fechar_ordem(s))
        for s, a in alvo.items():                         # 2) aparas/aumentos e 3) entradas
            cur = atual.get(s, 0) if s in alvo and sinal(alvo[s]) == sinal(atual.get(s, a)) else 0
            if cur == 0 or abs(a - cur) / abs(a) > CFG["banda_peso"]:
                ordens.append(ajustar_ordem(s, a - cur))
    else:                                                 # fora da vela de 4h: só escala o total
        G_atual = sum(abs(v) for v in atual.values())
        G_alvo = sum(abs(v) for s, v in alvo.items() if s in atual)
        if G_atual > 0 and abs(G_atual - G_alvo) / G_alvo > CFG["banda_G"]:
            f = G_alvo / G_atual
            ordens += [ajustar_ordem(s, v * (f - 1)) for s, v in atual.items()]
    return ordens

def executar_papel(st, o, px):
    tier = tier_slippage(o.sym)
    preco = px[o.sym] * (1 + sinal(o.delta_usd) * CFG["slip"][tier])
    qtd = arredondar_step(abs(o.delta_usd) / preco, o.sym)
    if qtd * preco < min_notional(o.sym):
        return
    taxa = qtd * preco * CFG["taxa"]
    aplicar_fill(st, o.sym, sinal(o.delta_usd) * qtd, preco, taxa)
    inicializar_stop_se_nova(st, o.sym)                  # melhor_preco = preço; stop = preço ∓ 4·ATR

def liquidaria(st, k1m, t):
    eq = st.conta.caixa_foguete; manut = 0.0
    for s, p in st.posicoes.items():
        pior = k1m[s][t].low if p.lado == 1 else k1m[s][t].high
        eq += p.lado * p.qtd * (pior - p.preco_entrada)
        manut += p.qtd * pior * CFG["mmr"]
    return eq <= manut

Antes de ligar:

Rode este mesmo código em modo backtest sobre 2021 a 2026 e confirme se a P(1000) e a P(piso) batem com o seu Monte Carlo.
Ajuste m para o seu σ_cesta real.
Rode num lugar só. O GitHub Actions não garante ciclos de 5 minutos, então use a VM com um timer do systemd.





há 2 minutos
Você usou mais de 90% do seu limite de 5 horas · Redefinição às 01:20Obter mais uso
Responder








O Claude é uma IA e pode cometer erros.
Opus 5.5
 Extra
Auto
O Claude terminou a resposta