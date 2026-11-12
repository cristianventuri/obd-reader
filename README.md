# obd-leitor

Lê dados OBD-II de um adaptador ELM327 BLE e imprime cada resposta do carro no terminal.

## Somente leitura

Todo comando passa por `exigir_somente_leitura` ([leitor/obd.py](leitor/obd.py)) dentro de `Elm327.enviar`, o único ponto que escreve no Bluetooth. Só podem sair:

- leituras do **modo 01** com até 6 PIDs da tabela `PIDS`;
- os comandos de configuração do ELM327 `ATZ ATE0 ATL0 ATS0 ATH0 ATSPx ATSHxxx`.

Qualquer outro comando (limpar códigos, UDS, reset etc.) é recusado antes de sair, e o programa encerra. O `ATSP` grava o protocolo padrão **no adaptador**, não no carro.

## Rodar com Docker (Linux)

O container usa o Bluetooth do host pelo D-Bus. Requer BlueZ ativo (`systemctl status bluetooth`).

```bash
docker compose run --rm --build leitor                       # busca e escolha do adaptador
docker compose run --rm leitor --endereco 00:10:CC:4F:36:03  # direto, sem busca
docker compose run --rm -T leitor --endereco 00:10:CC:4F:36:03 --json > leituras.jsonl
docker compose run --rm --build testes                       # testes
```

O `-T` desliga o terminal virtual e mantém o stdout limpo, só com dados. O Docker Desktop (macOS/Windows) não dá acesso ao Bluetooth. Nesses sistemas, rode com Python.

## Rodar com Python

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m leitor --help
.venv/bin/pytest
```

## Saída

Cada linha corresponde a uma resposta do carro e traz só os valores dela. `t` é o tempo em segundos desde o início. Logs e status vão para o stderr.

```
   12.345  rpm=979.0 velocidade_kmh=0 carga_absoluta_pct=18.43 lambda_comandado=1.0 map_kpa=36
{"t":12.345,"rpm":979.0,"velocidade_kmh":0,"carga_absoluta_pct":18.43,"lambda_comandado":1.0,"map_kpa":36}
```

Os casos de [tests/vetores.json](tests/vetores.json) (respostas e comandos permitidos ou proibidos) servem para validar outras implementações, como a do ESP32.

## Valores retornados

`A`, `B`, `C`… são os bytes da resposta, na ordem. A tabela completa fica em `PIDS` ([leitor/obd.py](leitor/obd.py)).

### Rápidos (lidos em todo ciclo)

| Chave | PID | O que é | Unidade | Fórmula |
|---|---|---|---|---|
| `rpm` | 0C | Rotação do motor | rpm | (256A+B)/4 |
| `velocidade_kmh` | 0D | Velocidade do veículo | km/h | A |
| `carga_absoluta_pct` | 43 | Massa de ar admitida em relação à cilindrada; passa de 100% com o turbo | % | (256A+B)·100/255 |
| `lambda_comandado` | 44 | Mistura pedida pela ECU: 1 = ideal, < 1 = rica, > 1 = pobre | — | (256A+B)·2/65536 |
| `map_kpa` | 0B | Pressão absoluta no coletor de admissão | kPa | A |

### Lentos (em rodízio, um bloco de até 6 PIDs a cada `--a-cada` ciclos)

| Chave | PID | O que é | Unidade | Fórmula |
|---|---|---|---|---|
| `temp_motor_c` | 05 | Temperatura do líquido de arrefecimento | °C | A−40 |
| `temp_ar_c` | 0F | Temperatura do ar admitido | °C | A−40 |
| `temp_ambiente_c` | 46 | Temperatura ambiente | °C | A−40 |
| `tanque_pct` | 2F | Nível de combustível | % | A·100/255 |
| `tensao_v` | 42 | Tensão de alimentação da ECU (bateria/alternador) | V | (256A+B)/1000 |
| `barometrica_kpa` | 33 | Pressão atmosférica | kPa | A |
| `pressao_turbo_kpa` | 70 | Pressão absoluta do turbo; `null` se o carro não informar | kPa | (256D+E)/32, se o bit 1 de A estiver ligado |
| `avanco_graus` | 0E | Avanço de ignição antes do PMS | ° | A/2−64 |
| `borboleta_pct` | 11 | Abertura da borboleta | % | A·100/255 |
| `pedal_pct` | 49 | Posição do pedal do acelerador | % | A·100/255 |
| `carga_calculada_pct` | 04 | Carga do motor calculada pela ECU | % | A·100/255 |
| `temp_catalisador_c` | 3C | Temperatura do catalisador (banco 1, sensor 1) | °C | (256A+B)/10−40 |
| `luz_injecao` | 01 | Luz de injeção acesa | bool | bit 7 de A |
| `codigos_falha` | 01 | Quantidade de códigos de falha armazenados | — | A & 0x7F |
| `ajuste_curto_pct` | 06 | Correção instantânea de combustível; positivo = ECU adicionando | % | (A−128)·100/128 |
| `ajuste_longo_pct` | 07 | Correção aprendida de combustível | % | (A−128)·100/128 |
| `lambda_sonda` | 34 | Mistura medida pela sonda lambda de banda larga | — | (256A+B)·2/65536 |
| `tempo_motor_s` | 1F | Tempo desde a partida | s | 256A+B |
| `km_desde_limpeza` | 31 | Distância desde que os códigos de falha foram apagados | km | 256A+B |
| `etanol_pct` | 52 | Percentual de etanol no combustível | % | A·100/255 |

## Outros dados disponíveis

Varredura feita no Polo 1.0 TSI em 31/10/2026, na ECU do motor. Ainda não estão na tabela `PIDS`; para ler, é preciso incluí-los lá.

| PID | O que é |
|---|---|
| 15 | Sonda lambda pós-catalisador: tensão e ajuste |
| 45 | Posição relativa da borboleta |
| 47 | Posição absoluta da borboleta B |
| 4A | Posição do pedal E (sensor redundante) |
| 4C | Abertura de borboleta comandada pela ECU |
| 2E | Purga do cânister comandada |
| 56 | Ajuste de longo prazo da sonda secundária |
| 67 | Temperatura do arrefecimento (até 2 sensores) |
| 68 | Temperatura do ar admitido (vários sensores) |
| 6D | Sistema de pressão de combustível: pressão do rail da injeção direta |
| 21 | Distância rodada com a luz de injeção acesa |
| 30 | Aquecimentos do motor desde que os códigos foram apagados |
| 03 | Estado do sistema de combustível (malha aberta/fechada) |
| 41 | Estado dos monitores de diagnóstico no ciclo atual |
| 13 / 1C / 51 / 93 | Sondas presentes, norma OBD, tipo de combustível, contadores WWH-OBD |

**Não existem nesse carro:** fluxo de ar (10), consumo instantâneo (5E/9D/A2), temperatura do óleo (5C), marcha engatada (A4) e hodômetro (A6).

### Outros modos (também só leitura, mas hoje bloqueados)

A regra de somente leitura libera apenas o modo 01. Os modos abaixo também só leem, mas precisam ser incluídos em `exigir_somente_leitura`. O modo 04 (apagar códigos) nunca deve entrar.

| Modo | O que lê |
|---|---|
| 03 / 07 / 0A | Códigos de falha armazenados, pendentes e permanentes (ex.: P0301) |
| 02 | Quadro congelado: valores dos sensores no momento da falha |
| 09 | Chassi (VIN), calibração e nome da ECU |
| 22 (UDS) | Dados próprios da VW (óleo, marcha, hodômetro…); os IDs não são públicos e nunca foram testados nesse carro |
