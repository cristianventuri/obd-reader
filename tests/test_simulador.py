import asyncio
from contextlib import aclosing

from leitor.coleta import Leitura
from leitor.obd import LEITURAS_UDS, PIDS
from leitor.simulador import DURACAO_ROTEIRO_S, Simulador


def _nomes_do_carro() -> set[str]:
    """Todo nome que a leitura real pode trazer: PIDs (inclusive os que viram vários valores) e leituras UDS."""
    nomes = {leitura.nome for leitura in LEITURAS_UDS.values()}
    for nome, tamanho, conversao in PIDS.values():
        valor = conversao(*[0] * tamanho)
        nomes |= set(valor) if isinstance(valor, dict) else {nome}
    return nomes


def _uma_volta() -> list[Leitura]:
    async def ler() -> list[Leitura]:
        leituras = []
        async with aclosing(Simulador(intervalo_s=0).ler()) as gerador:
            async for leitura in gerador:
                if leitura.t > DURACAO_ROTEIRO_S:
                    return leituras
                leituras.append(leitura)
        return leituras
    return asyncio.run(ler())


def test_simulador_traz_exatamente_os_dados_do_carro():
    # dado novo nas tabelas sem simulação (ou nome inventado no simulador) quebra aqui
    recebidos = set().union(*(leitura.valores for leitura in _uma_volta()))
    assert recebidos == _nomes_do_carro()


def test_trajeto_passa_por_todo_o_cambio_e_estacionado_acompanha_p_e_n():
    marchas = set()
    for leitura in _uma_volta():
        valores = leitura.valores
        if "marcha" not in valores:
            continue
        marchas.add(valores["marcha"])
        if valores["marcha"] in ("P", "N"):
            assert valores["estacionado"] == (valores["marcha"] == "P")
        else:
            assert "estacionado" not in valores
    assert marchas == {"P", "R", "N", "1", "2", "3", "4", "5", "6"}


def test_leituras_parciais_em_ordem_como_no_coletor():
    leituras = _uma_volta()
    assert all(antes.t <= depois.t for antes, depois in zip(leituras, leituras[1:]))
    # rápidos chegam sozinhos a cada ciclo; os lentos vêm em blocos separados
    assert "rpm" in leituras[0].valores and "temp_motor_c" not in leituras[0].valores
