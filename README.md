# obd-leitor

Lê dados OBD-II de um adaptador ELM327 Bluetooth LE e imprime cada resposta no terminal. Opcionalmente, mostra os indicadores num painel web em tempo real.

## Somente leitura

Todo comando passa por `exigir_somente_leitura` ([leitor/obd.py](leitor/obd.py)) dentro de `Elm327.enviar`, o único ponto que escreve no Bluetooth. Só podem sair leituras de dados (os itens das tabelas `PIDS` e `LEITURAS_UDS`) e os comandos de configuração do próprio ELM327. Qualquer outro comando é recusado antes de sair, e o programa encerra. O painel só recebe dados; ele não envia nada ao carro.

## Rodar

Requer Python 3.12+ e Bluetooth ativo. Na primeira execução, o `iniciar.sh` cria o ambiente e instala as dependências.

```bash
./iniciar.sh                                        # busca e escolha do adaptador, saída no terminal
./iniciar.sh --endereco AA:BB:CC:DD:EE:FF           # direto, sem busca
./iniciar.sh --endereco AA:BB:CC:DD:EE:FF --json > leituras.jsonl
./iniciar.sh --painel                               # terminal + painel em http://localhost:8080
./iniciar.sh --painel --host 0.0.0.0                # painel acessível por outros aparelhos da rede
```

As demais opções (dados lidos, frequência, porta do painel) aparecem em `./iniciar.sh --help`.

## Saída

Cada linha corresponde a uma resposta do carro e traz só os valores dela. `t` é o tempo em segundos desde o início. Logs e status vão para o stderr.

```
   12.345  rpm=850.0 velocidade_kmh=0
{"t":12.345,"rpm":850.0,"velocidade_kmh":0}
```

Os nomes, as unidades e as fórmulas de cada valor estão em [leitor/obd.py](leitor/obd.py).

## Painel

Com `--painel`, o leitor também serve uma página ([leitor/estatico/](leitor/estatico/)) que recebe as leituras por SSE (`/leituras`) e mostra os indicadores. Os cartões exibidos ficam na lista `INDICADORES` de [painel.js](leitor/estatico/painel.js). Um cartão sem atualização há 10 s fica esmaecido. Se o leitor reiniciar, a página reconecta sozinha.

## Testes

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest
```

Os casos de [tests/vetores.json](tests/vetores.json) (respostas e comandos permitidos ou proibidos) servem para validar outras implementações, como a de um microcontrolador.
