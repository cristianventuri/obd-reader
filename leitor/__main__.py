"""Linha de comando: escolhe o adaptador, lê o carro e imprime cada resposta no stdout (e no painel, se pedido)."""
import argparse
import asyncio
import logging
import re
import signal
import sys
from collections.abc import Callable
from typing import TYPE_CHECKING

from .coleta import Coletor, Leitura
from .elm327 import AdaptadorIncompativel, buscar
from .obd import ESTACIONADO, MARCHA, PIDS, ComandoProibido
from .saida import formatar_json, formatar_texto

if TYPE_CHECKING:
    from .painel import Painel

log = logging.getLogger("leitor")

RAPIDOS_PADRAO = "0C,0D,43,44,0B"
LENTOS_PADRAO = "05,0F,46,2F,42,33,70,0E,11,49,04,3C,01,06,07,34,1F,31,52"


def _lista_de_pids(texto: str) -> list[int]:
    try:
        pids = [int(pid, 16) for pid in texto.split(",") if pid.strip()]
    except ValueError:
        raise argparse.ArgumentTypeError(f"PIDs devem ser hexadecimais separados por vírgula: {texto}")
    desconhecidos = [f"{pid:02X}" for pid in pids if pid not in PIDS]
    if desconhecidos:
        raise argparse.ArgumentTypeError(f"PIDs fora da tabela: {', '.join(desconhecidos)}")
    return pids


def _formato(padrao: str, descricao: str):
    def validar(texto: str) -> str:
        if not re.fullmatch(padrao, texto.upper()):
            raise argparse.ArgumentTypeError(f"{descricao} inválido: {texto}")
        return texto.upper()
    return validar


def _inteiro_positivo(texto: str) -> int:
    if not texto.isdigit() or int(texto) < 1:
        raise argparse.ArgumentTypeError(f"esperado inteiro >= 1: {texto}")
    return int(texto)


def _porta(texto: str) -> int:
    if not texto.isdigit() or not 1 <= int(texto) <= 65535:
        raise argparse.ArgumentTypeError(f"porta inválida: {texto}")
    return int(texto)


def _argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="leitor", description="Lê dados OBD-II de um ELM327 BLE (somente leitura).")
    # MAC no Linux/Windows; UUID no macOS
    parser.add_argument("--endereco", type=_formato(r"[0-9A-F]{2}(:[0-9A-F]{2}){5}|[0-9A-F-]{36}", "endereço"),
                        help="endereço BLE do adaptador; sem ele, abre a lista de dispositivos")
    parser.add_argument("--protocolo", type=_formato(r"[0-9A-C]", "protocolo"), default="6",
                        help="protocolo do ELM327 (padrão: 6 = CAN 11 bits 500k)")
    parser.add_argument("--cabecalho", type=_formato(r"[0-9A-F]{3}", "cabeçalho"), default="7E0",
                        help="ECU consultada (padrão: 7E0 = motor)")
    parser.add_argument("--rapidos", type=_lista_de_pids, default=RAPIDOS_PADRAO, help="PIDs lidos em todo ciclo")
    parser.add_argument("--lentos", type=_lista_de_pids, default=LENTOS_PADRAO, help="PIDs lidos em rodízio")
    parser.add_argument("--a-cada", type=_inteiro_positivo, default=3, help="ciclos entre blocos de PIDs lentos")
    parser.add_argument("--sem-marcha", action="store_true",
                        help="não lê a marcha nem a posição P do câmbio, ganhando velocidade nos PIDs rápidos")
    parser.add_argument("--json", action="store_true", help="uma linha JSON por resposta")
    parser.add_argument("-v", "--verbose", action="store_true", help="mostra comandos e respostas cruas do ELM327")
    parser.add_argument("--painel", action="store_true", help="abre também o painel web com os indicadores")
    parser.add_argument("--host", default="127.0.0.1",
                        help="endereço do painel (padrão: só esta máquina; 0.0.0.0 abre para a rede)")
    parser.add_argument("--porta", type=_porta, default=8080, help="porta do painel (padrão: 8080)")
    return parser.parse_args()


def avisar(texto: str) -> None:
    print(texto, file=sys.stderr, flush=True)


def escolher_dispositivo() -> str:
    """Busca dispositivos BLE e pergunta qual usar; 'r' busca de novo."""
    if not sys.stdin.isatty():
        sys.exit("sem terminal interativo: informe --endereco")
    while True:
        avisar("buscando dispositivos bluetooth (5 s)...")
        dispositivos = asyncio.run(buscar())
        if not dispositivos:
            avisar("nenhum dispositivo encontrado; o adaptador está ligado no carro?")
        for numero, dispositivo in enumerate(dispositivos, 1):
            avisar(f"  {numero}) {dispositivo.nome:<20} {dispositivo.endereco}  {dispositivo.rssi} dBm")
        avisar("número do adaptador (r = buscar de novo): ")
        escolha = input().strip().lower()
        if escolha.isdigit() and 1 <= int(escolha) <= len(dispositivos):
            endereco = dispositivos[int(escolha) - 1].endereco
            avisar(f"da próxima vez: --endereco {endereco}")
            return endereco


def criar_painel(args: argparse.Namespace) -> "Painel | None":
    if not args.painel:
        return None
    from .painel import Painel  # só carrega o servidor web quando o painel é pedido
    return Painel(args.host, args.porta)


async def executar(coletor: Coletor, formatar: Callable[[Leitura], str], painel: "Painel | None") -> None:
    """Imprime cada leitura no stdout e repassa ao painel, se houver."""
    if painel is not None:
        try:
            await painel.iniciar()
        except OSError as erro:
            sys.exit(f"não foi possível abrir o painel em {painel.host}:{painel.porta}: {erro.strerror or erro}")
    try:
        async for leitura in coletor.ler():
            print(formatar(leitura), flush=True)
            if painel is not None:
                painel.publicar(leitura)
    finally:
        if painel is not None:
            await painel.parar()


def _encerrar(*_) -> None:
    raise KeyboardInterrupt


def main() -> None:
    args = _argumentos()
    logging.basicConfig(stream=sys.stderr, level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("bleak").setLevel(logging.WARNING)
    # kill/systemd mandam SIGTERM: encerra como no Ctrl+C, desconectando o BLE.
    signal.signal(signal.SIGTERM, _encerrar)

    coletor = None
    try:
        endereco = args.endereco or escolher_dispositivo()
        coletor = Coletor(endereco, args.protocolo, args.cabecalho, args.rapidos, args.lentos, args.a_cada,
                          leituras_uds=() if args.sem_marcha else (ESTACIONADO, MARCHA))
        asyncio.run(executar(coletor, formatar_json if args.json else formatar_texto, criar_painel(args)))
    except KeyboardInterrupt:
        pass
    except ComandoProibido as erro:
        sys.exit(f"comando bloqueado pela regra de somente leitura: {erro}")
    except AdaptadorIncompativel as erro:
        sys.exit(str(erro))
    finally:
        if coletor is not None:
            log.info("%d leituras (%.1f/s), contagem de respostas %s", coletor.total_leituras, coletor.taxa,
                     "ativa" if coletor.contagem_ativa else "desligada")


if __name__ == "__main__":
    main()
