"""Consumo estimado pela massa de ar, já que o carro não informa MAF (10) nem consumo (5E, 9D, A2)."""
import math

# A carga absoluta (PID 43) é a massa de ar por admissão dividida por 1,184 g/L × cilindrada do cilindro (SAE J1979).
DENSIDADE_AR_REFERENCIA = 1.184  # g/L

# Gasolina pura (E0) e etanol hidratado (E100 de bomba); a mistura é interpolada pelo % de etanol.
AFR_GASOLINA, AFR_ETANOL = 14.7, 9.0
DENSIDADE_GASOLINA, DENSIDADE_ETANOL = 745.0, 809.0  # g/L

ETANOL_PADRAO_PCT = 30  # gasolina comum vendida no Brasil, até chegar a leitura do sensor de etanol
CILINDRADA_L = 0.999  # Polo 1.0 TSI
FATOR_CALIBRACAO = 1.0  # ajuste fino depois de comparar com o consumo de um tanque cheio
SUAVIZACAO_S = 4
VELOCIDADE_MINIMA_KMH = 5  # abaixo disso o km/l não faz sentido e o consumo sai em L/h


def _misturar(gasolina: float, etanol: float, etanol_pct: float) -> float:
    fracao = min(max(etanol_pct, 0), 100) / 100
    return gasolina * (1 - fracao) + etanol * fracao


def vazao_ar_gs(rpm: float, carga_absoluta_pct: float, cilindrada_l: float) -> float:
    admissoes_do_motor_por_segundo = rpm / 120  # 4 tempos: cada cilindro admite a cada 2 voltas
    return carga_absoluta_pct / 100 * DENSIDADE_AR_REFERENCIA * cilindrada_l * admissoes_do_motor_por_segundo


def litros_por_hora(rpm: float, carga_absoluta_pct: float, lambda_comandado: float, etanol_pct: float,
                    cilindrada_l: float, fator_calibracao: float = 1.0) -> float:
    ar = vazao_ar_gs(rpm, carga_absoluta_pct, cilindrada_l)
    afr = _misturar(AFR_GASOLINA, AFR_ETANOL, etanol_pct) * max(lambda_comandado, 0.5)
    combustivel_gs = ar / afr
    return combustivel_gs * 3600 / _misturar(DENSIDADE_GASOLINA, DENSIDADE_ETANOL, etanol_pct) * fator_calibracao


def _suavizar(anterior: float | None, atual: float, alfa: float) -> float:
    return atual if anterior is None else anterior + alfa * (atual - anterior)


class Consumo:
    """Consumo suavizado a partir do último valor de cada dado: km/l andando e L/h sempre."""

    def __init__(self):
        self._lh: float | None = None
        self._velocidade: float | None = None
        self._t: float | None = None

    def atualizar(self, estado: dict[str, object], t: float) -> dict[str, float | None] | None:
        """Um passo da média; None enquanto faltar rotação, carga ou velocidade."""
        if any(estado.get(nome) is None for nome in ("rpm", "carga_absoluta_pct", "velocidade_kmh")):
            return None
        rpm, velocidade = estado["rpm"], estado["velocidade_kmh"]
        lh = litros_por_hora(rpm, estado["carga_absoluta_pct"], estado.get("lambda_comandado") or 1.0,
                             estado.get("etanol_pct") or ETANOL_PADRAO_PCT, CILINDRADA_L, FATOR_CALIBRACAO)
        dt = 0.0 if self._t is None else max(t - self._t, 0.0)
        self._t = t
        alfa = 1 - math.exp(-dt / SUAVIZACAO_S)
        self._lh = _suavizar(self._lh, lh, alfa)
        self._velocidade = _suavizar(self._velocidade, velocidade, alfa)
        if rpm < 1:
            # motor desligado não gasta nada: zera as médias juntas em vez de deixá-las cair devagar
            self._lh, self._velocidade = 0.0, velocidade
        andando = velocidade > 0 and self._velocidade >= VELOCIDADE_MINIMA_KMH
        kml = self._velocidade / self._lh if andando and self._lh > 0 else None
        return {"consumo_lh": round(self._lh, 2), "consumo_kml": None if kml is None else round(kml, 1)}
