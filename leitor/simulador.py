"""Simulador: leituras de um trajeto inventado, no mesmo formato do Coletor, para usar o leitor e o painel sem carro."""
import asyncio
import logging
import math
from collections.abc import AsyncIterator

from .coleta import Leitura

log = logging.getLogger(__name__)

PASSO_S = 0.1  # tempo simulado entre leituras rápidas, perto do ritmo real do ELM327
MARCHA_A_CADA = 2
LENTOS_A_CADA = 3

RALENTI_RPM = 850
RELACOES = {1: 105, 2: 58, 3: 38, 4: 29, 5: 24, 6: 20}  # rpm por km/h em cada marcha do câmbio automático
RELACAO_RE = 110
FRENAGEM_KMH_S = 10
BAROMETRICA_KPA = 100
ETANOL_PCT = 30  # gasolina comum vendida no Brasil
TANQUE_INICIAL_PCT = 34
KM_DESDE_LIMPEZA = 11086

# Trajeto repetido em loop: (segundos, velocidade alvo em km/h, pedal % para chegar nela, alavanca do câmbio).
# Passa por P, R, N e D com as trocas de marcha, arranca com pé no fundo (turbo cheio e giro na faixa vermelha)
# e volta a estacionar. Pedal 0 = segue no embalo ou freia até o alvo.
ROTEIRO = (
    (5, 0, 0, "P"),
    (5, 6, 20, "R"),       # manobra de ré
    (2, 0, 0, "R"),
    (2, 0, 0, "N"),
    (12, 50, 40, "D"),     # saída tranquila
    (8, 50, 0, "D"),       # cidade
    (6, 0, 0, "D"),        # parando no semáforo
    (11, 100, 100, "D"),   # arrancada com pé no fundo
    (12, 100, 0, "D"),     # estrada
    (10, 0, 0, "D"),       # freando até parar
    (3, 0, 0, "N"),
    (4, 0, 0, "P"),
)
DURACAO_ROTEIRO_S = sum(etapa[0] for etapa in ROTEIRO)

# Cada bloco chega numa leitura separada, como as consultas de até 6 PIDs lentos do Coletor.
BLOCOS_LENTOS = (
    ("temp_motor_c", "temp_ar_c", "temp_ambiente_c", "tanque_pct", "tensao_v", "barometrica_kpa"),
    ("pressao_turbo_kpa", "avanco_graus", "borboleta_pct", "pedal_pct", "carga_calculada_pct", "temp_catalisador_c"),
    ("luz_injecao", "codigos_falha", "ajuste_curto_pct", "ajuste_longo_pct", "lambda_sonda", "tempo_motor_s",
     "km_desde_limpeza"),
    ("etanol_pct",),
)


def _aproximar(atual: float, alvo: float, taxa: float) -> float:
    return atual + (alvo - atual) * taxa


class Simulador:
    """Gera leituras de um carro rodando o ROTEIRO, sem Bluetooth: rápidos todo ciclo, marcha e lentos em rodízio."""

    def __init__(self, intervalo_s: float = PASSO_S):
        self.intervalo_s = intervalo_s  # espera real entre ciclos; o tempo simulado sempre anda PASSO_S
        self.tempo = 0.0
        self.velocidade = 0.0
        self.pedal = 0.0
        self.rpm = float(RALENTI_RPM)
        self.carga = 16.0
        self.catalisador = 350.0
        self.marcha = 1
        self.alavanca = "P"

    async def ler(self) -> AsyncIterator[Leitura]:
        """Gera uma leitura por "resposta do carro", para sempre."""
        log.info("simulador: trajeto de %d s em loop, sem Bluetooth", DURACAO_ROTEIRO_S)
        ciclo = 0
        while True:
            ciclo += 1
            self._avancar()
            yield self._leitura(self._rapidos())
            if ciclo % MARCHA_A_CADA == 0:
                yield self._leitura(self._marcha())
            if ciclo % LENTOS_A_CADA == 0:
                lentos = self._lentos()
                bloco = BLOCOS_LENTOS[(ciclo // LENTOS_A_CADA) % len(BLOCOS_LENTOS)]
                yield self._leitura({nome: lentos[nome] for nome in bloco})
            await asyncio.sleep(self.intervalo_s)

    def _leitura(self, valores: dict[str, object]) -> Leitura:
        return Leitura(round(self.tempo, 3), valores)

    def _etapa(self) -> tuple[int, int, int, str]:
        t = self.tempo % DURACAO_ROTEIRO_S
        for etapa in ROTEIRO:
            if t < etapa[0]:
                return etapa
            t -= etapa[0]
        return ROTEIRO[-1]

    def _avancar(self) -> None:
        self.tempo += PASSO_S
        _, alvo, pedal_arrancada, self.alavanca = self._etapa()
        if self.alavanca in ("P", "N"):
            alvo = 0
        diferenca = alvo - self.velocidade
        if diferenca > 1:
            pedal = pedal_arrancada or 30
            aceleracao = (2 + pedal * 0.1) * max(0.35, 1 - self.velocidade / 220)  # km/h por segundo
            self.velocidade += min(diferenca, aceleracao * PASSO_S)
        elif diferenca < -1:
            pedal = 0
            self.velocidade -= min(-diferenca, FRENAGEM_KMH_S * PASSO_S)
        else:
            pedal = 8 + alvo * 0.15 if alvo else 0  # só o necessário para manter a velocidade
            self.velocidade = _aproximar(self.velocidade, alvo, 0.3)
        self.pedal = _aproximar(self.pedal, pedal, 0.3)

        if self.alavanca == "D":
            self._trocar_marcha()
            rpm = self.velocidade * RELACOES[self.marcha]
        elif self.alavanca == "R":
            rpm = self.velocidade * RELACAO_RE
        else:
            rpm = 0
        self.rpm = _aproximar(self.rpm, max(RALENTI_RPM, rpm), 0.5)
        self.carga = _aproximar(self.carga, 16 + self.pedal * 1.55, 0.3)
        self.catalisador = _aproximar(self.catalisador, 350 + self.carga * 2.6, 0.01)

    def _trocar_marcha(self) -> None:
        """Sobe mais tarde quanto mais fundo o pedal; desce quando o giro cai demais (ou no pé no fundo)."""
        # subir / descer >= 2 em qualquer pedal, mais que o salto entre marchas: a troca nunca fica indo e voltando
        rpm = self.velocidade * RELACOES[self.marcha]
        if self.marcha < 6 and rpm > 1800 + 52 * self.pedal:
            self.marcha += 1
        elif self.marcha > 1 and rpm < 900 + 25 * self.pedal:
            self.marcha -= 1

    def _rapidos(self) -> dict[str, object]:
        return {
            "rpm": float(round(self.rpm + 15 * math.sin(self.tempo * 9))),
            "velocidade_kmh": round(self.velocidade),
            "carga_absoluta_pct": round(self.carga, 1),
            "lambda_comandado": self._lambda_comandado(),
            "map_kpa": round(22 + self.carga * 1.15),
        }

    def _lambda_comandado(self) -> float:
        return 0.86 if self.carga > 130 else 1.0  # o motor enriquece a mistura em carga alta

    def _marcha(self) -> dict[str, object]:
        if self.alavanca in ("P", "N"):
            return {"marcha": self.alavanca, "estacionado": self.alavanca == "P"}
        return {"marcha": "R" if self.alavanca == "R" else str(self.marcha)}

    def _lentos(self) -> dict[str, object]:
        t = self.tempo
        return {
            "temp_motor_c": round(45 + 47 * (1 - math.exp(-t / 80))),  # aquecendo depois da partida
            "temp_ar_c": round(28 + self.carga * 0.07),
            "temp_ambiente_c": 26,
            "tanque_pct": round(max(0.0, TANQUE_INICIAL_PCT - t * 0.004), 1),
            "tensao_v": round(14.3 + 0.06 * math.sin(t * 0.7), 2),
            "barometrica_kpa": BAROMETRICA_KPA,
            "pressao_turbo_kpa": round(22 + self.carga * 1.15 + 6, 1),
            "avanco_graus": round(24 - self.carga * 0.1 + 2 * math.sin(t), 1),
            "borboleta_pct": round(min(100.0, 4 + self.pedal * 0.92), 1),
            "pedal_pct": round(self.pedal, 1),
            "carga_calculada_pct": round(min(100.0, self.carga * 0.62), 1),
            "temp_catalisador_c": round(self.catalisador),
            "luz_injecao": False,
            "codigos_falha": 0,
            "ajuste_curto_pct": round(2.5 * math.sin(t * 1.3), 1),
            "ajuste_longo_pct": -4.7,
            "lambda_sonda": round(self._lambda_comandado() + 0.02 * math.sin(t * 5.3), 3),
            "tempo_motor_s": int(t),
            "km_desde_limpeza": KM_DESDE_LIMPEZA,
            "etanol_pct": ETANOL_PCT,
        }
