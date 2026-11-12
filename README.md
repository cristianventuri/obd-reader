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

Os nomes e as unidades estão em `PIDS` ([leitor/obd.py](leitor/obd.py)). Os casos de [tests/vetores.json](tests/vetores.json) (respostas e comandos permitidos ou proibidos) servem para validar outras implementações, como a do ESP32.
