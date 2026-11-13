// Mostrador redondo da tela AMOLED de 1,75" (422×422): uma unidade do viewBox é um pixel da tela.
const NS = "http://www.w3.org/2000/svg";
export const TAMANHO = 422;
const C = TAMANHO / 2;

// Todos os mostradores varrem 270°, das 7h30 às 4h30 (0° = 3 horas, sentido horário).
const INICIO = 135;
const VARREDURA = 270;

// Raios, de fora para dentro. A agulha começa depois do miolo e dos textos: em nenhum ângulo passa por cima deles.
const RAIO = {
  aro: 208, halo: 204, zona: 198, agulhaFim: 188, marcaFim: 187, marcaMicro: 182, marcaMenor: 177, rastro: 176,
  marcaMaior: 167, rotulo: 143, agulhaInicio: 72, miolo: 60,
};
// Abaixo do miolo, de cima para baixo (centro de cada linha): nome, leitura, unidade e complementos.
// Vãos de 12 a 14 px entre o miolo e cada linha.
const Y = { legenda: 290, valor: 330, unidade: 368, complementos: 396 };
const LARGURA_VALOR = 140;
// Números da escala: tamanho sozinhos, quando intercalados e o dos intermediários; largura aproximada por algarismo.
const NUMERO = { principal: 22, intercalado: 20, menor: 15, larguraPorCaractere: 0.5, folga: 3 };
// Micro-escala: cada intervalo do meio vira 5 (ou 2) partes, se as marquinhas ficarem a pelo menos 7 px uma da outra.
const MICRO = { divisoes: [5, 2], distanciaMinima: 7 };
// Área dos textos embaixo do miolo (nome, leitura e unidade): número da escala que encostaria nela não é escrito.
const AREA_DOS_TEXTOS = {
  esquerda: C - LARGURA_VALOR / 2 - 6, direita: C + LARGURA_VALOR / 2 + 6, topo: Y.legenda - 10, base: Y.unidade + 10,
};

const f = (v) => Math.round(v * 100) / 100;
const limitar = (v, min = 0, max = 1) => Math.min(max, Math.max(min, v));

export function svg(tag, atributos = {}, pai = null) {
  const el = document.createElementNS(NS, tag);
  for (const [nome, valor] of Object.entries(atributos)) el.setAttribute(nome, valor);
  pai?.append(el);
  return el;
}

function polar(r, graus) {
  const a = (graus * Math.PI) / 180;
  return [C + r * Math.cos(a), C + r * Math.sin(a)];
}

function arco(r, de, ate) {
  const [x1, y1] = polar(r, de);
  const [x2, y2] = polar(r, ate);
  return `M ${f(x1)} ${f(y1)} A ${r} ${r} 0 ${ate - de > 180 ? 1 : 0} 1 ${f(x2)} ${f(y2)}`;
}

const arcoCompleto = (r) => arco(r, INICIO, INICIO + VARREDURA);

// Brilho e degradê do miolo: criados uma vez na página e usados por todos os mostradores.
function garantirDefinicoes() {
  if (document.getElementById("obd-brilho")) return;
  const raiz = svg("svg", { "aria-hidden": "true", width: 0, height: 0, style: "position: absolute" });
  const defs = svg("defs", {}, raiz);
  // região no espaço do desenho: o brilho da agulha, fina, não é cortado pela caixa dela
  const brilho = svg("filter", {
    id: "obd-brilho", filterUnits: "userSpaceOnUse", x: 0, y: 0, width: TAMANHO, height: TAMANHO,
  }, defs);
  svg("feGaussianBlur", { stdDeviation: 4 }, brilho);
  const miolo = svg("radialGradient", { id: "obd-miolo", cx: "50%", cy: "30%", r: "75%" }, defs);
  svg("stop", { offset: "0%", "stop-color": "#161b24" }, miolo);
  svg("stop", { offset: "100%", "stop-color": "#040506" }, miolo);
  document.body.append(raiz);
}

const larguraDoNumero = (texto, tamanho) => texto.length * tamanho * NUMERO.larguraPorCaractere;
// Distância entre dois pontos da escala separados por `passo`, medida no arco de raio `raio`.
const distanciaNoArco = (passo, faixa, raio) => (passo / faixa) * VARREDURA * (Math.PI / 180) * raio;

function encostaNosTextos(x, y, texto, tamanho) {
  const [meiaLargura, meiaAltura] = [larguraDoNumero(texto, tamanho) / 2, tamanho / 2];
  const area = AREA_DOS_TEXTOS;
  return x + meiaLargura > area.esquerda && x - meiaLargura < area.direita
    && y + meiaAltura > area.topo && y - meiaAltura < area.base;
}

/**
 * Passo dos números principais, entre `passos` (em ordem de preferência): o primeiro que couber sem encostar no
 * vizinho. Intercalados (um número também em cada marca do meio) pedem o dobro de espaço; se nenhum passo couber
 * assim, ficam só os principais.
 */
function escolherPasso(minimo, maximo, passos, intercalados, formatarRotulo) {
  const faixa = maximo - minimo;
  // distância no arco entre dois números principais
  const distancia = (passo) => distanciaNoArco(passo, faixa, RAIO.rotulo);
  const exemplos = (passo) => [minimo, maximo, maximo - passo / 2].map(formatarRotulo);
  const largura = (passo, tamanho) => Math.max(...exemplos(passo).map((texto) => larguraDoNumero(texto, tamanho)));
  if (intercalados) {
    const passo = passos.find((p) => distancia(p) / 2
      >= (largura(p, NUMERO.intercalado) + largura(p, NUMERO.menor)) / 2 + NUMERO.folga);
    if (passo !== undefined) return { passoMaior: passo, intercalados: true };
  }
  const passo = passos.find((p) => distancia(p) >= largura(p, NUMERO.principal) + NUMERO.folga);
  return { passoMaior: passo ?? passos.at(-1), intercalados: false };
}

/** Passo "redondo" (1, 2 ou 5 × 10ⁿ) que divide a faixa em umas 4 partes. */
export function passoBonito(minimo, maximo) {
  const bruto = (maximo - minimo) / 4;
  const magnitude = 10 ** Math.floor(Math.log10(bruto));
  const residuo = bruto / magnitude;
  return (residuo < 1.5 ? 1 : residuo < 3 ? 2 : residuo < 7 ? 5 : 10) * magnitude;
}

/** Faixa de valores nos 270°; quando cruza o zero (turbo), o preenchimento sai do zero para os dois lados. */
class Escala {
  constructor(minimo, maximo) {
    Object.assign(this, { minimo, maximo });
    this.origem = minimo < 0 && maximo > 0 ? this.fracao(0) : 0;
  }

  fracao(valor) {
    return valor === null ? this.origem : limitar((valor - this.minimo) / (this.maximo - this.minimo));
  }

  angulo(valor) {
    return INICIO + this.fracao(valor) * VARREDURA;
  }

  /** Pinta um arco de pathLength 100 da origem até o valor. */
  preencher(caminho, valor) {
    const fracao = this.fracao(valor);
    const [inicio, fim] = fracao >= this.origem ? [this.origem, fracao] : [fracao, this.origem];
    caminho.style.strokeDasharray = `${f((fim - inicio) * 100)} 100`;
    caminho.style.strokeDashoffset = f(-inicio * 100);
  }
}

/** Texto que encolhe para caber em `larguraMax`; só remede quando muda o número de caracteres. */
class TextoAjustado {
  constructor(el, larguraMax, tamanho) {
    Object.assign(this, { el, larguraMax, tamanho, caracteres: -1 });
    el.setAttribute("font-size", tamanho);
  }

  definir(texto) {
    if (this.el.textContent === texto) return;
    this.el.textContent = texto;
    if (texto.length === this.caracteres) return;
    this.caracteres = texto.length;
    this.el.setAttribute("font-size", this.tamanho);
    const largura = this.el.getComputedTextLength();
    if (largura > this.larguraMax) this.el.setAttribute("font-size", f((this.tamanho * this.larguraMax) / largura));
  }

  /** Mostrador escondido (display: none) mede largura zero: ao reaparecer, mede de novo. */
  remedir() {
    const texto = this.el.textContent;
    this.el.textContent = "";
    this.caracteres = -1;
    this.definir(texto);
  }
}

const texto = (pai, classe, y, larguraMax, tamanho, x = C) =>
  new TextoAjustado(svg("text", { class: classe, x, y }, pai), larguraMax, tamanho);

// --- miolo ---

// Fundo do miolo e, por cima, uma tinta na cor do nível que só aparece quando o dado passa do limite.
function fundoDoMiolo(g) {
  svg("circle", { class: "miolo-fundo", cx: C, cy: C, r: RAIO.miolo - 5 }, g);
  svg("circle", { class: "miolo-tinta", cx: C, cy: C, r: RAIO.miolo - 5 }, g);
}

/** Valor complementar no centro (nome, número e unidade), com anel de progresso em volta quando tem faixa. */
class MioloValor {
  constructor(g, { rotulo, faixa }) {
    fundoDoMiolo(g);
    if (faixa) {
      this.escala = new Escala(...faixa);
      svg("path", { class: "anel-trilho", d: arcoCompleto(RAIO.miolo) }, g);
      this.anel = svg("path", { class: "anel", d: arcoCompleto(RAIO.miolo), pathLength: 100 }, g);
    }
    const legenda = texto(g, "miolo-rotulo", C - 26, 88, 13);
    legenda.definir(rotulo.toUpperCase());
    this.valor = texto(g, "miolo-valor", C + 2, 90, 32);
    this.etiqueta = texto(g, "etiqueta", C + 28, 76, 12);
    this.textos = [legenda, this.valor, this.etiqueta];
  }

  /** `anel`: valor na faixa do anel (o próprio valor, ou uma fração calculada quando depende de mais dados). */
  atualizar({ anel, texto: conteudo, unidade }) {
    this.valor.definir(conteudo);
    this.etiqueta.definir(unidade.toUpperCase());
    if (this.anel) this.escala.preencher(this.anel, typeof anel === "number" ? anel : null);
  }
}

const SELETOR = ["P", "R", "N", "D"];
const MARCHAS = 6;

/**
 * Marcha engatada em destaque; abaixo, a alavanca (P R N D) com a posição atual preenchida;
 * no anel, um degrau por marcha, aceso até a engatada.
 */
class MioloMarcha {
  constructor(g) {
    this.g = g;
    fundoDoMiolo(g);
    const passo = VARREDURA / MARCHAS;
    this.degraus = Array.from({ length: MARCHAS }, (_, i) => svg("path", {
      class: "degrau", d: arco(RAIO.miolo, INICIO + i * passo + 3, INICIO + (i + 1) * passo - 3),
    }, g));
    this.marcha = texto(g, "marcha", C - 16, 84, 56);
    this.posicoes = SELETOR.map((letra, i) => {
      const x = C + (i - 1.5) * 19;
      const item = svg("g", { class: "seletor" }, g);
      svg("rect", { x: x - 8, y: C + 20, width: 16, height: 16, rx: 4.5 }, item);
      svg("text", { x, y: C + 28 }, item).textContent = letra;
      return { letra, item };
    });
    this.textos = [this.marcha];
  }

  atualizar({ texto: marcha }) {
    // número = marcha em D; P, R e N chegam como letra ("P/N" enquanto o câmbio não respondeu)
    const numero = /^\d+$/.test(marcha) ? Number(marcha) : 0;
    const posicao = numero ? "D" : marcha;
    this.marcha.definir(marcha);
    this.g.dataset.posicao = posicao;
    this.degraus.forEach((degrau, i) => {
      degrau.classList.toggle("passado", i + 1 < numero);
      degrau.classList.toggle("ativo", i + 1 === numero);
    });
    for (const { letra, item } of this.posicoes) item.classList.toggle("ativa", posicao.includes(letra));
  }
}

const MIOLOS = { valor: MioloValor, marcha: MioloMarcha };

/** Até dois dados importantes embaixo da leitura, cada um num container: nome à esquerda, número à direita. */
class Complementos {
  constructor(pai) {
    this.g = svg("g", {}, pai);
    this.itens = [];
  }

  configurar(definicoes) {
    this.g.replaceChildren();
    const [largura, vao, altura, margem, larguraValor] = [definicoes.length > 1 ? 92 : 104, 10, 26, 12, 34];
    const total = definicoes.length * largura + (definicoes.length - 1) * vao;
    this.itens = definicoes.map(({ rotulo }, i) => {
      const x = C - total / 2 + i * (largura + vao);
      const item = svg("g", { class: "complemento" }, this.g);
      svg("rect", { x, y: Y.complementos - altura / 2, width: largura, height: altura, rx: altura / 2 }, item);
      const larguraNome = largura - 2 * margem - larguraValor - 6;
      const nome = texto(item, "complemento-rotulo", Y.complementos, larguraNome, 10, x + margem);
      nome.definir(rotulo.toUpperCase());
      const valor = texto(item, "complemento-valor", Y.complementos, larguraValor, 16, x + largura - margem);
      return { item, nome, valor };
    });
  }

  atualizar(dados) {
    this.itens.forEach(({ item, valor }, i) => {
      item.style.visibility = dados[i] ? "visible" : "hidden";
      if (dados[i]) valor.definir(dados[i].texto);
    });
  }

  get textos() {
    return this.itens.flatMap((item) => [item.nome, item.valor]);
  }
}

/**
 * Mostrador de ponteiro: escala numerada, faixas de atenção e perigo, rastro colorido e leitura digital
 * com a unidade embaixo, mais um dado complementar no miolo e, se houver, dados importantes em containers.
 */
export class MostradorRedondo {
  constructor(el) {
    garantirDefinicoes();
    this.el = el;
    el.setAttribute("viewBox", `0 0 ${TAMANHO} ${TAMANHO}`);
    el.classList.add("redondo");
    el.dataset.nivel = "ok";
    svg("circle", { class: "face", cx: C, cy: C, r: RAIO.aro }, el);
    svg("circle", { class: "halo", cx: C, cy: C, r: RAIO.halo, filter: "url(#obd-brilho)" }, el);
    this.zonas = svg("g", {}, el);
    svg("path", { class: "trilho", d: arcoCompleto(RAIO.rastro) }, el);
    this.rastro = svg("path", { class: "rastro", d: arcoCompleto(RAIO.rastro), pathLength: 100 }, el);
    this.marcas = svg("g", {}, el);
    this.grupoMiolo = svg("g", { class: "miolo", "data-nivel": "ok" }, el);
    this.legenda = texto(el, "legenda", Y.legenda, 140, 13);
    this.valor = texto(el, "valor", Y.valor, LARGURA_VALOR, 60);
    this.unidade = texto(el, "etiqueta", Y.unidade, 120, 13);
    this.complementos = new Complementos(el);
    // ponteiro afinando para a ponta, com um brilho na cor do nível por baixo
    const { agulhaInicio: de, agulhaFim: ate } = RAIO;
    const ponteiro = `M ${C + de} ${C - 2.2} L ${C + ate} ${C - 0.8} L ${C + ate} ${C + 0.8} L ${C + de} ${C + 2.2} Z`;
    this.agulha = svg("g", { class: "agulha" }, el);
    svg("path", { class: "agulha-brilho", d: ponteiro, filter: "url(#obd-brilho)" }, this.agulha);
    svg("path", { class: "agulha-ponteiro", d: ponteiro }, this.agulha);
    svg("circle", { class: "aro", cx: C, cy: C, r: RAIO.aro }, el);
    this.miolo = null;
  }

  /** `passos`: passos possíveis dos números principais, em ordem de preferência (veja escolherPasso). */
  configurar({
    minimo, maximo, passos, intercalados = false, formatarRotulo = String,
    legenda = "", unidade = "", zonas = [], miolo = null, complementos = [],
  }) {
    this.escala = new Escala(minimo, maximo);
    this.legenda.definir(legenda.toUpperCase());
    this.unidade.definir(unidade.toUpperCase());

    this.zonas.replaceChildren();
    for (const { de, ate, nivel } of zonas) {
      if (ate > de) {
        svg("path", { class: `zona ${nivel}`, d: arco(RAIO.zona, this.escala.angulo(de), this.escala.angulo(ate)) },
          this.zonas);
      }
    }

    this.marcas.replaceChildren();
    const escolha = escolherPasso(minimo, maximo, passos, intercalados, formatarRotulo);
    this.el.classList.toggle("intercalado", escolha.intercalados);
    const passoMenor = escolha.passoMaior / 2;
    // numerada a partir do fim: o último número cai sempre no máximo (até 210: 10, 30, 50… 210)
    for (let k = 0; maximo - k * passoMenor >= minimo - 1e-9; k++) {
      const v = Math.round((maximo - k * passoMenor) * 1e6) / 1e6;
      const maior = k % 2 === 0;
      const angulo = this.escala.angulo(v);
      const [x1, y1] = polar(maior ? RAIO.marcaMaior : RAIO.marcaMenor, angulo);
      const [x2, y2] = polar(RAIO.marcaFim, angulo);
      svg("line", { class: maior ? "marca maior" : "marca", x1: f(x1), y1: f(y1), x2: f(x2), y2: f(y2) }, this.marcas);
      if (!maior && !escolha.intercalados) continue;
      const [tx, ty] = polar(RAIO.rotulo, angulo);
      const rotulo = formatarRotulo(v);
      const tamanho = !maior ? NUMERO.menor : escolha.intercalados ? NUMERO.intercalado : NUMERO.principal;
      // o primeiro número fica embaixo da agulha parada (carro parado, motor desligado): não é escrito
      const sobAgulhaParada = Math.abs(v - minimo) < 1e-9 && ty > Y.legenda - 14;
      if (sobAgulhaParada || encostaNosTextos(tx, ty, rotulo, tamanho)) continue;
      const classe = maior ? "numero-escala" : "numero-escala menor";
      svg("text", { class: classe, x: f(tx), y: f(ty) }, this.marcas).textContent = rotulo;
    }
    this.#microEscala(minimo, maximo, passoMenor);

    this.grupoMiolo.replaceChildren();
    this.miolo = miolo ? new MIOLOS[miolo.tipo ?? "valor"](this.grupoMiolo, miolo) : null;
    this.complementos.configurar(complementos);
  }

  /** Marquinhas curtas entre as marcas do meio, tantas quantas a densidade da escala permitir (ou nenhuma). */
  #microEscala(minimo, maximo, passoMenor) {
    const faixa = maximo - minimo;
    const divisoes = MICRO.divisoes
      .find((n) => distanciaNoArco(passoMenor / n, faixa, RAIO.marcaFim) >= MICRO.distanciaMinima);
    if (!divisoes) return;
    const passoMicro = passoMenor / divisoes;
    // a partir do fim, como as outras marcas; onde já existe marca maior ou do meio, não repete
    for (let j = 1; maximo - j * passoMicro >= minimo - 1e-9; j++) {
      if (j % divisoes === 0) continue;
      const angulo = this.escala.angulo(maximo - j * passoMicro);
      const [x1, y1] = polar(RAIO.marcaMicro, angulo);
      const [x2, y2] = polar(RAIO.marcaFim, angulo);
      svg("line", { class: "marca micro", x1: f(x1), y1: f(y1), x2: f(x2), y2: f(y2) }, this.marcas);
    }
  }

  /** `valor` null deixa a agulha na origem. */
  atualizar({ valor, nivel, texto: conteudo, miolo = null, complementos = [] }) {
    this.el.dataset.nivel = nivel;
    this.agulha.style.transform = `rotate(${f(this.escala.angulo(valor))}deg)`;
    this.escala.preencher(this.rastro, valor);
    this.valor.definir(conteudo);
    if (this.miolo && miolo) {
      this.grupoMiolo.dataset.nivel = miolo.nivel;
      this.miolo.atualizar(miolo);
    }
    this.complementos.atualizar(complementos);
  }

  remedir() {
    const textos = [this.legenda, this.valor, this.unidade, ...(this.miolo?.textos ?? []), ...this.complementos.textos];
    for (const item of textos) item.remedir();
  }
}

// --- ajustes da configuração, no mesmo formato redondo ---

// Linhas dos ajustes: seção e nome em cima, valor no centro, botões − e + na abertura de baixo do arco.
const AJUSTE = { secao: 112, nome: 140, valor: C + 2, unidade: C + 44, botoes: C + 108, status: 386 };

/** Botão redondo do desenho, acionável por toque e teclado; `data-acao` diz o que ele faz. */
function botao(pai, { acao, rotulo, simbolo, cx, cy, r = 32 }) {
  const g = svg("g", { class: "botao", "data-acao": acao, role: "button", tabindex: 0, "aria-label": rotulo }, pai);
  svg("circle", { cx, cy, r }, g);
  svg("text", { x: cx, y: cy }, g).textContent = simbolo;
  return g;
}

/** Face, aro, seção e nome do ajuste, e a linha de status (salvo ou erro) embaixo. */
class MolduraDeAjuste {
  constructor(el, { secao, rotulo }) {
    garantirDefinicoes();
    this.el = el;
    el.setAttribute("viewBox", `0 0 ${TAMANHO} ${TAMANHO}`);
    el.classList.add("redondo", "ajuste");
    el.dataset.nivel = "ok";
    svg("circle", { class: "face", cx: C, cy: C, r: RAIO.aro }, el);
    svg("circle", { class: "aro", cx: C, cy: C, r: RAIO.aro }, el);
    this.secao = texto(el, "legenda", AJUSTE.secao, 200, 13);
    this.secao.definir(secao.toUpperCase());
    this.nome = texto(el, "ajuste-nome", AJUSTE.nome, 240, 18);
    this.nome.definir(rotulo);
    this.status = texto(el, "ajuste-status", AJUSTE.status, 180, 13);
    this.textos = [this.secao, this.nome, this.status];
  }

  definirStatus(status, erro) {
    this.status.definir(status ?? "");
    this.status.el.classList.toggle("erro", Boolean(erro));
  }

  remedir() {
    for (const item of this.textos) item.remedir();
  }
}

/**
 * Ajuste de um número ou de uma opção: valor grande no centro, arco mostrando onde ele está entre o mínimo e o
 * máximo permitidos (numa opção, um segmento por opção) e botões − e + embaixo.
 */
export class MostradorAjuste extends MolduraDeAjuste {
  constructor(el, { secao, rotulo, opcoes = 0 }) {
    super(el, { secao, rotulo });
    svg("path", { class: "trilho", d: arcoCompleto(RAIO.rastro) }, el);
    if (opcoes) {
      const passo = VARREDURA / opcoes;
      this.segmentos = Array.from({ length: opcoes }, (_, i) => svg("path", {
        class: "degrau opcao", d: arco(RAIO.rastro, INICIO + i * passo + 2, INICIO + (i + 1) * passo - 2),
      }, el));
    } else {
      this.rastro = svg("path", { class: "rastro", d: arcoCompleto(RAIO.rastro), pathLength: 100 }, el);
      this.escala = new Escala(0, 1);
    }
    this.valor = texto(el, "valor", AJUSTE.valor, 240, 72);
    this.unidade = texto(el, "etiqueta", AJUSTE.unidade, 120, 13);
    const ladoBotao = 72;
    this.menos = botao(el, { acao: "menos", rotulo: "Diminuir", simbolo: "−", cx: C - ladoBotao, cy: AJUSTE.botoes });
    this.mais = botao(el, { acao: "mais", rotulo: "Aumentar", simbolo: "+", cx: C + ladoBotao, cy: AJUSTE.botoes });
    this.textos.push(this.valor, this.unidade);
  }

  /** `fracao` (0 a 1) para números; `opcao` (índice) para opções. */
  atualizar({ texto: conteudo, unidade = "", fracao = null, opcao = null, podeDiminuir, podeAumentar, status, erro }) {
    this.valor.definir(conteudo);
    this.unidade.definir(unidade.toUpperCase());
    if (this.rastro) this.escala.preencher(this.rastro, fracao);
    this.segmentos?.forEach((segmento, i) => segmento.classList.toggle("ativo", i === opcao));
    for (const [el, pode] of [[this.menos, podeDiminuir], [this.mais, podeAumentar]]) {
      el.classList.toggle("desabilitado", !pode);
      el.setAttribute("aria-disabled", String(!pode));
    }
    this.definirStatus(status, erro);
  }
}

/** Lista de itens que se ligam e desligam com um toque (ex.: quais mostradores aparecem no painel). */
export class MostradorLista extends MolduraDeAjuste {
  constructor(el, { secao, rotulo, itens }) {
    super(el, { secao, rotulo });
    const [largura, altura, primeira, passo] = [196, 30, 178, 38];
    this.linhas = itens.map(({ valor, rotulo: nome }, i) => {
      const y = primeira + i * passo;
      const g = svg("g", {
        class: "linha", "data-acao": "alternar", "data-valor": valor, role: "switch", tabindex: 0, "aria-label": nome,
      }, el);
      svg("rect", { class: "linha-fundo", x: C - largura / 2, y: y - altura / 2, width: largura, height: altura,
        rx: altura / 2 }, g);
      const rotuloLinha = texto(g, "linha-nome", y, 120, 15, C - largura / 2 + 16);
      rotuloLinha.definir(nome);
      svg("rect", { class: "chave", x: C + largura / 2 - 50, y: y - 9, width: 34, height: 18, rx: 9 }, g);
      const botaoDaChave = svg("circle", { class: "chave-botao", cx: C + largura / 2 - 41, cy: y, r: 6 }, g);
      this.textos.push(rotuloLinha);
      return { valor, g, botaoDaChave, x: C + largura / 2 - 41 };
    });
  }

  atualizar({ marcados, status, erro }) {
    for (const { valor, g, botaoDaChave, x } of this.linhas) {
      const ligado = marcados.has(valor);
      g.classList.toggle("ligado", ligado);
      g.setAttribute("aria-checked", String(ligado));
      botaoDaChave.setAttribute("cx", ligado ? x + 16 : x);
    }
    this.definirStatus(status, erro);
  }
}
