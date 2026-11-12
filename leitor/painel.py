"""Painel web opcional: serve a página de indicadores e transmite as leituras por SSE (Server-Sent Events)."""
import asyncio
import json
import logging
from pathlib import Path

from aiohttp import web

from .coleta import Leitura
from .saida import como_dict

log = logging.getLogger(__name__)

ESTATICO = Path(__file__).parent / "estatico"
# Leituras guardadas para um navegador lento; cheia, descarta a mais antiga em vez de segurar o carro.
TAMANHO_FILA = 100


def _enfileirar(fila: asyncio.Queue, mensagem: str | None) -> None:
    """Coloca na fila sem esperar; cheia, descarta a mensagem mais antiga."""
    if fila.full():
        fila.get_nowait()
    fila.put_nowait(mensagem)


class Painel:
    """Servidor do painel; só envia dados ao navegador, nunca recebe comandos."""

    def __init__(self, host: str, porta: int):
        self.host = host
        self.porta = porta
        self._clientes: set[asyncio.Queue[str | None]] = set()
        self._estado: dict[str, object] = {}
        self._runner: web.AppRunner | None = None

    async def iniciar(self) -> None:
        app = web.Application()
        app.router.add_get("/", self._pagina)
        app.router.add_get("/leituras", self._transmitir)
        app.router.add_static("/estatico", ESTATICO)
        self._runner = web.AppRunner(app, access_log=None, shutdown_timeout=1)
        await self._runner.setup()
        await web.TCPSite(self._runner, self.host, self.porta).start()
        endereco = "localhost" if self.host in ("127.0.0.1", "0.0.0.0") else self.host
        rede = " (e pelo IP desta máquina na rede)" if self.host == "0.0.0.0" else ""
        log.info("painel em http://%s:%d%s", endereco, self.porta, rede)

    async def parar(self) -> None:
        for fila in self._clientes:
            _enfileirar(fila, None)  # encerra cada transmissão aberta para o servidor fechar na hora
        if self._runner is not None:
            await self._runner.cleanup()

    def publicar(self, leitura: Leitura) -> None:
        """Repassa a leitura a cada navegador conectado, sem nunca bloquear a coleta."""
        dados = como_dict(leitura)
        self._estado.update(dados)
        mensagem = json.dumps(dados, ensure_ascii=False)
        for fila in self._clientes:
            _enfileirar(fila, mensagem)

    async def _pagina(self, _: web.Request) -> web.FileResponse:
        return web.FileResponse(ESTATICO / "index.html")

    async def _transmitir(self, request: web.Request) -> web.StreamResponse:
        resposta = web.StreamResponse(headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"})
        await resposta.prepare(request)
        fila: asyncio.Queue[str | None] = asyncio.Queue(maxsize=TAMANHO_FILA)
        fila.put_nowait(json.dumps(self._estado, ensure_ascii=False))  # quem chega já vê o último valor de tudo
        self._clientes.add(fila)
        try:
            while (mensagem := await fila.get()) is not None:
                await resposta.write(f"data: {mensagem}\n\n".encode())
        except ConnectionResetError:
            pass  # navegador fechou a aba
        finally:
            self._clientes.discard(fila)
        return resposta
