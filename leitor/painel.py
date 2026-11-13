"""Painel web opcional: serve as páginas, transmite as leituras por SSE e guarda a configuração do painel."""
import asyncio
import copy
import json
import logging
from pathlib import Path

from aiohttp import web

from . import config as cfg
from .coleta import Leitura
from .consumo import Consumo
from .saida import como_dict

log = logging.getLogger(__name__)

ESTATICO = Path(__file__).parent / "estatico"
# Mensagens guardadas para um navegador lento; cheia, descarta a mais antiga em vez de segurar o carro.
TAMANHO_FILA = 100


def _quadro(dados: object, evento: str | None = None) -> str:
    """Uma mensagem SSE; com `evento`, o navegador a recebe separada das leituras."""
    cabecalho = f"event: {evento}\n" if evento else ""
    return f"{cabecalho}data: {json.dumps(dados, ensure_ascii=False)}\n\n"


def _enfileirar(fila: asyncio.Queue, quadro: str | None) -> None:
    """Coloca na fila sem esperar; cheia, descarta a mensagem mais antiga."""
    if fila.full():
        fila.get_nowait()
    fila.put_nowait(quadro)


class Painel:
    """Servidor do painel; recebe só a configuração do próprio painel, nunca comandos para o carro."""

    def __init__(self, host: str, porta: int, caminho_config: Path | None = None):
        self.host = host
        self.porta = porta
        self._caminho_config = caminho_config
        self.config = cfg.carregar(caminho_config) if caminho_config else copy.deepcopy(cfg.PADRAO)
        self._clientes: set[asyncio.Queue[str | None]] = set()
        self._estado: dict[str, object] = {}
        self._consumo = Consumo()
        self._runner: web.AppRunner | None = None

    async def iniciar(self) -> None:
        app = web.Application()
        app.router.add_get("/", self._pagina("index.html"))
        app.router.add_get("/config", self._pagina("config.html"))
        app.router.add_get("/leituras", self._transmitir)
        app.router.add_get("/api/config", self._obter_config)
        app.router.add_put("/api/config", self._alterar_config)
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
        """Repassa a leitura, mais o consumo estimado, a cada navegador conectado, sem nunca bloquear a coleta."""
        dados = como_dict(leitura)
        self._estado.update(dados)
        # um passo da média a cada ciclo: a rotação chega em toda leitura rápida
        if "rpm" in dados and (consumo := self._consumo.atualizar(self._estado, leitura.t)):
            dados |= consumo
            self._estado.update(consumo)
        self._difundir(_quadro(dados))

    def alterar_config(self, alteracoes: object) -> dict:
        """Valida, grava e avisa todas as telas abertas; inválida, nada muda."""
        novo = cfg.atualizar(self.config, alteracoes)
        if self._caminho_config is not None:
            cfg.salvar(self._caminho_config, novo)
        self.config = novo
        self._difundir(_quadro(novo, "config"))
        return novo

    def _difundir(self, quadro: str) -> None:
        for fila in self._clientes:
            _enfileirar(fila, quadro)

    @staticmethod
    def _pagina(arquivo: str):
        async def responder(_: web.Request) -> web.FileResponse:
            return web.FileResponse(ESTATICO / arquivo)
        return responder

    async def _obter_config(self, _: web.Request) -> web.Response:
        return web.json_response(self.config)

    async def _alterar_config(self, request: web.Request) -> web.Response:
        try:
            return web.json_response(self.alterar_config(await request.json()))
        except (cfg.ErroConfig, json.JSONDecodeError) as erro:
            return web.json_response({"erro": str(erro)}, status=400)
        except OSError as erro:
            log.warning("não foi possível salvar a configuração: %s", erro)
            return web.json_response({"erro": f"não foi possível salvar: {erro.strerror or erro}"}, status=500)

    async def _transmitir(self, request: web.Request) -> web.StreamResponse:
        resposta = web.StreamResponse(headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"})
        await resposta.prepare(request)
        fila: asyncio.Queue[str | None] = asyncio.Queue(maxsize=TAMANHO_FILA)
        # quem chega recebe a configuração e já vê o último valor de tudo
        fila.put_nowait(_quadro(self.config, "config"))
        fila.put_nowait(_quadro(self._estado))
        self._clientes.add(fila)
        try:
            while (quadro := await fila.get()) is not None:
                await resposta.write(quadro.encode())
        except ConnectionResetError:
            pass  # navegador fechou a aba
        finally:
            self._clientes.discard(fila)
        return resposta
