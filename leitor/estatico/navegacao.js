// Grade de mostradores redondos e o modo "um só", como roda na tela redonda: ?<parametro>=<chave>.
const SEGURAR_MS = 700;

/**
 * Na grade, tocar num item abre ele sozinho; sozinho, tocar passa para o próximo, as setas navegam e Esc volta.
 * Segurar o dedo num item chama `aoSegurar(unico)`: na tela redonda é o caminho entre o painel e as configurações.
 * Itens: { chave, el, remedir() }. Toques em elementos com data-acao (botões dos ajustes) não navegam.
 */
export class Navegacao {
  #itens = [];
  #segurou = false;

  constructor(container, parametro, { aoSegurar = null } = {}) {
    Object.assign(this, { container, parametro, aoSegurar });
    container.addEventListener("click", (evento) => this.#tocar(evento));
    window.addEventListener("keydown", (evento) => this.#tecla(evento));
    window.addEventListener("popstate", () => this.#mostrarSo(this.chaveDaUrl()));
    if (aoSegurar) this.#detectarSegurar();
    // os textos foram medidos com a fonte de reserva; quando a fonte da página chega, mede de novo
    document.fonts?.ready.then(() => this.#remedir());
  }

  get unico() {
    return document.body.classList.contains("unico");
  }

  chaveDaUrl() {
    return new URLSearchParams(location.search).get(this.parametro);
  }

  definirItens(itens) {
    this.#itens = itens;
    this.#mostrarSo(this.chaveDaUrl());
  }

  navegar(chave, substituir = false) {
    const url = chave ? `?${this.parametro}=${chave}` : location.pathname;
    history[substituir ? "replaceState" : "pushState"](null, "", url);
    this.#mostrarSo(chave);
  }

  #mostrarSo(chave) {
    const alvo = this.#itens.find((item) => item.chave === chave);
    document.body.classList.toggle("unico", alvo !== undefined);
    for (const item of this.#itens) item.el.classList.toggle("ativo", item === alvo);
    // quem estava escondido mediu os textos com largura zero
    this.#remedir();
    alvo?.el.focus({ preventScroll: true });
  }

  #remedir() {
    for (const item of this.#itens) item.remedir();
  }

  #vizinho(passo) {
    const atual = this.#itens.findIndex((item) => item.chave === this.chaveDaUrl());
    return this.#itens[(atual + passo + this.#itens.length) % this.#itens.length].chave;
  }

  #tocar(evento) {
    if (this.#segurou) return; // o toque longo já foi atendido
    const el = evento.target.closest(".mostrador");
    if (!el || evento.target.closest("[data-acao]")) return;
    if (this.unico) this.navegar(this.#vizinho(1), true);
    else this.navegar(el.dataset.chave);
  }

  #tecla(evento) {
    if (!this.unico) return;
    if (evento.key === "ArrowRight") this.navegar(this.#vizinho(1), true);
    if (evento.key === "ArrowLeft") this.navegar(this.#vizinho(-1), true);
    if (evento.key === "Escape") this.navegar(null);
  }

  #detectarSegurar() {
    let temporizador = null;
    const cancelar = () => clearTimeout(temporizador);
    this.container.addEventListener("pointerdown", (evento) => {
      this.#segurou = false;
      if (!evento.target.closest(".mostrador") || evento.target.closest("[data-acao]")) return;
      cancelar();
      temporizador = setTimeout(() => {
        this.#segurou = true;
        this.aoSegurar(this.unico);
      }, SEGURAR_MS);
    });
    for (const tipo of ["pointerup", "pointercancel", "pointerleave"]) this.container.addEventListener(tipo, cancelar);
  }
}
