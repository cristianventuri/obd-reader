import json

import pytest

from leitor import config as cfg


def test_padrao_e_valido():
    cfg.validar(cfg.PADRAO)


@pytest.mark.parametrize("alteracoes, trecho", [
    ({"velocidade": {"atencao": 130}}, "amarelo precisa começar antes do vermelho"),
    ({"velocidade": {"perigo": 250}}, "vermelho até o máximo"),
    ({"velocidade": {"maximo": 420}}, "entre 100 e 400"),
    ({"velocidade": {"maximo": 255}}, "de 10 em 10"),
    ({"rpm": {"maximo": 7500}}, "de 1000 em 1000"),
    ({"rpm": {"numeros": "todos"}}, "principais ou intercalados"),
    ({"rpm": {"centro": "lambda"}}, "consumo ou esforco"),
    ({"tanque": {"centro": "autonomia"}}, "litros ou etanol"),
    ({"tanque": {"capacidade_l": "52"}}, "deveria ser um número"),
    ({"mostradores": []}, "ao menos um mostrador"),
    ({"mostradores": ["rpm", "rpm"]}, "sem repetir"),
    ({"mostradores": ["bateria"]}, "entre:"),
    ({"cor": "azul"}, "chave desconhecida"),
    (["velocidade"], "objeto JSON"),
])
def test_recusa_configuracao_invalida(alteracoes, trecho):
    with pytest.raises(cfg.ErroConfig, match=trecho):
        cfg.atualizar(cfg.PADRAO, alteracoes)


def test_alteracao_parcial_mantem_o_resto():
    novo = cfg.atualizar(cfg.PADRAO, {"velocidade": {"maximo": 240}})
    assert novo["velocidade"] == {"maximo": 240, "atencao": 100, "perigo": 120, "numeros": "principais"}
    assert novo["rpm"] == cfg.PADRAO["rpm"]
    assert cfg.PADRAO["velocidade"]["maximo"] == 200  # o padrão não é alterado


def test_salva_e_carrega(tmp_path):
    caminho = tmp_path / "config.json"
    novo = cfg.atualizar(cfg.PADRAO, {"mostradores": ["velocidade", "tanque"], "tanque": {"capacidade_l": 45}})
    cfg.salvar(caminho, novo)
    assert cfg.carregar(caminho) == novo
    assert not (tmp_path / "config.json.tmp").exists()


def test_arquivo_estragado_ou_ausente_usa_o_padrao(tmp_path):
    assert cfg.carregar(tmp_path / "nao_existe.json") == cfg.PADRAO
    estragado = tmp_path / "config.json"
    estragado.write_text("{ isso não é json")
    assert cfg.carregar(estragado) == cfg.PADRAO
    estragado.write_text(json.dumps({"velocidade": {"perigo": 999}}))
    assert cfg.carregar(estragado) == cfg.PADRAO
