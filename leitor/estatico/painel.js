// Indicadores exibidos: chave = nome do valor na leitura. "maximo" desenha a barra; "alerta" destaca o cartão.
const INDICADORES = [
  { chave: "velocidade_kmh", titulo: "Velocidade", unidade: "km/h", destaque: true },
  { chave: "rpm", titulo: "Rotação", unidade: "rpm", destaque: true, maximo: 7000, alerta: (v) => v > 6000 },
  { chave: "marcha", titulo: "Marcha", destaque: true },
  { chave: "temp_motor_c", titulo: "Motor", unidade: "°C", maximo: 130, alerta: (v) => v > 110 },
  { chave: "pressao_turbo_kpa", titulo: "Turbo", unidade: "kPa", maximo: 250 },
  { chave: "carga_absoluta_pct", titulo: "Carga", unidade: "%", maximo: 150 },
  { chave: "pedal_pct", titulo: "Pedal", unidade: "%", maximo: 100 },
  { chave: "tanque_pct", titulo: "Tanque", unidade: "%", maximo: 100, alerta: (v) => v < 10 },
  { chave: "tensao_v", titulo: "Bateria", unidade: "V", casas: 1, alerta: (v) => v < 11.8 },
  { chave: "temp_ar_c", titulo: "Ar admitido", unidade: "°C" },
  { chave: "etanol_pct", titulo: "Etanol", unidade: "%" },
  { chave: "luz_injecao", titulo: "Injeção", formatar: (v) => (v ? "acesa" : "ok"), alerta: (v) => v },
];

// Sem atualização por esse tempo, o cartão esmaece; sem nenhuma mensagem, o status avisa.
const DESATUALIZADO_MS = 10000;
const SEM_DADOS_MS = 5000;

const cartoes = new Map();
const statusEl = document.getElementById("status");
let ultimaMensagem = 0;
let conectado = false;

function montarCartoes() {
  const modelo = document.getElementById("modelo-cartao");
  for (const indicador of INDICADORES) {
    const elemento = modelo.content.firstElementChild.cloneNode(true);
    elemento.querySelector(".titulo").textContent = indicador.titulo;
    elemento.querySelector(".unidade").textContent = indicador.unidade ?? "";
    const barra = elemento.querySelector(".barra");
    barra.hidden = indicador.maximo === undefined;
    document.getElementById(indicador.destaque ? "destaques" : "grade").append(elemento);
    cartoes.set(indicador.chave, {
      indicador,
      elemento,
      valor: elemento.querySelector(".valor"),
      preenchimento: elemento.querySelector(".preenchimento"),
      atualizadoEm: 0,
    });
  }
}

function formatar(indicador, valor) {
  if (indicador.formatar) return indicador.formatar(valor);
  if (typeof valor !== "number") return String(valor);
  return valor.toLocaleString("pt-BR", { maximumFractionDigits: indicador.casas ?? 0 });
}

function atualizar(dados) {
  const agora = Date.now();
  for (const [chave, valor] of Object.entries(dados)) {
    const cartao = cartoes.get(chave);
    if (!cartao || valor === null || valor === undefined) continue;
    const { indicador, elemento } = cartao;
    cartao.valor.textContent = formatar(indicador, valor);
    if (indicador.maximo !== undefined) {
      const proporcao = Math.min(Math.max(valor / indicador.maximo, 0), 1);
      cartao.preenchimento.style.width = `${proporcao * 100}%`;
    }
    elemento.classList.toggle("alerta", Boolean(indicador.alerta?.(valor)));
    elemento.classList.remove("desatualizado");
    cartao.atualizadoEm = agora;
  }
}

function definirStatus(estado, texto) {
  statusEl.dataset.estado = estado;
  statusEl.textContent = texto;
}

function vigiar() {
  const agora = Date.now();
  for (const cartao of cartoes.values()) {
    cartao.elemento.classList.toggle("desatualizado", agora - cartao.atualizadoEm > DESATUALIZADO_MS);
  }
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
  fonte.onmessage = (evento) => {
    const dados = JSON.parse(evento.data);
    if (Object.keys(dados).length === 0) return;
    ultimaMensagem = Date.now();
    definirStatus("ao-vivo", "ao vivo");
    atualizar(dados);
  };
}

montarCartoes();
conectar();
setInterval(vigiar, 1000);
