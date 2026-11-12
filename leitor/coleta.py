"""Ciclo de leitura: consulta os PIDs em rodízio e reconecta sozinho quando o adaptador cai."""
import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from functools import partial

from .elm327 import Elm327, ErroAdaptador
from .obd import (CONTAGEM_DE_RESPOSTAS, LeituraUds, RespostaAtrasada, RespostaInvalida, SemDados, ler_resposta,
                  ler_uds, montar_consultas)

log = logging.getLogger(__name__)

ESPERA_RECONEXAO_S = 3
ESPERA_SEM_DADOS_S = 1


@dataclass(frozen=True)
class Leitura:
    t: float
    valores: dict[str, object]


@dataclass(frozen=True)
class _Consulta:
    comando: str
    decodificar: Callable[[list[str]], dict[str, object]]
    rapida: bool


class Coletor:
    """Lê o carro continuamente: rápidos a todo ciclo, cada UDS no seu ritmo, um bloco de lentos a cada N ciclos."""

    def __init__(self, endereco: str, protocolo: str, cabecalho: str | None, rapidos: list[int],
                 lentos: list[int], lentos_a_cada: int, leituras_uds: tuple[LeituraUds, ...] = ()):
        if not rapidos or lentos_a_cada < 1:
            raise ValueError("é preciso ao menos um PID rápido e lentos_a_cada >= 1")
        self.endereco = endereco
        self.protocolo = protocolo
        self.cabecalho = cabecalho
        self.lentos_a_cada = lentos_a_cada
        self._rapidas = montar_consultas(rapidos)
        self._lentas = montar_consultas(lentos)
        self._leituras_uds = leituras_uds
        self._sufixo = ""
        self._sem_dados = False
        self._inicio = time.monotonic()
        self._primeira: float | None = None
        self.total_leituras = 0

    @property
    def contagem_ativa(self) -> bool:
        return self._sufixo == CONTAGEM_DE_RESPOSTAS

    @property
    def taxa(self) -> float:
        """Leituras por segundo desde a primeira resposta do carro."""
        if self._primeira is None:
            return 0.0
        return self.total_leituras / max(time.monotonic() - self._primeira, 1e-9)

    async def ler(self) -> AsyncIterator[Leitura]:
        """Gera uma leitura por resposta do carro, para sempre."""
        while True:
            elm = Elm327(self.endereco)
            try:
                log.info("conectando em %s", self.endereco)
                await elm.conectar()
                await elm.inicializar(self.protocolo, self.cabecalho)
                self._sufixo = CONTAGEM_DE_RESPOSTAS if await self._aceita_contagem(elm) else ""
                log.info("lendo (contagem de respostas %s)", "ativa" if self.contagem_ativa else "desligada")
                async for leitura in self._ciclos(elm):
                    yield leitura
                log.warning("conexão com o adaptador caiu")
            except ErroAdaptador as erro:
                log.warning("falha no adaptador: %s", erro)
            finally:
                await elm.desconectar()
            await asyncio.sleep(ESPERA_RECONEXAO_S)

    async def _aceita_contagem(self, elm: Elm327) -> bool:
        """Liga a contagem de respostas só se o adaptador devolver o mesmo que sem ela."""
        # Com a contagem o ELM327 responde assim que a ECU fala, sem esperar o próprio timeout.
        consulta = self._rapidas[0]
        try:
            sem = ler_resposta(await elm.enviar(consulta))
            com = ler_resposta(await elm.enviar(consulta + CONTAGEM_DE_RESPOSTAS))
        except (SemDados, RespostaInvalida, ErroAdaptador):
            return False
        return com.keys() == sem.keys()

    async def _ciclos(self, elm: Elm327) -> AsyncIterator[Leitura]:
        ciclo = 0
        while elm.conectado:
            ciclo += 1
            for consulta in self._consultas_do_ciclo(ciclo):
                valores = await self._consultar(elm, consulta)
                if valores:
                    self._primeira = self._primeira or time.monotonic()
                    self.total_leituras += 1
                    yield Leitura(round(time.monotonic() - self._inicio, 3), valores)

    def _consultas_do_ciclo(self, ciclo: int) -> list[_Consulta]:
        consultas = [_Consulta(rapida + self._sufixo, ler_resposta, True) for rapida in self._rapidas]
        consultas += [_Consulta(uds.comando + self._sufixo, partial(ler_uds, leitura=uds), False)
                      for uds in self._leituras_uds if ciclo % uds.a_cada == 0]
        if self._lentas and ciclo % self.lentos_a_cada == 0:
            lenta = self._lentas[(ciclo // self.lentos_a_cada) % len(self._lentas)]
            consultas.append(_Consulta(lenta + self._sufixo, ler_resposta, False))
        return consultas

    async def _consultar(self, elm: Elm327, consulta: _Consulta) -> dict[str, object]:
        """Uma consulta ao carro; sem resposta vira dict vazio."""
        try:
            valores = consulta.decodificar(await elm.enviar(consulta.comando))
        except SemDados as erro:
            if consulta.rapida:
                if not self._sem_dados:
                    log.warning("o carro não respondeu (%s); a ignição está ligada?", erro)
                    self._sem_dados = True
                await asyncio.sleep(ESPERA_SEM_DADOS_S)
            return {}
        except RespostaAtrasada as erro:
            log.debug("%s: %s", consulta.comando, erro)
            return {}
        except RespostaInvalida as erro:
            log.warning("%s", erro)
            return {}
        except ErroAdaptador as erro:
            # Timeout isolado não derruba a conexão; só a queda do BLE leva à reconexão.
            if not elm.conectado:
                raise
            log.warning("%s: %s; seguindo", consulta.comando, erro)
            return {}
        if self._sem_dados:
            log.info("o carro voltou a responder")
            self._sem_dados = False
        return valores
