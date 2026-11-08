"""Suma y resta sobre capturas sincronizadas, antes de acumular resultados."""

from collections import deque
from dataclasses import dataclass, replace

import numpy as np

from acquisition.acquisition_processor import AcquisitionProcessor


@dataclass(frozen=True)
class MathConfig:
    operation: str = "add"
    source_a: int = 1
    source_b: int = 2


@dataclass(frozen=True)
class MathResult:
    time: np.ndarray
    values: np.ndarray
    unit: str = "u.a."


class MathProcessor:
    """Las entradas son muestras, nunca coordenadas ni divisiones de pantalla."""

    def __init__(self, config=None):
        self.config = MathConfig()
        if config is not None:
            self.configure(**vars(config))

    def configure(self, **changes):
        candidate = replace(self.config, **changes)
        if candidate.operation not in ("add", "subtract"):
            raise ValueError("Operación no disponible: usar add o subtract")
        for channel in (candidate.source_a, candidate.source_b):
            if isinstance(channel, (bool, np.bool_)) or not isinstance(channel, (int, np.integer)) or channel not in (1, 2):
                raise ValueError("Las fuentes deben ser CH1 o CH2")
        self.config = candidate

    @property
    def expression(self):
        sign = "+" if self.config.operation == "add" else "−"
        return f"CH{self.config.source_a} {sign} CH{self.config.source_b}"

    def evaluate(self, samples, sample_rate):
        data = np.asarray(samples, dtype=np.float32)
        rate = float(sample_rate)
        if data.ndim != 2 or data.shape[1] != 2 or not np.isfinite(data).all():
            raise ValueError("MATH requiere muestras finitas sincronizadas (N, 2)")
        if not np.isfinite(rate) or rate <= 0:
            raise ValueError("Frecuencia de muestreo inválida")
        a, b = data[:, self.config.source_a-1], data[:, self.config.source_b-1]
        with np.errstate(over="raise", invalid="raise"):
            try:
                values = a+b if self.config.operation == "add" else a-b
            except FloatingPointError as exc:
                raise ValueError("El resultado MATH excede el rango numérico") from exc
        return MathResult(np.arange(len(data), dtype=float)/rate, values.copy())


class MathTraceProcessor:
    """Historial propio, separado de CH1/CH2 y de las escalas del gráfico.

    Cada resultado matemático se calcula ANTES de Sampling/Average/Envelope.
    Se retienen los pares originales de las últimas N capturas para permitir
    cambiar la fórmula en STOP sin operar sobre límites de envolvente.
    """

    def __init__(self, acquisition_config=None):
        self.math = MathProcessor()
        self.acquisition = AcquisitionProcessor(acquisition_config)
        self.reset()

    def reset(self):
        self.acquisition.reset()
        config = self.acquisition.get_config()
        size = {"average": config.average_count,
                "envelope": config.envelope_count}.get(config.mode, 1)
        self.history = deque(maxlen=size)
        self.sample_rate = None
        self.result = None

    def configure_acquisition(self, config):
        if config != self.acquisition.get_config():
            self.acquisition = AcquisitionProcessor(config)
            self.reset()

    def process(self, samples, sample_rate):
        evaluated = self.math.evaluate(samples, sample_rate)
        if not len(evaluated.values):
            return self.result
        if (self.history and (self.history[-1].shape != np.shape(samples)
                             or self.sample_rate != float(sample_rate))):
            self.reset()
        self.sample_rate = float(sample_rate)
        self.history.append(np.asarray(samples, dtype=np.float32).copy())
        self.result = self.acquisition.process(evaluated.values, channel=1)
        return self.result

    def configure_math(self, **changes):
        self.math.configure(**changes)
        self.acquisition.reset()
        self.result = None
        # Reprocesar pares retenidos conserva correlación y signo de la resta.
        for capture in self.history:
            values = self.math.evaluate(capture, self.sample_rate).values
            self.result = self.acquisition.process(values, channel=1)
        return self.result

    def replace_sampling_capture(self, samples, sample_rate):
        """Un recorte de Sampling reemplaza el único registro, no acumula."""
        if self.acquisition.get_mode() not in ("sampling", "high_resolution"):
            raise ValueError("El recorte directo solo se usa en Sampling o Hi-Res")
        self.reset()
        return self.process(samples, sample_rate)
