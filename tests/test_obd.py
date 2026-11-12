import asyncio
import inspect
import json
from pathlib import Path

import pytest

from leitor import elm327, obd
from leitor.coleta import Coletor
from leitor.elm327 import Elm327, ErroAdaptador, comandos_de_configuracao
from leitor.obd import (LEITURAS_UDS, MARCHA, ComandoProibido, exigir_somente_leitura, ler_resposta, ler_uds,
                        montar_consultas)

VETORES = json.loads((Path(__file__).parent / "vetores.json").read_text())


def _aproximado(esperado: dict) -> dict:
    return {nome: pytest.approx(valor, abs=0.01) if isinstance(valor, float) else valor
            for nome, valor in esperado.items()}


@pytest.mark.parametrize("vetor", VETORES["respostas"], ids=lambda v: v["caso"])
def test_respostas(vetor):
    if "erro" in vetor:
        with pytest.raises(getattr(obd, vetor["erro"])):
            ler_resposta(vetor["linhas"])
    else:
        assert ler_resposta(vetor["linhas"]) == _aproximado(vetor["esperado"])


@pytest.mark.parametrize("vetor", VETORES["respostas_uds"], ids=lambda v: v["caso"])
def test_respostas_uds(vetor):
    leitura = LEITURAS_UDS[vetor["comando"]]
    if "erro" in vetor:
        with pytest.raises(getattr(obd, vetor["erro"])):
            ler_uds(vetor["linhas"], leitura)
    else:
        assert ler_uds(vetor["linhas"], leitura) == vetor["esperado"]


def _coletor_com_marcha() -> Coletor:
    return Coletor("00:00:00:00:00:00", "6", "7E0", [0x0C], [0x05], 3, leituras_uds=(MARCHA,))


def test_marcha_a_cada_dois_ciclos_com_contagem():
    coletor = _coletor_com_marcha()
    coletor._sufixo = "1"
    comandos = [[c.comando for c in coletor._consultas_do_ciclo(ciclo)] for ciclo in (1, 2, 3)]
    assert comandos == [["010C1"], ["010C1", "2214CB1"], ["010C1", "01051"]]


class _ElmQueEsgota:
    conectado = True

    async def enviar(self, comando, timeout=2.0):
        raise ErroAdaptador(f"sem resposta para {comando}")


def test_timeout_isolado_nao_derruba_a_leitura():
    coletor = _coletor_com_marcha()
    consulta = coletor._consultas_do_ciclo(2)[1]
    assert asyncio.run(coletor._consultar(_ElmQueEsgota(), consulta)) == {}


@pytest.mark.parametrize("comando", VETORES["comandos"]["permitidos"])
def test_comandos_permitidos(comando):
    exigir_somente_leitura(comando)


@pytest.mark.parametrize("comando", VETORES["comandos"]["proibidos"])
def test_comandos_proibidos(comando):
    with pytest.raises(ComandoProibido):
        exigir_somente_leitura(comando)


def test_montar_consultas_divide_em_blocos_de_seis():
    assert montar_consultas([0x0C, 0x0D, 0x43, 0x44, 0x0B, 0x05, 0x0F]) == ["010C0D43440B05", "010F"]


def test_montar_consultas_recusa_pid_fora_da_tabela():
    with pytest.raises(ValueError, match="99"):
        montar_consultas([0x0C, 0x99])


def test_tudo_que_o_leitor_gera_e_permitido():
    padrao = [0x0C, 0x0D, 0x43, 0x44, 0x0B, 0x05, 0x0F, 0x46, 0x2F, 0x42, 0x33, 0x70]
    for comando in ["ATZ", *comandos_de_configuracao("6", "7E0"), *montar_consultas(list(obd.PIDS)),
                    *(consulta + "1" for consulta in montar_consultas(padrao)), *LEITURAS_UDS]:
        exigir_somente_leitura(comando)


class _ClienteFalso:
    is_connected = True

    def __init__(self):
        self.escritas = []

    async def write_gatt_char(self, caracteristica, dados, response=None):
        self.escritas.append(dados)


@pytest.mark.parametrize("comando", ["04", "1101", "ATMA"])
def test_enviar_recusa_antes_de_escrever(comando):
    elm = Elm327("00:00:00:00:00:00")
    elm._cliente = _ClienteFalso()
    with pytest.raises(ComandoProibido):
        asyncio.run(elm.enviar(comando))
    assert elm._cliente.escritas == []


def test_escrita_no_ble_so_existe_dentro_de_enviar():
    assert inspect.getsource(elm327).count("write_gatt_char") == 1
    assert "write_gatt_char" in inspect.getsource(Elm327.enviar)
