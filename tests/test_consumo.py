import pytest

from leitor.consumo import Consumo, litros_por_hora


def test_consumo_em_valores_plausiveis_para_1_0_tsi():
    # marcha lenta medida no Polo: 979 rpm, carga absoluta 18,4%, λ 1,0, 35,7% de etanol
    assert litros_por_hora(979, 18.4, 1.0, 35.7, 0.999) == pytest.approx(0.66, abs=0.05)
    # motor pequeno turbinado roda com carga alta em cruzeiro: ~65% a 80 km/h
    cruzeiro = litros_por_hora(2000, 65, 1.0, 27, 0.999)
    assert 14 < 80 / cruzeiro < 20
    # etanol queima mais litros para o mesmo ar; mistura rica (λ < 1) também
    assert litros_por_hora(2000, 65, 1.0, 100, 0.999) > cruzeiro
    assert litros_por_hora(2000, 65, 0.85, 27, 0.999) > cruzeiro
    assert litros_por_hora(2000, 65, 1.0, 27, 0.999, fator_calibracao=1.1) == pytest.approx(cruzeiro * 1.1)


def _estado(**valores):
    return {"rpm": 2000, "velocidade_kmh": 80, "carga_absoluta_pct": 65, "lambda_comandado": 1.0,
            "etanol_pct": 27} | valores


def test_km_por_litro_andando_e_so_litros_por_hora_parado():
    andando = Consumo().atualizar(_estado(), 0)
    assert 14 < andando["consumo_kml"] < 20
    parado = Consumo().atualizar(_estado(rpm=979, velocidade_kmh=0, carga_absoluta_pct=18.4), 0)
    assert parado["consumo_kml"] is None
    assert parado["consumo_lh"] == pytest.approx(0.66, abs=0.1)


def test_suaviza_a_arrancada():
    consumo = Consumo()
    consumo.atualizar(_estado(), 0)
    pico = consumo.atualizar(_estado(rpm=5000, carga_absoluta_pct=150, lambda_comandado=0.85), 0.5)
    assert litros_por_hora(2000, 65, 1.0, 27, 0.999) < pico["consumo_lh"] < litros_por_hora(5000, 150, 0.85, 27, 0.999)


def test_motor_desligado_zera_na_hora_e_falta_de_dado_nao_calcula():
    consumo = Consumo()
    consumo.atualizar(_estado(), 0)
    desligado = consumo.atualizar(_estado(rpm=0, velocidade_kmh=0, carga_absoluta_pct=0), 1)
    assert desligado == {"consumo_lh": 0, "consumo_kml": None}
    assert Consumo().atualizar({"rpm": 900}, 0) is None
