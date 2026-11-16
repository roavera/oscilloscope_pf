"""Operaciones matemáticas sobre capturas sincronizadas."""

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
        operations = {
            "add", "subtract", "multiply", "divide",
            "integrate", "derivative", "abs", "sqrt", "log10", "ln", "exp",
            "greater", "less", "greater_equal", "less_equal", "equal",
            "and", "or", "xor",
        }
        if candidate.operation not in operations:
            raise ValueError("Operación matemática no disponible")
        for channel in (candidate.source_a, candidate.source_b):
            if isinstance(channel, (bool, np.bool_)) or not isinstance(channel, (int, np.integer)) or channel not in (1, 2):
                raise ValueError("Las fuentes deben ser CH1 o CH2")
        self.config = candidate

    @property
    def expression(self):
        labels = {
            "add": "+", "subtract": "−", "multiply": "×", "divide": "÷",
            "greater": ">", "less": "<", "greater_equal": "≥",
            "less_equal": "≤", "equal": "=", "and": "AND",
            "or": "OR", "xor": "XOR",
        }
        op = self.config.operation
        if op in labels:
            return f"CH{self.config.source_a} {labels[op]} CH{self.config.source_b}"
        names = {"integrate": "∫", "derivative": "d/dt", "abs": "abs",
                 "sqrt": "√", "log10": "log10", "ln": "ln", "exp": "exp"}
        return f"{names[op]}(CH{self.config.source_a})"

    def evaluate(self, samples, sample_rate):
        data = np.asarray(samples, dtype=np.float32)
        rate = float(sample_rate)
        if data.ndim != 2 or data.shape[1] != 2 or not np.isfinite(data).all():
            raise ValueError("MATH requiere muestras finitas sincronizadas (N, 2)")
        if not np.isfinite(rate) or rate <= 0:
            raise ValueError("Frecuencia de muestreo inválida")
        a = data[:, self.config.source_a - 1].astype(np.float64)
        b = data[:, self.config.source_b - 1].astype(np.float64)
        op = self.config.operation
        with np.errstate(over="raise", invalid="raise"):
            try:
                if op == "add":
                    values = a + b
                elif op == "subtract":
                    values = a - b
                elif op == "multiply":
                    values = a * b
                elif op == "divide":
                    values = np.divide(a, b, out=np.zeros_like(a), where=np.abs(b) > np.finfo(float).eps)
                elif op == "integrate":
                    increments = (a[:-1] + a[1:]) * 0.5 / rate
                    values = np.concatenate(([0.0], np.cumsum(increments)))
                elif op == "derivative":
                    values = np.gradient(a, 1.0 / rate)
                elif op == "abs":
                    values = np.abs(a)
                elif op == "sqrt":
                    values = np.sqrt(np.maximum(a, 0.0))
                elif op == "log10":
                    values = np.log10(np.maximum(a, np.finfo(float).tiny))
                elif op == "ln":
                    values = np.log(np.maximum(a, np.finfo(float).tiny))
                elif op == "exp":
                    values = np.exp(np.clip(a, -700.0, 700.0))
                elif op == "greater":
                    values = (a > b).astype(float)
                elif op == "less":
                    values = (a < b).astype(float)
                elif op == "greater_equal":
                    values = (a >= b).astype(float)
                elif op == "less_equal":
                    values = (a <= b).astype(float)
                elif op == "equal":
                    values = np.isclose(a, b, rtol=1e-5, atol=1e-8).astype(float)
                elif op == "and":
                    values = ((a != 0) & (b != 0)).astype(float)
                elif op == "or":
                    values = ((a != 0) | (b != 0)).astype(float)
                elif op == "xor":
                    values = ((a != 0) ^ (b != 0)).astype(float)
                values = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
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
