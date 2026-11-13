import { MOSTRADORES, formatar, nomeDoMostrador } from "./indicadores.js";
import { MostradorAjuste, MostradorLista, svg } from "./mostrador.js";
import { Navegacao } from "./navegacao.js";

// Espera depois do último toque antes de salvar: vários toques seguidos viram uma gravação só.
const SALVAR_APOS_MS = 400;
const MOSTRAR_SALVO_MS = 2500;

/*
 * Cada ajuste mexe num campo da configuração (as mesmas regras de leitor/config.py):
 * - números andam de `passo` em `passo` dentro de limites(config), que dependem dos outros campos
 *   (o amarelo fica abaixo do vermelho, e o vermelho até o máximo da escala); escala(config) é a faixa do arco;
 * - opcoes: [valor, nome] alternados com − e +; lista: quais mostradores aparecem no painel.
 */
// O máximo da escala anda de passo em passo, nos mesmos múltiplos que o leitor aceita.
const multiploAcima = (valor, passo) => Math.ceil(valor / passo) * passo;
// Só nas marcas principais ou também nas do meio, intercalados (quando couber no mostrador).
const NUMEROS_DA_ESCALA = [["principais", "Principais"], ["intercalados", "Intercalados"]];

const AJUSTES = [
  {
    chave: "velocidade-maximo", secao: "velocidade", campo: "maximo", titulo: "Velocímetro",
    rotulo: "Máximo da escala", unidade: "km/h", passo: 10,
    limites: (c) => [multiploAcima(Math.max(100, c.velocidade.perigo), 10), 400], escala: () => [100, 400],
  },
  {
    chave: "velocidade-atencao", secao: "velocidade", campo: "atencao", titulo: "Velocímetro", nivel: "atencao",
    rotulo: "Amarelo a partir de", unidade: "km/h", passo: 5,
    limites: (c) => [5, c.velocidade.perigo - 5], escala: (c) => [0, c.velocidade.maximo],
  },
  {
    chave: "velocidade-perigo", secao: "velocidade", campo: "perigo", titulo: "Velocímetro", nivel: "perigo",
    rotulo: "Vermelho a partir de", unidade: "km/h", passo: 5,
    limites: (c) => [c.velocidade.atencao + 5, c.velocidade.maximo], escala: (c) => [0, c.velocidade.maximo],
  },
  {
    chave: "velocidade-numeros", secao: "velocidade", campo: "numeros", titulo: "Velocímetro",
    rotulo: "Números da escala", opcoes: NUMEROS_DA_ESCALA,
  },
  {
    chave: "rpm-maximo", secao: "rpm", campo: "maximo", titulo: "Rotação",
    rotulo: "Máximo da escala", unidade: "rpm", passo: 1000,
    limites: (c) => [multiploAcima(Math.max(4000, c.rpm.perigo), 1000), 10000], escala: () => [4000, 10000],
  },
  {
    chave: "rpm-atencao", secao: "rpm", campo: "atencao", titulo: "Rotação", nivel: "atencao",
    rotulo: "Amarelo a partir de", unidade: "rpm", passo: 250,
    limites: (c) => [250, c.rpm.perigo - 250], escala: (c) => [0, c.rpm.maximo],
  },
  {
    chave: "rpm-perigo", secao: "rpm", campo: "perigo", titulo: "Rotação", nivel: "perigo",
    rotulo: "Vermelho a partir de", unidade: "rpm", passo: 250,
    limites: (c) => [c.rpm.atencao + 250, c.rpm.maximo], escala: (c) => [0, c.rpm.maximo],
  },
  {
    chave: "rpm-numeros", secao: "rpm", campo: "numeros", titulo: "Rotação",
    rotulo: "Números da escala", opcoes: NUMEROS_DA_ESCALA,
  },
  {
    chave: "rpm-centro", secao: "rpm", campo: "centro", titulo: "Rotação", rotulo: "No centro",
    opcoes: [["consumo", "Consumo"], ["esforco", "Esforço"]],
  },
  {
    chave: "tanque-capacidade", secao: "tanque", campo: "capacidade_l", titulo: "Tanque",
    rotulo: "Capacidade", unidade: "litros", passo: 1, limites: () => [20, 150], escala: () => [20, 150],
  },
  {
    chave: "tanque-centro", secao: "tanque", campo: "centro", titulo: "Tanque", rotulo: "No centro",
    opcoes: [["litros", "Litros"], ["etanol", "Etanol"]],
  },
  { chave: "mostradores", titulo: "Painel", rotulo: "Mostradores exibidos", lista: true },
];

const container = document.getElementById("ajustes");
let config = null;
let itens = [];
let pendentes = {};
let temporizadorSalvar = null;
let status = { texto: "", erro: false };

// Segurar o dedo num ajuste volta ao painel; sozinho (tela redonda), volta ao primeiro mostrador sozinho.
const navegacao = new Navegacao(container, "ajuste", {
  aoSegurar: (unico) => location.assign(unico ? `/?mostrador=${config.mostradores[0]}` : "/"),
});

/** Cópia de `base` com `alteracao` aplicada em profundidade (listas são trocadas inteiras). */
function mesclar(base, alteracao) {
  const resultado = structuredClone(base);
  for (const [chave, valor] of Object.entries(alteracao)) {
    const objeto = valor && typeof valor === "object" && !Array.isArray(valor);
    resultado[chave] = objeto ? mesclar(resultado[chave] ?? {}, valor) : valor;
  }
  return resultado;
}

function montar() {
  itens = AJUSTES.map((ajuste) => {
    const el = document.createElement("div");
    el.className = "mostrador";
    el.tabIndex = -1;
    el.dataset.chave = ajuste.chave;
    el.setAttribute("role", "group");
    el.setAttribute("aria-label", `${ajuste.titulo}: ${ajuste.rotulo}`);
    const desenho = svg("svg", {}, el);
    // os textos só são medidos com o desenho já na página
    container.append(el);
    const mostrador = ajuste.lista
      ? new MostradorLista(desenho, {
        secao: ajuste.titulo, rotulo: ajuste.rotulo,
        itens: MOSTRADORES.map((chave) => ({ valor: chave, rotulo: nomeDoMostrador(chave, config) })),
      })
      : new MostradorAjuste(desenho, { secao: ajuste.titulo, rotulo: ajuste.rotulo, opcoes: ajuste.opcoes?.length });
    if (ajuste.nivel) desenho.dataset.nivel = ajuste.nivel; // amarelo e vermelho já aparecem na cor da faixa
    return { chave: ajuste.chave, el, ajuste, mostrador, remedir: () => mostrador.remedir() };
  });
  navegacao.definirItens(itens);
}

function desenhar() {
  for (const { ajuste, mostrador } of itens) {
    if (ajuste.lista) {
      mostrador.atualizar({ marcados: new Set(config.mostradores), status: status.texto, erro: status.erro });
      continue;
    }
    const valor = config[ajuste.secao][ajuste.campo];
    const comum = { status: status.texto, erro: status.erro };
    if (ajuste.opcoes) {
      const opcao = ajuste.opcoes.findIndex(([chave]) => chave === valor);
      const texto = ajuste.opcoes[opcao]?.[1] ?? valor;
      mostrador.atualizar({ ...comum, texto, opcao, podeDiminuir: true, podeAumentar: true });
      continue;
    }
    const [minimo, maximo] = ajuste.limites(config);
    const [de, ate] = ajuste.escala(config);
    mostrador.atualizar({
      ...comum, texto: formatar(valor), unidade: ajuste.unidade, fracao: (valor - de) / (ate - de),
      podeDiminuir: valor > minimo, podeAumentar: valor < maximo,
    });
  }
}

function avisar(texto, erro = false) {
  status = { texto, erro };
  desenhar();
  if (!erro && texto === "salvo") {
    setTimeout(() => {
      if (status.texto === "salvo") avisar("");
    }, MOSTRAR_SALVO_MS);
  }
}

function alterar({ ajuste }, acao, valorDaLinha) {
  if (ajuste.lista) {
    const marcados = new Set(config.mostradores);
    if (marcados.has(valorDaLinha)) marcados.delete(valorDaLinha);
    else marcados.add(valorDaLinha);
    if (marcados.size === 0) return avisar("deixe ao menos um mostrador", true);
    return mudar({ mostradores: MOSTRADORES.filter((chave) => marcados.has(chave)) });
  }
  const atual = config[ajuste.secao][ajuste.campo];
  const direcao = acao === "mais" ? 1 : -1;
  let novo;
  if (ajuste.opcoes) {
    const total = ajuste.opcoes.length;
    const indice = ajuste.opcoes.findIndex(([chave]) => chave === atual);
    novo = ajuste.opcoes[(indice + direcao + total) % total][0];
  } else {
    const [minimo, maximo] = ajuste.limites(config);
    novo = Math.min(maximo, Math.max(minimo, atual + direcao * ajuste.passo));
    if (novo === atual) return;
  }
  mudar({ [ajuste.secao]: { [ajuste.campo]: novo } });
}

function mudar(alteracao) {
  config = mesclar(config, alteracao);
  pendentes = mesclar(pendentes, alteracao);
  avisar("salvando…");
  clearTimeout(temporizadorSalvar);
  temporizadorSalvar = setTimeout(salvar, SALVAR_APOS_MS);
}

async function salvar() {
  const enviar = pendentes;
  pendentes = {};
  try {
    const resposta = await fetch("/api/config", {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(enviar),
    });
    const corpo = await resposta.json();
    if (!resposta.ok) throw new Error(corpo.erro ?? `erro ${resposta.status}`);
    // se o usuário mexeu de novo enquanto salvava, fica com o que está na tela até a próxima gravação
    if (Object.keys(pendentes).length === 0) config = corpo;
    avisar("salvo");
  } catch (erro) {
    avisar(erro.message || "não foi possível salvar", true);
    await recarregar();
  }
}

/** Volta para a configuração que está valendo no leitor. */
async function recarregar() {
  try {
    config = await (await fetch("/api/config")).json();
    pendentes = {};
    desenhar();
  } catch {
    // leitor fora do ar: a tela fica como está e o erro continua à vista
  }
}

container.addEventListener("click", (evento) => {
  const alvo = evento.target.closest("[data-acao]");
  if (!alvo || alvo.classList.contains("desabilitado")) return;
  const item = itens.find(({ el }) => el.contains(alvo));
  if (item) alterar(item, alvo.dataset.acao, alvo.dataset.valor);
});

// botões do desenho respondem a Enter e Espaço como um botão comum
container.addEventListener("keydown", (evento) => {
  if (!["Enter", " "].includes(evento.key) || !evento.target.closest?.("[data-acao]")) return;
  evento.preventDefault();
  evento.target.dispatchEvent(new MouseEvent("click", { bubbles: true }));
});

async function iniciar() {
  try {
    config = await (await fetch("/api/config")).json();
  } catch {
    container.textContent = "Não foi possível falar com o leitor. Ele está rodando com --painel?";
    return;
  }
  montar();
  desenhar();
}

iniciar();
