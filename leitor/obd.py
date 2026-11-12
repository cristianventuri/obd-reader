"""Núcleo OBD-II sem I/O: tabelas de PIDs e DIDs, decodificação e regra de somente leitura."""
import re
from collections.abc import Callable
from dataclasses import dataclass

MAX_PIDS_POR_CONSULTA = 6

_pct = lambda a: a * 100 / 255  # noqa: E731
_temperatura = lambda a: a - 40  # noqa: E731
_u16 = lambda a, b: a * 256 + b  # noqa: E731
_ajuste = lambda a: (a - 128) * 100 / 128  # noqa: E731


def _turbo(suportado, *dados):
    # bit 1 do primeiro byte indica a pressão real do turbo A, nos bytes D-E em 1/32 kPa
    return {"pressao_turbo_kpa": _u16(dados[2], dados[3]) / 32 if suportado & 0x02 else None}


# PID do modo 01 -> (nome, quantidade de bytes, conversão); conversão que devolve dict vira vários valores
PIDS = {
    0x01: ("diagnostico", 4, lambda a, b, c, d: {"luz_injecao": bool(a & 0x80), "codigos_falha": a & 0x7F}),
    0x04: ("carga_calculada_pct", 1, _pct),
    0x05: ("temp_motor_c", 1, _temperatura),
    0x06: ("ajuste_curto_pct", 1, _ajuste),
    0x07: ("ajuste_longo_pct", 1, _ajuste),
    0x0B: ("map_kpa", 1, lambda a: a),
    0x0C: ("rpm", 2, lambda a, b: _u16(a, b) / 4),
    0x0D: ("velocidade_kmh", 1, lambda a: a),
    0x0E: ("avanco_graus", 1, lambda a: a / 2 - 64),
    0x0F: ("temp_ar_c", 1, _temperatura),
    0x11: ("borboleta_pct", 1, _pct),
    0x1F: ("tempo_motor_s", 2, _u16),
    0x2F: ("tanque_pct", 1, _pct),
    0x31: ("km_desde_limpeza", 2, _u16),
    0x33: ("barometrica_kpa", 1, lambda a: a),
    0x34: ("lambda_sonda", 4, lambda a, b, c, d: _u16(a, b) * 2 / 65536),
    0x3C: ("temp_catalisador_c", 2, lambda a, b: _u16(a, b) / 10 - 40),
    0x42: ("tensao_v", 2, lambda a, b: _u16(a, b) / 1000),
    0x43: ("carga_absoluta_pct", 2, lambda a, b: _u16(a, b) * 100 / 255),
    0x44: ("lambda_comandado", 2, lambda a, b: _u16(a, b) * 2 / 65536),
    0x46: ("temp_ambiente_c", 1, _temperatura),
    0x49: ("pedal_pct", 1, _pct),
    0x52: ("etanol_pct", 1, _pct),
    0x70: ("turbo", 10, _turbo),
}


MOTOR, CAMBIO = "7E0", "7E1"
PARADO = ("P", "N", "P/N")


@dataclass(frozen=True)
class LeituraUds:
    """Dado próprio da VW lido pelo serviço 22 (ReadDataByIdentifier) numa central."""
    did: int
    nome: str
    conversao: Callable[[bytes], object]
    a_cada: int = 1  # lida a cada N ciclos de leitura
    cabecalho: str = MOTOR
    condicao: Callable[[dict], bool] | None = None  # só é lida quando a condição sobre o contexto é verdadeira

    @property
    def comando(self) -> str:
        return f"22{self.did:04X}"


def _marcha(dados: bytes) -> str:
    """Byte com sinal: -1 = ré, 0 = nenhuma engatada (P ou N), 1..6 = marcha."""
    numero = int.from_bytes(dados[:1], signed=True)
    return {-1: "R", 0: "P/N"}.get(numero, str(numero))


def _estacionado(dados: bytes) -> bool:
    """00 = alavanca em P; 01 = N, R ou D."""
    return dados[0] == 0


# DIDs confirmados no carro (captura do Car Scanner e varredura de leitura); comando -> leitura.
# O câmbio vem antes da marcha para o P/N já sair resolvido no mesmo ciclo.
LEITURAS_UDS = {leitura.comando: leitura for leitura in (
    LeituraUds(0x104B, "estacionado", _estacionado, a_cada=2, cabecalho=CAMBIO,
               condicao=lambda contexto: contexto.get("marcha", "P/N") in PARADO),
    LeituraUds(0x14CB, "marcha", _marcha, a_cada=2),
)}
ESTACIONADO, MARCHA = LEITURAS_UDS["22104B"], LEITURAS_UDS["2214CB"]


def falta_para_resolver(valores: dict[str, object], contexto: dict[str, object]) -> str | None:
    """Nome da leitura a fazer na hora para não emitir um valor ambíguo (marcha "P/N" sem a posição do câmbio)."""
    if valores.get("marcha") == "P/N" and "estacionado" not in contexto and "estacionado" not in valores:
        return "estacionado"
    return None


def contextualizar(valores: dict[str, object], contexto: dict[str, object]) -> dict[str, object]:
    """Guarda a leitura no contexto e troca "P/N" por P ou N quando a posição do câmbio é conhecida."""
    valores = dict(valores)
    if "estacionado" in valores and contexto.get("marcha") in PARADO:
        valores.setdefault("marcha", "P/N")
    if valores.get("marcha") in PARADO:
        estacionado = valores.get("estacionado", contexto.get("estacionado"))
        if estacionado is not None:
            valores["marcha"] = "P" if estacionado else "N"
    elif "marcha" in valores:
        contexto.pop("estacionado", None)  # fora de P/N o câmbio não é consultado; o valor antigo envelheceria
    contexto.update(valores)
    return valores

ERROS_ELM = ("NO DATA", "CAN ERROR", "STOPPED", "UNABLE TO CONNECT", "BUS ERROR", "BUS BUSY",
             "BUFFER FULL", "DATA ERROR", "FB ERROR", "LV RESET", "ERROR", "?")

_LINHA_IGNORADA = re.compile(r"(SEARCHING|BUS INIT).*")
# "7F xx 78" = resposta pendente do UDS; o valor vem depois, na mesma resposta ou atrasado.
_PENDENTE = re.compile(r"7F[0-9A-F]{2}78")
_TAMANHO_MULTIQUADRO = re.compile(r"[0-9A-F]{3}")
_QUADRO = re.compile(r"([0-9A-F]):([0-9A-F]*)")

# Sufixo que faz o ELM327 devolver a resposta assim que a central fala, sem esperar o próprio timeout.
CONTAGEM_DE_RESPOSTAS = "1"

# Lista do que pode sair para o adaptador; o resto é recusado.
_CONSULTA_PERMITIDA = re.compile(r"01((?:[0-9A-F]{2}){1,%d})%s?" % (MAX_PIDS_POR_CONSULTA, CONTAGEM_DE_RESPOSTAS))
_AT_PERMITIDO = re.compile(r"AT(Z|E0|L0|S0|H0|SP[0-9A-C]|SH[0-9A-F]{3})")


class SemDados(Exception):
    """O adaptador respondeu, mas o carro não (ignição desligada, protocolo errado...)."""


class RespostaInvalida(Exception):
    """A resposta não segue o formato esperado."""


class RespostaAtrasada(Exception):
    """Só veio o "aguarde" (7F xx 78) ou a sobra de um pedido anterior; o valor vem num próximo ciclo."""


class ComandoProibido(Exception):
    """Comando fora da lista de leitura permitida; nunca é enviado."""


def exigir_somente_leitura(comando: str) -> None:
    """Só deixa passar configuração do ELM327, modo 01 com PIDs conhecidos e as leituras de `LEITURAS_UDS`."""
    sem_contagem = comando.removesuffix(CONTAGEM_DE_RESPOSTAS)
    if _AT_PERMITIDO.fullmatch(comando) or comando in LEITURAS_UDS or sem_contagem in LEITURAS_UDS:
        return
    consulta = _CONSULTA_PERMITIDA.fullmatch(comando)
    if consulta and all(int(pid, 16) in PIDS for pid in re.findall("..", consulta.group(1))):
        return
    raise ComandoProibido(repr(comando))


def montar_consultas(pids: list[int]) -> list[str]:
    """Agrupa os PIDs em consultas do modo 01 com no máximo 6 PIDs cada."""
    desconhecidos = [f"{pid:02X}" for pid in pids if pid not in PIDS]
    if desconhecidos:
        raise ValueError(f"PIDs fora da tabela: {', '.join(desconhecidos)}")
    blocos = [pids[i:i + MAX_PIDS_POR_CONSULTA] for i in range(0, len(pids), MAX_PIDS_POR_CONSULTA)]
    return ["01" + "".join(f"{pid:02X}" for pid in bloco) for bloco in blocos]


def _e_sobra(linha: str, esperado: int) -> bool:
    """Resposta de quadro único de outro pedido (ex.: um 62 atrasado chegando junto de um 41)."""
    if _QUADRO.fullmatch(linha) or _TAMANHO_MULTIQUADRO.fullmatch(linha):
        return False
    return not linha.startswith((f"{esperado:02X}", "7F"))


def extrair_bytes(linhas: list[str], esperado: int | None = None) -> bytes:
    """Junta as linhas do ELM327 (quadro único ou ISO-TP multiquadro) em bytes; `esperado` descarta sobras."""
    limpas, descartadas = [], []
    for linha in linhas:
        linha = linha.replace(" ", "").replace(">", "").upper()
        if not linha or _LINHA_IGNORADA.fullmatch(linha):
            continue
        if any(linha.startswith(erro.replace(" ", "")) for erro in ERROS_ELM):
            raise SemDados(linha)
        if _PENDENTE.fullmatch(linha) or (esperado is not None and _e_sobra(linha, esperado)):
            descartadas.append(linha)
            continue
        limpas.append(linha)

    if not limpas:
        if descartadas:
            raise RespostaAtrasada(f"só veio {descartadas}")
        raise SemDados("resposta vazia")

    quadros = [m.group(2) for m in map(_QUADRO.fullmatch, limpas) if m]
    if quadros:
        tamanho = next((int(linha, 16) for linha in limpas if _TAMANHO_MULTIQUADRO.fullmatch(linha)), None)
        hexa = "".join(quadros)
        if tamanho is not None:
            hexa = hexa[: tamanho * 2]
    else:
        hexa = limpas[0]

    try:
        return bytes.fromhex(hexa)
    except ValueError as erro:
        raise RespostaInvalida(f"resposta não hexadecimal: {limpas}") from erro


def decodificar_modo01(dados: bytes) -> dict[int, object]:
    """Converte uma resposta do modo 01 com um ou vários PIDs (ex.: 41 0C xx xx 0D xx)."""
    if not dados or dados[0] != 0x41:
        raise RespostaInvalida(f"resposta não é do modo 01: {dados.hex()}")
    valores = {}
    i = 1
    while i < len(dados):
        pid = dados[i]
        if pid not in PIDS:
            break
        _, tamanho, conversao = PIDS[pid]
        if i + 1 + tamanho > len(dados):
            break
        valores[pid] = conversao(*dados[i + 1: i + 1 + tamanho])
        i += 1 + tamanho
    return valores


def nomear(valores: dict[int, object]) -> dict[str, object]:
    """Troca os PIDs pelos nomes, espalhando os que trazem vários valores."""
    nomeados = {}
    for pid, valor in valores.items():
        if isinstance(valor, dict):
            nomeados.update(valor)
        else:
            nomeados[PIDS[pid][0]] = valor
    return nomeados


def ler_resposta(linhas: list[str]) -> dict[str, object]:
    """Linhas cruas do ELM327 -> valores nomeados."""
    return nomear(decodificar_modo01(extrair_bytes(linhas, esperado=0x41)))


def ler_uds(linhas: list[str], leitura: LeituraUds) -> dict[str, object]:
    """Linhas cruas de uma leitura do serviço 22 -> valor nomeado; resposta negativa (7F) é inválida."""
    dados = extrair_bytes(linhas, esperado=0x62)
    if len(dados) < 4 or dados[:3] != bytes([0x62, leitura.did >> 8, leitura.did & 0xFF]):
        raise RespostaInvalida(f"resposta inesperada para {leitura.comando}: {dados.hex()}")
    return {leitura.nome: leitura.conversao(dados[3:])}
