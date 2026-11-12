"""Formatos de uma leitura: texto para o terminal e JSON para máquinas (stdout e painel)."""
import json

from .coleta import Leitura


def _arredondar(valor: object) -> object:
    return round(valor, 2) if isinstance(valor, float) else valor


def como_dict(leitura: Leitura) -> dict[str, object]:
    """Tempo desde o início + valores arredondados em 2 casas."""
    return {"t": leitura.t, **{nome: _arredondar(valor) for nome, valor in leitura.valores.items()}}


def formatar_texto(leitura: Leitura) -> str:
    valores = " ".join(f"{nome}={_arredondar(valor)}" for nome, valor in leitura.valores.items())
    return f"{leitura.t:9.3f}  {valores}"


def formatar_json(leitura: Leitura) -> str:
    return json.dumps(como_dict(leitura), separators=(",", ":"), ensure_ascii=False)
