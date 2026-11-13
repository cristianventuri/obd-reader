import { Indicador, definicoesDaConfig } from "./indicadores.js";
import { Navegacao } from "./navegacao.js";

// Sem atualização por esse tempo, o mostrador esmaece; sem nenhuma mensagem, o status avisa.
const DESATUALIZADO_MS = 10000;
const SEM_DADOS_MS = 5000;

const statusEl = document.getElementById("status");
const container = document.getElementById("mostradores");
// Segurar o dedo num mostrador abre as configurações; sozinho (tela redonda), abre o primeiro ajuste sozinho.
const navegacao = new Navegacao(container, "mostrador", {
  aoSegurar: (unico) => location.assign(unico ? "/config?ajuste=velocidade-maximo" : "/config"),
});
let indicadores = [];
// Último valor de cada dado e quando chegou; cada leitura do carro traz só parte deles.
const estado = {};
const atualizadoEm = {};
let ultimaMensagem = 0;
let conectado = false;
let desenhoAgendado = false;

function definirStatus(situacao, texto) {
  statusEl.dataset.estado = situacao;
  statusEl.textContent = texto;
}

// Escalas, faixas e quais mostradores aparecem vêm da configuração: a cada mudança, remonta tudo.
function aplicarConfig(config) {
  container.replaceChildren();
  indicadores = definicoesDaConfig(config).map((definicao) => new Indicador(definicao, container));
  navegacao.definirItens(indicadores);
  const agora = Date.now();
  for (const indicador of indicadores) {
    indicador.atualizar(estado);
    indicador.vigiar(atualizadoEm, agora, DESATUALIZADO_MS);
  }
}

// Várias leituras podem chegar entre dois quadros da tela: desenha uma vez só, com o estado mais novo.
function agendarDesenho() {
  if (desenhoAgendado) return;
  desenhoAgendado = true;
  requestAnimationFrame(() => {
    desenhoAgendado = false;
    for (const indicador of indicadores) indicador.atualizar(estado);
  });
}

function receber(dados) {
  const agora = Date.now();
  for (const [chave, valor] of Object.entries(dados)) {
    // null também vale: o km/l some ao parar, e o carro manda null no que não informa
    estado[chave] = valor;
    atualizadoEm[chave] = agora;
  }
  ultimaMensagem = agora;
  definirStatus("ao-vivo", "ao vivo");
  agendarDesenho();
}

function vigiar() {
  const agora = Date.now();
  for (const indicador of indicadores) indicador.vigiar(atualizadoEm, agora, DESATUALIZADO_MS);
  if (!conectado) return;
  if (agora - ultimaMensagem > SEM_DADOS_MS) definirStatus("sem-dados", "sem dados do carro");
  else definirStatus("ao-vivo", "ao vivo");
}

function conectar() {
  // EventSource reconecta sozinho quando o leitor reinicia ou a rede oscila.
  const fonte = new EventSource("/leituras");
  fonte.onopen = () => {
    conectado = true;
    definirStatus("conectando", "aguardando dados…");
  };
  fonte.onerror = () => {
    conectado = false;
    definirStatus("desconectado", "leitor desconectado, tentando de novo…");
  };
  // a configuração chega ao conectar e de novo sempre que alguém a muda (de qualquer aparelho)
  fonte.addEventListener("config", (evento) => aplicarConfig(JSON.parse(evento.data)));
  fonte.onmessage = (evento) => {
    const dados = JSON.parse(evento.data);
    if (Object.keys(dados).length > 0) receber(dados);
  };
}

conectar();
setInterval(vigiar, 1000);
