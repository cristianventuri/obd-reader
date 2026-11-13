"""Configuração do painel (escalas, faixas de alerta e mostradores exibidos), guardada num arquivo JSON."""
import copy
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

# Mesmos nomes e ordem dos mostradores de leitor/estatico/indicadores.js.
MOSTRADORES = ("velocidade", "rpm", "turbo", "temp_motor", "tanque")
CENTROS_DA_ROTACAO = ("consumo", "esforco")
CENTROS_DO_TANQUE = ("litros", "etanol")
# Números da escala: só nas marcas principais ou também nas intermediárias, intercalados.
NUMEROS_DA_ESCALA = ("principais", "intercalados")

PADRAO = {
    "mostradores": list(MOSTRADORES),  # os exibidos, na ordem em que aparecem
    # km/h; faixas amarela e vermelha
    "velocidade": {"maximo": 200, "atencao": 100, "perigo": 120, "numeros": "principais"},
    "rpm": {"maximo": 8000, "atencao": 5500, "perigo": 6500, "centro": "consumo", "numeros": "principais"},
    "tanque": {"capacidade_l": 52, "centro": "litros"},
}


class ErroConfig(ValueError):
    """Configuração recusada; a mensagem diz o motivo e aparece na tela."""


def mesclar(base: dict, novo: dict, caminho: str = "") -> dict:
    """Copia `base` aplicando `novo`, aceitando só chaves conhecidas e com o mesmo tipo."""
    resultado = copy.deepcopy(base)
    for chave, valor in novo.items():
        nome = caminho + chave
        if chave not in base:
            raise ErroConfig(f"chave desconhecida: {nome}")
        atual = base[chave]
        if isinstance(atual, dict):
            if not isinstance(valor, dict):
                raise ErroConfig(f"{nome} deveria ser um objeto")
            resultado[chave] = mesclar(atual, valor, nome + ".")
        elif isinstance(atual, list):
            if not isinstance(valor, list):
                raise ErroConfig(f"{nome} deveria ser uma lista")
            resultado[chave] = copy.deepcopy(valor)
        elif isinstance(atual, (int, float)):
            if isinstance(valor, bool) or not isinstance(valor, (int, float)):
                raise ErroConfig(f"{nome} deveria ser um número")
            resultado[chave] = valor
        elif not isinstance(valor, str):
            raise ErroConfig(f"{nome} deveria ser um texto")
        else:
            resultado[chave] = valor
    return resultado


def _mostradores_validos(mostradores: list) -> bool:
    return (len(mostradores) >= 1 and len(set(mostradores)) == len(mostradores)
            and all(isinstance(chave, str) and chave in MOSTRADORES for chave in mostradores))


def validar(config: dict) -> None:
    vel, rpm, tanque = config["velocidade"], config["rpm"], config["tanque"]
    regras = [
        # a escala é numerada a partir do máximo: com ele redondo, o último número fica redondo também
        (100 <= vel["maximo"] <= 400 and vel["maximo"] % 10 == 0,
         "o máximo do velocímetro precisa ficar entre 100 e 400 km/h, de 10 em 10"),
        (0 < vel["atencao"] < vel["perigo"] <= vel["maximo"],
         "no velocímetro, o amarelo precisa começar antes do vermelho, e o vermelho até o máximo da escala"),
        (4000 <= rpm["maximo"] <= 10000 and rpm["maximo"] % 1000 == 0,
         "o máximo da rotação precisa ficar entre 4000 e 10000 rpm, de 1000 em 1000"),
        (0 < rpm["atencao"] < rpm["perigo"] <= rpm["maximo"],
         "na rotação, o amarelo precisa começar antes do vermelho, e o vermelho até o máximo da escala"),
        (rpm["centro"] in CENTROS_DA_ROTACAO, f"o centro da rotação precisa ser {' ou '.join(CENTROS_DA_ROTACAO)}"),
        (vel["numeros"] in NUMEROS_DA_ESCALA and rpm["numeros"] in NUMEROS_DA_ESCALA,
         f"os números da escala precisam ser {' ou '.join(NUMEROS_DA_ESCALA)}"),
        (20 <= tanque["capacidade_l"] <= 150, "a capacidade do tanque precisa ficar entre 20 e 150 litros"),
        (tanque["centro"] in CENTROS_DO_TANQUE, f"o centro do tanque precisa ser {' ou '.join(CENTROS_DO_TANQUE)}"),
        (_mostradores_validos(config["mostradores"]),
         f"escolha ao menos um mostrador, sem repetir, entre: {', '.join(MOSTRADORES)}"),
    ]
    for ok, mensagem in regras:
        if not ok:
            raise ErroConfig(mensagem)


def atualizar(config: dict, alteracoes: object) -> dict:
    """Configuração nova com as alterações aplicadas; recusa tudo se algo não valer."""
    if not isinstance(alteracoes, dict):
        raise ErroConfig("as alterações precisam ser um objeto JSON")
    novo = mesclar(config, alteracoes)
    validar(novo)
    return novo


def carregar(caminho: Path) -> dict:
    """Lê o arquivo; sem ele, ou com ele estragado, segue com o padrão para o painel não deixar de abrir no carro."""
    if not caminho.exists():
        return copy.deepcopy(PADRAO)
    try:
        return atualizar(PADRAO, json.loads(caminho.read_text(encoding="utf-8")))
    except (ErroConfig, json.JSONDecodeError) as erro:
        log.warning("configuração em %s ignorada (%s); usando o padrão", caminho, erro)
        return copy.deepcopy(PADRAO)


def salvar(caminho: Path, config: dict) -> None:
    """Grava num arquivo temporário e troca de uma vez: desligar o carro no meio não deixa o JSON pela metade."""
    temporario = caminho.with_name(caminho.name + ".tmp")
    temporario.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporario.replace(caminho)
