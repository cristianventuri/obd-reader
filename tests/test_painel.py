import asyncio
import json

from leitor.coleta import Leitura
from leitor.painel import TAMANHO_FILA, Painel


def test_publicar_nao_bloqueia_com_navegador_lento():
    painel = Painel("127.0.0.1", 0)
    fila = asyncio.Queue(maxsize=TAMANHO_FILA)
    painel._clientes.add(fila)
    for i in range(TAMANHO_FILA + 50):
        painel.publicar(Leitura(float(i), {"rpm": float(i)}))
    assert fila.qsize() == TAMANHO_FILA
    assert json.loads(fila.get_nowait())["rpm"] == 50.0


def test_estado_acumula_o_ultimo_valor_de_cada_dado():
    painel = Painel("127.0.0.1", 0)
    painel.publicar(Leitura(1.0, {"rpm": 900.123, "velocidade_kmh": 0}))
    painel.publicar(Leitura(2.0, {"marcha": "N"}))
    assert painel._estado == {"t": 2.0, "rpm": 900.12, "velocidade_kmh": 0, "marcha": "N"}
