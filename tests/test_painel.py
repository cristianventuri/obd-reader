import asyncio
import json

import pytest

from leitor import config as cfg
from leitor.coleta import Leitura
from leitor.painel import TAMANHO_FILA, Painel


def _dados(quadro: str) -> dict:
    return json.loads(quadro.split("data: ", 1)[1])


def test_publicar_nao_bloqueia_com_navegador_lento():
    painel = Painel("127.0.0.1", 0)
    fila = asyncio.Queue(maxsize=TAMANHO_FILA)
    painel._clientes.add(fila)
    for i in range(TAMANHO_FILA + 50):
        painel.publicar(Leitura(float(i), {"rpm": float(i)}))
    assert fila.qsize() == TAMANHO_FILA
    assert _dados(fila.get_nowait())["rpm"] == 50.0


def test_estado_acumula_o_ultimo_valor_de_cada_dado():
    painel = Painel("127.0.0.1", 0)
    painel.publicar(Leitura(1.0, {"rpm": 900.123, "velocidade_kmh": 0}))
    painel.publicar(Leitura(2.0, {"marcha": "N"}))
    assert painel._estado == {"t": 2.0, "rpm": 900.12, "velocidade_kmh": 0, "marcha": "N"}


def test_alterar_config_grava_e_avisa_as_telas(tmp_path):
    caminho = tmp_path / "config.json"
    painel = Painel("127.0.0.1", 0, caminho)
    fila = asyncio.Queue(maxsize=TAMANHO_FILA)
    painel._clientes.add(fila)
    painel.alterar_config({"velocidade": {"maximo": 240}})
    quadro = fila.get_nowait()
    assert quadro.startswith("event: config\n")
    assert _dados(quadro)["velocidade"]["maximo"] == 240
    assert cfg.carregar(caminho)["velocidade"]["maximo"] == 240


def test_config_invalida_nao_muda_nada(tmp_path):
    caminho = tmp_path / "config.json"
    painel = Painel("127.0.0.1", 0, caminho)
    fila = asyncio.Queue(maxsize=TAMANHO_FILA)
    painel._clientes.add(fila)
    with pytest.raises(cfg.ErroConfig):
        painel.alterar_config({"velocidade": {"perigo": 500}})
    assert painel.config == cfg.PADRAO
    assert fila.empty()
    assert not caminho.exists()
