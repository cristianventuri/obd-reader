import { MostradorRedondo, passoBonito, svg } from "./mostrador.js";

const MOTOR_FRIO_C = 60;
// Até chegar a primeira leitura da pressão atmosférica, o turbo usa a do nível do mar.
const BAROMETRICA_PADRAO_KPA = 100;
// Consumo (estimado pelo leitor): alertas andando em km/l e parado em L/h, e o gasto que enche o anel.
const CONSUMO = {
  andando: { atencao: 10, perigo: 7 }, kmlAnelCheio: 22,
  parado: { atencao: 2, perigo: 2.7 }, lhAnelCheio: 4.5,
};

// Leitura de painel: casas fixas, sem separador de milhar ("4435 rpm") e sem "-0" quando arredonda para zero.
export const formatar = (valor, casas = 0) => valor.toLocaleString("pt-BR", {
  minimumFractionDigits: casas, maximumFractionDigits: casas, useGrouping: false, signDisplay: "negative",
});

// O que pode ir no centro da rotação (config rpm.centro).
const CENTROS_DA_ROTACAO = {
  consumo: {
    rotulo: "Consumo", campo: "consumo_lh", casas: 1, faixa: [0, 1],
    descricao: "No centro, o consumo: km/l andando e litros por hora parado. O anel enche e muda de cor quanto "
      + "mais o carro gasta.",
    valor: (e) => (e.consumo_kml == null ? e.consumo_lh : Math.min(e.consumo_kml, 99.9)),
    unidade: (e) => (e.consumo_kml == null ? "L/h" : "km/l"),
    fracaoDoAnel: (v, e) => (e.consumo_kml == null ? v / CONSUMO.lhAnelCheio : 1 - v / CONSUMO.kmlAnelCheio),
    nivel: (v, e) => {
      const nivel = e.consumo_kml == null ? nivelPorLimites(v, CONSUMO.parado)
        : nivelPorLimites(v, CONSUMO.andando, "abaixo");
      return nivel === "ok" ? "bom" : nivel;
    },
  },
  esforco: {
    rotulo: "Esforço", campo: "carga_absoluta_pct", unidade: "%", faixa: [0, 200],
    descricao: "No centro, o esforço do motor: quanto do ar que ele consegue puxar está sendo usado. "
      + "Acima de 100% é o turbo empurrando ar a mais.",
  },
};

// O que pode ir no centro do tanque (config tanque.centro); os litros saem da capacidade configurada.
const centrosDoTanque = (capacidade) => ({
  litros: {
    rotulo: "No tanque", campo: "tanque_pct", unidade: "L",
    descricao: "No centro, os litros que sobraram (estimativa pela capacidade configurada).",
    valor: (e) => (e.tanque_pct * capacidade) / 100,
  },
  etanol: {
    rotulo: "Etanol", campo: "etanol_pct", unidade: "%", faixa: [0, 100],
    descricao: "No centro, quanto do combustível é etanol.",
  },
});

/*
 * Cada indicador vira um mostrador redondo; a função recebe a configuração do painel (config.json).
 * - rotulo: nome escrito abaixo do miolo; unidade: etiqueta embaixo da leitura; descricao: o que cada número
 *   significa (ao passar o mouse).
 * - campo: dado da leitura que move a agulha e diz se o mostrador está atualizado;
 *   valor(estado) só quando a agulha mostra uma conta sobre a leitura.
 * - marcas { passos, formatarRotulo }: passos possíveis dos números principais; intercalados: número também
 *   nas marcas do meio, quando couber.
 * - limites { atencao, perigo } pintam as faixas e o alerta; sentido: "acima" (padrão), "abaixo" ou "absoluto" (±).
 *   nivel(valor, estado) devolve um nível próprio ou null para seguir os limites.
 * - miolo: dado complementar do centro (tipo "valor" ou "marcha"), com campo, limites e faixa próprios;
 *   valor(estado), unidade(estado) e fracaoDoAnel(valor, estado) quando dependem de mais de um dado.
 * - complementos: só dados importantes (até dois), cada um num container embaixo da leitura;
 *   valor(estado) devolve o número ou null para esconder o container.
 * As chaves e a ordem são as mesmas de MOSTRADORES em leitor/config.py.
 */
const DEFINICOES = {
  velocidade: ({ velocidade: { maximo, atencao, perigo, numeros } }) => ({
    rotulo: "Velocidade", unidade: "km/h", campo: "velocidade_kmh",
    descricao: "Velocidade do carro, amarela e vermelha a partir dos limites configurados. No centro, a marcha "
      + "engatada e a posição da alavanca do câmbio (P R N D).",
    faixa: [0, maximo], limites: { atencao, perigo },
    marcas: { passos: [20, 40, 50, 100] }, intercalados: numeros === "intercalados",
    miolo: { tipo: "marcha", campo: "marcha" },
  }),
  rpm: ({ rpm: { maximo, atencao, perigo, centro, numeros } }) => ({
    rotulo: "Rotação", unidade: "rpm", campo: "rpm",
    descricao: `Rotação do motor (a escala está em milhares de rpm). ${CENTROS_DA_ROTACAO[centro].descricao}`,
    faixa: [0, maximo], limites: { atencao, perigo },
    marcas: { passos: [1000, 2000], formatarRotulo: (v) => formatar(v / 1000, v % 1000 ? 1 : 0) },
    intercalados: numeros === "intercalados",
    miolo: CENTROS_DA_ROTACAO[centro],
  }),
  turbo: () => ({
    rotulo: "Turbo", unidade: "bar", casas: 2, campo: "map_kpa",
    descricao: "Pressão do turbo acima da atmosfera; negativo é vácuo, com o turbo ainda sem empurrar ar. "
      + "No centro, quanto o acelerador está pisado.",
    valor: (e) => (e.map_kpa - (e.barometrica_kpa ?? BAROMETRICA_PADRAO_KPA)) / 100,
    faixa: [-1, 1.5],
    miolo: { rotulo: "Acelerador", campo: "pedal_pct", unidade: "%", faixa: [0, 100] },
  }),
  temp_motor: () => ({
    rotulo: "Motor", unidade: "°C", campo: "temp_motor_c",
    descricao: "Temperatura do motor (água do radiador); o fundo fica azulado enquanto o motor está frio. "
      + "No centro, a temperatura do ar que entra no motor.",
    faixa: [40, 140], limites: { atencao: 103, perigo: 110 },
    nivel: (v) => (v < MOTOR_FRIO_C ? "frio" : null),
    miolo: { rotulo: "Ar admitido", campo: "temp_ar_c", unidade: "°C" },
  }),
  tanque: ({ tanque: { capacidade_l: capacidade, centro } }) => {
    const miolo = centrosDoTanque(capacidade)[centro];
    return {
      rotulo: "Tanque", unidade: "%", campo: "tanque_pct",
      descricao: `Nível do tanque. ${miolo.descricao}`,
      faixa: [0, 100], limites: { atencao: 25, perigo: 12 }, sentido: "abaixo",
      miolo,
    };
  },
};

/** Todos os mostradores, na ordem padrão. */
export const MOSTRADORES = Object.keys(DEFINICOES);

/** Os mostradores exibidos, na ordem da configuração. */
export const definicoesDaConfig = (config) => config.mostradores
  .filter((chave) => chave in DEFINICOES)
  .map((chave) => ({ chave, ...DEFINICOES[chave](config) }));

/** Nome de um mostrador, para a tela de configurações. */
export const nomeDoMostrador = (chave, config) => DEFINICOES[chave](config).rotulo;

// Faixas âmbar/vermelha a partir dos limites de atenção/perigo e do sentido do alerta.
function zonasDe({ faixa: [minimo, maximo], limites = {}, sentido = "acima" }) {
  const { atencao = null, perigo = null } = limites;
  const zonas = [];
  const faixa = (de, ate, nivel) => {
    const [inicio, fim] = [Math.max(de, minimo), Math.min(ate, maximo)];
    if (fim > inicio) zonas.push({ de: inicio, ate: fim, nivel });
  };
  if (sentido === "abaixo") {
    if (atencao !== null) faixa(perigo ?? minimo, atencao, "atencao");
    if (perigo !== null) faixa(minimo, perigo, "perigo");
  } else if (sentido === "absoluto") {
    if (atencao !== null) {
      faixa(atencao, perigo ?? maximo, "atencao");
      faixa(perigo === null ? minimo : -perigo, -atencao, "atencao");
    }
    if (perigo !== null) {
      faixa(perigo, maximo, "perigo");
      faixa(minimo, -perigo, "perigo");
    }
  } else {
    if (atencao !== null) faixa(atencao, perigo ?? maximo, "atencao");
    if (perigo !== null) faixa(perigo, maximo, "perigo");
  }
  return zonas;
}

// Passos possíveis dos números da escala (o mostrador escolhe o que cabe) e as casas decimais deles.
function marcasDe({ faixa: [minimo, maximo], marcas = {}, intercalados = false }) {
  const { passos = [passoBonito(minimo, maximo)], ...resto } = marcas;
  const menorNumerado = Math.min(...passos) / (intercalados ? 2 : 1);
  const casas = Math.max(0, -Math.floor(Math.log10(menorNumerado) + 1e-9));
  return { passos, intercalados, formatarRotulo: (v) => formatar(v, casas), ...resto };
}

function nivelPorLimites(valor, { atencao = null, perigo = null } = {}, sentido = "acima") {
  if (typeof valor !== "number") return "ok";
  const medida = sentido === "absoluto" ? Math.abs(valor) : valor;
  const passou = (limite) => limite !== null && (sentido === "abaixo" ? medida <= limite : medida >= limite);
  return passou(perigo) ? "perigo" : passou(atencao) ? "atencao" : "ok";
}

/** Um mostrador na página: monta o desenho a partir da definição e o atualiza a cada estado novo. */
export class Indicador {
  constructor(definicao, pai) {
    this.definicao = definicao;
    this.chave = definicao.chave;
    this.el = document.createElement("button");
    this.el.type = "button";
    this.el.className = "mostrador desatualizado";
    this.el.dataset.chave = definicao.chave;
    this.el.setAttribute("aria-label", definicao.rotulo);
    this.el.title = definicao.descricao;
    const desenho = svg("svg", { "aria-hidden": "true" }, this.el);
    // os textos só são medidos com o desenho já na página
    pai.append(this.el);
    this.mostrador = new MostradorRedondo(desenho);
    const [minimo, maximo] = definicao.faixa;
    this.mostrador.configurar({
      minimo, maximo, ...marcasDe(definicao),
      legenda: definicao.rotulo, unidade: definicao.unidade,
      zonas: zonasDe(definicao), miolo: definicao.miolo, complementos: definicao.complementos ?? [],
    });
    this.mostrador.atualizar({ valor: null, nivel: "ok", texto: "–", miolo: this.#miolo({}) });
  }

  atualizar(estado) {
    const definicao = this.definicao;
    const bruto = estado[definicao.campo];
    const valor = bruto == null ? null : definicao.valor ? definicao.valor(estado) : bruto;
    const numerico = typeof valor === "number" && Number.isFinite(valor);
    const nivel = !numerico ? "ok"
      : definicao.nivel?.(valor, estado) ?? nivelPorLimites(valor, definicao.limites, definicao.sentido);
    this.mostrador.atualizar({
      valor: numerico ? valor : null,
      nivel,
      texto: numerico ? formatar(valor, definicao.casas) : "–",
      miolo: this.#miolo(estado),
      complementos: this.#complementos(estado),
    });
  }

  #miolo(estado) {
    const miolo = this.definicao.miolo;
    if (!miolo) return null;
    const bruto = estado[miolo.campo] ?? null;
    const valor = bruto === null ? null : miolo.valor ? miolo.valor(estado) : bruto;
    const unidade = typeof miolo.unidade === "function" ? miolo.unidade(estado) : miolo.unidade ?? "";
    if (valor === null) return { valor, anel: null, texto: "–", unidade, nivel: "ok" };
    const nivel = miolo.nivel?.(valor, estado) ?? nivelPorLimites(valor, miolo.limites, miolo.sentido);
    if (typeof valor !== "number") return { valor, anel: null, texto: String(valor), unidade, nivel };
    const anel = miolo.fracaoDoAnel ? miolo.fracaoDoAnel(valor, estado) : valor;
    return { valor, anel, texto: formatar(valor, miolo.casas), unidade, nivel };
  }

  #complementos(estado) {
    return (this.definicao.complementos ?? []).map(({ valor, casas }) => {
      const numero = valor(estado);
      return Number.isFinite(numero) ? { texto: formatar(numero, casas) } : null;
    });
  }

  /** Esmaece quando o dado principal não chega há `limiteMs`. */
  vigiar(atualizadoEm, agora, limiteMs) {
    const recebido = atualizadoEm[this.definicao.campo];
    this.el.classList.toggle("desatualizado", recebido === undefined || agora - recebido > limiteMs);
  }

  remedir() {
    this.mostrador.remedir();
  }
}
