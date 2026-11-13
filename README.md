# obd-leitor

Lê dados OBD-II de um adaptador ELM327 Bluetooth LE e imprime cada resposta no terminal. Opcionalmente, mostra os indicadores num painel web em tempo real.

## Somente leitura

Todo comando passa por `exigir_somente_leitura` ([leitor/obd.py](leitor/obd.py)) dentro de `Elm327.enviar`, o único ponto que escreve no Bluetooth. Só podem sair leituras de dados (os itens das tabelas `PIDS` e `LEITURAS_UDS`) e os comandos de configuração do próprio ELM327. Qualquer outro comando é recusado antes de sair, e o programa encerra. O painel não envia nada ao carro: além das leituras, ele só troca com o navegador a própria configuração. O simulador nem abre o Bluetooth.

## Rodar

Requer Python 3.12+ e Bluetooth ativo. Na primeira execução, o `iniciar.sh` cria o ambiente e instala as dependências.

```bash
./iniciar.sh                                        # busca e escolha do adaptador, saída no terminal
./iniciar.sh --endereco AA:BB:CC:DD:EE:FF           # direto, sem busca
./iniciar.sh --endereco AA:BB:CC:DD:EE:FF --json > leituras.jsonl
./iniciar.sh --painel                               # terminal + painel em http://localhost:8080
./iniciar.sh --painel --host 0.0.0.0                # painel acessível por outros aparelhos da rede
./iniciar.sh --simulador --painel                   # dados simulados, sem carro nem adaptador
```

As demais opções (dados lidos, frequência, porta do painel) aparecem em `./iniciar.sh --help`.

## Saída

Cada linha corresponde a uma resposta do carro e traz só os valores dela. `t` é o tempo em segundos desde o início. Logs e status vão para o stderr.

```
   12.345  rpm=850.0 velocidade_kmh=0
{"t":12.345,"rpm":850.0,"velocidade_kmh":0}
```

Os nomes, as unidades e as fórmulas de cada valor estão em [leitor/obd.py](leitor/obd.py). A lista completa está em [Dados disponíveis](#dados-disponíveis).

## Dados disponíveis

Todos chegam ao painel e podem ser exibidos. Para mostrar um deles, use a chave como `campo` de um mostrador em `DEFINICOES` ([indicadores.js](leitor/estatico/indicadores.js)), ou no `miolo` de um que já existe.

Na coluna Leitura, **rápido** quer dizer lido em todo ciclo. **Lento** quer dizer lido em rodízio, num bloco de até 6 PIDs a cada `--a-cada` ciclos. Para mudar um dado de grupo, passe o PID dele em `--rapidos` ou `--lentos`.

| Chave | O que é | Unidade | PID | Leitura | No painel |
|---|---|---|---|---|---|
| `velocidade_kmh` | Velocidade do carro | km/h | 0D | rápido | agulha da Velocidade |
| `rpm` | Rotação do motor | rpm | 0C | rápido | agulha da Rotação |
| `carga_absoluta_pct` | Esforço do motor: ar admitido em relação ao máximo sem turbo; passa de 100% com o turbo | % | 43 | rápido | cálculo do consumo |
| `map_kpa` | Pressão absoluta no coletor de admissão | kPa | 0B | rápido | agulha do Turbo |
| `lambda_comandado` | Mistura pedida pela injeção: 1 = ideal, < 1 = rica (mais combustível), > 1 = pobre | λ | 44 | rápido | cálculo do consumo |
| `marcha` | Marcha engatada: `1` a `6` em D, `R`, `N` ou `P` (`P/N` enquanto o câmbio não respondeu) | — | UDS 22 14CB | a cada 2 ciclos | centro da Velocidade |
| `estacionado` | Alavanca em P (`true`) ou fora dela; lido só parado em P ou N | — | UDS 22 104B (câmbio) | só em P/N | separa P de N na marcha |
| `temp_motor_c` | Temperatura do motor (água do radiador) | °C | 05 | lento | agulha do Motor |
| `temp_ar_c` | Temperatura do ar que entra no motor | °C | 0F | lento | centro do Motor |
| `temp_ambiente_c` | Temperatura do ar externo | °C | 46 | lento | — |
| `tanque_pct` | Nível de combustível | % | 2F | lento | agulha do Tanque e litros no centro |
| `etanol_pct` | Etanol no combustível | % | 52 | lento | centro do Tanque (se configurado) e cálculo do consumo |
| `pedal_pct` | Quanto o acelerador está pisado | % | 49 | lento | centro do Turbo |
| `barometrica_kpa` | Pressão atmosférica | kPa | 33 | lento | desconta a pressão do ar no Turbo |
| `tensao_v` | Tensão da bateria e do alternador vista pela injeção | V | 42 | lento | — |
| `pressao_turbo_kpa` | Pressão absoluta medida no turbo; `null` se o carro não informar | kPa | 70 | lento | — |
| `borboleta_pct` | Abertura da borboleta | % | 11 | lento | — |
| `carga_calculada_pct` | Carga do motor calculada pela injeção, de 0 a 100% | % | 04 | lento | — |
| `avanco_graus` | Avanço de ignição antes do ponto morto superior | ° | 0E | lento | — |
| `temp_catalisador_c` | Temperatura do catalisador | °C | 3C | lento | — |
| `lambda_sonda` | Mistura medida pela sonda lambda (mesma escala do `lambda_comandado`) | λ | 34 | lento | — |
| `ajuste_curto_pct` | Correção instantânea de combustível; positivo = injeção adicionando | % | 06 | lento | — |
| `ajuste_longo_pct` | Correção de combustível aprendida pela injeção | % | 07 | lento | — |
| `luz_injecao` | Luz de injeção acesa | sim/não | 01 | lento | — |
| `codigos_falha` | Quantidade de códigos de falha guardados | — | 01 | lento | — |
| `tempo_motor_s` | Tempo desde a partida | s | 1F | lento | — |
| `km_desde_limpeza` | Distância desde que os códigos de falha foram apagados | km | 31 | lento | — |

O painel também calcula valores a partir desses dados:

| Chave | O que é | Unidade | No painel |
|---|---|---|---|
| `consumo_kml` | Consumo andando, suavizado em 4 s; `null` abaixo de 5 km/h | km/l | centro da Rotação (se configurado), andando |
| `consumo_lh` | Combustível gasto por hora, suavizado em 4 s | L/h | centro da Rotação (se configurado), parado |
| — | Pressão do turbo: (`map_kpa` − `barometrica_kpa`) / 100 | bar | agulha do Turbo |
| — | Litros no tanque: `tanque_pct` × capacidade do tanque (configuração) | L | centro do Tanque (se configurado) |

O carro não informa consumo nem fluxo de ar. O consumo é estimado pela massa de ar que entra no motor: rotação, carga absoluta e cilindrada dão o ar; a mistura pedida e o % de etanol dão o combustível. É o mesmo cálculo do projeto odb-scanner, em [leitor/consumo.py](leitor/consumo.py), onde ficam a cilindrada e o fator de calibração. O servidor do painel faz a conta e manda `consumo_kml` e `consumo_lh` junto das leituras; a saída no terminal continua só com o que o carro respondeu.


## Painel

Com `--painel`, o leitor também serve uma página ([leitor/estatico/](leitor/estatico/)) que recebe as leituras por SSE (`/leituras`) e mostra os indicadores. Cada indicador é um mostrador redondo de 422×422, o tamanho de uma tela AMOLED redonda de 1,75". No desenho, uma unidade do SVG equivale a um pixel da tela. O fundo é preto puro, porque no AMOLED pixel preto fica apagado.

## Simulador

`--simulador` troca o carro por um trajeto fictício de 80 s em loop: estaciona, dá ré, sai pela cidade, arranca com pé no fundo (turbo cheio e giro na faixa vermelha), segue na estrada e estaciona de novo, enquanto o motor aquece. As leituras saem no mesmo formato e no mesmo ritmo do carro: os dados rápidos a cada ciclo e a marcha e os lentos em rodízio. Por isso a saída no terminal, o `--json` e o painel funcionam iguais. As opções do adaptador são ignoradas. O trajeto e os valores ficam em [leitor/simulador.py](leitor/simulador.py).

## Testes

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

Os casos de [tests/vetores.json](tests/vetores.json) (respostas e comandos permitidos ou proibidos) servem para validar outras implementações, como a de um microcontrolador.
