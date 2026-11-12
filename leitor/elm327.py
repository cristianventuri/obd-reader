"""Transporte BLE do ELM327: busca de dispositivos, conexão e troca de comandos somente leitura."""
import asyncio
import logging
from dataclasses import dataclass

from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError

from .obd import exigir_somente_leitura

log = logging.getLogger(__name__)

FIM_DE_RESPOSTA = b">"
ERROS_BLE = (BleakError, TimeoutError, OSError)


def _uuid(curto: str) -> str:
    return f"0000{curto}-0000-1000-8000-00805f9b34fb"


@dataclass(frozen=True)
class CanalSerial:
    """Serviço GATT que emula a serial do adaptador: respostas por notify, comandos por escrita."""
    servico: str
    leitura: str
    escrita: str


# Só pares confirmados: escrever numa característica desconhecida poderia reconfigurar o adaptador.
CANAIS_CONHECIDOS = (
    CanalSerial(_uuid("fff0"), _uuid("fff1"), _uuid("fff2")),
    CanalSerial(_uuid("ffe0"), _uuid("ffe1"), _uuid("ffe1")),
)


@dataclass(frozen=True)
class Dispositivo:
    endereco: str
    nome: str
    rssi: int


class ErroAdaptador(Exception):
    """Falha passageira de comunicação (BLE caiu, timeout); vale tentar de novo."""


class AdaptadorIncompativel(Exception):
    """O dispositivo não expõe nenhum canal serial conhecido; tentar de novo não resolve."""


async def buscar(timeout: float = 5.0) -> list[Dispositivo]:
    """Dispositivos BLE com nome, do sinal mais forte ao mais fraco."""
    # Sem filtro por serviço: nem todo adaptador anuncia o FFF0.
    encontrados = await BleakScanner.discover(timeout=timeout, return_adv=True)
    dispositivos = [Dispositivo(aparelho.address, anuncio.local_name or aparelho.name, anuncio.rssi)
                    for aparelho, anuncio in encontrados.values() if anuncio.local_name or aparelho.name]
    return sorted(dispositivos, key=lambda d: d.rssi, reverse=True)


def comandos_de_configuracao(protocolo: str, cabecalho: str | None) -> list[str]:
    """Deixa o ELM327 sem eco, sem espaços, sem cabeçalho e no protocolo do carro."""
    comandos = ["ATE0", "ATL0", "ATS0", "ATH0", f"ATSP{protocolo}"]
    if cabecalho:
        comandos.append(f"ATSH{cabecalho}")
    return comandos


class Elm327:
    """Conexão com o ELM327; todo comando passa pela regra de somente leitura antes de sair."""

    def __init__(self, endereco: str):
        self.endereco = endereco
        self._cliente: BleakClient | None = None
        self._escrita: BleakGATTCharacteristic | None = None
        self._escrita_com_confirmacao = False
        self._buffer = bytearray()
        self._pronto = asyncio.Event()
        self._trava = asyncio.Lock()

    @property
    def conectado(self) -> bool:
        return self._cliente is not None and self._cliente.is_connected

    async def conectar(self) -> None:
        try:
            aparelho = await BleakScanner.find_device_by_address(self.endereco, timeout=15)
            if aparelho is None:
                raise ErroAdaptador(f"adaptador {self.endereco} não encontrado")
            self._cliente = BleakClient(aparelho, timeout=20)
            await self._cliente.connect()
            leitura, self._escrita = self._abrir_canal()
            self._escrita_com_confirmacao = "write-without-response" not in self._escrita.properties
            await self._cliente.start_notify(leitura, self._ao_receber)
        except ERROS_BLE as erro:
            raise ErroAdaptador(str(erro) or type(erro).__name__) from erro

    async def desconectar(self) -> None:
        if self._cliente is not None:
            try:
                await self._cliente.disconnect()
            except ERROS_BLE:
                pass
            self._cliente = None

    async def inicializar(self, protocolo: str, cabecalho: str | None) -> None:
        versao = await self.enviar("ATZ", timeout=5)
        log.info("adaptador: %s", " ".join(versao))
        await asyncio.sleep(1)
        for comando in comandos_de_configuracao(protocolo, cabecalho):
            await self.enviar(comando)

    async def enviar(self, comando: str, timeout: float = 2.0) -> list[str]:
        """Envia um comando permitido e devolve as linhas da resposta, sem o prompt '>'."""
        exigir_somente_leitura(comando)
        if not self.conectado:
            raise ErroAdaptador("adaptador desconectado")
        async with self._trava:
            self._buffer.clear()
            self._pronto.clear()
            try:
                await self._cliente.write_gatt_char(self._escrita, (comando + "\r").encode(),
                                                    response=self._escrita_com_confirmacao)
                await asyncio.wait_for(self._pronto.wait(), timeout)
            except TimeoutError:
                # Uma resposta atrasada não pode vazar para o próximo comando.
                await asyncio.sleep(0.3)
                self._buffer.clear()
                raise ErroAdaptador(f"sem resposta para {comando}")
            except ERROS_BLE as erro:
                raise ErroAdaptador(str(erro) or type(erro).__name__) from erro
            texto = self._buffer.decode(errors="replace")
        linhas = [linha.strip() for linha in texto.replace(">", "").splitlines() if linha.strip()]
        log.debug("%s -> %s", comando, linhas)
        return linhas

    def _ao_receber(self, _, dados: bytearray) -> None:
        self._buffer.extend(dados)
        if FIM_DE_RESPOSTA in dados:
            self._pronto.set()

    def _abrir_canal(self) -> tuple[BleakGATTCharacteristic, BleakGATTCharacteristic]:
        """Acha o primeiro canal serial conhecido com notify na leitura e escrita na escrita."""
        for canal in CANAIS_CONHECIDOS:
            servico = self._cliente.services.get_service(canal.servico)
            if servico is None:
                continue
            leitura = servico.get_characteristic(canal.leitura)
            escrita = servico.get_characteristic(canal.escrita)
            if (leitura and escrita and "notify" in leitura.properties
                    and {"write", "write-without-response"} & set(escrita.properties)):
                log.info("canal serial: serviço %s", canal.servico[4:8].upper())
                return leitura, escrita
        servicos = ", ".join(s.uuid for s in self._cliente.services)
        raise AdaptadorIncompativel(f"nenhum canal serial conhecido em {self.endereco}; serviços: {servicos}")
