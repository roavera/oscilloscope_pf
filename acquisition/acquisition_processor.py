
"""
===============================================================================
PROCESADOR DE ADQUISICIÓN
===============================================================================
Proyecto: Osciloscopio de Audio en Python

Responsabilidades:
    - Seleccionar el modo de adquisición.
    - Validar y administrar la configuración.
    - Coordinar el procesamiento por canal.
    - Reiniciar los estados cuando cambia la configuración.
    - Permitir incorporar los algoritmos de adquisición por separado.

Modos:
    sampling
    peak_detect
    average
    envelope
    fastact
    high_resolution
    roll

NOTA:
    Sampling, Peak Detect, Average y Envelope están implementados.
    Los demás modos se incorporarán progresivamente.
    FastAct y Roll requieren integración con la actualización de pantalla.
===============================================================================
"""

from copy import deepcopy
from dataclasses import dataclass, replace

import numpy as np

from acquisition.modes.sampling import process_sampling
from acquisition.modes.peak_detect import process_peak_detect
from acquisition.modes.average import process_average
from acquisition.modes.envelope import process_envelope, EnvelopeResult

@dataclass
class AcquisitionConfig:
    """Configuración de los modos de adquisición."""

    mode: str = "sampling"

    # Cantidad de adquisiciones para Average.
    average_count: int = 16

    # Cantidad de adquisiciones para Envelope.
    envelope_count: int = 16

    # Cantidad de muestras por intervalo en Peak Detect.
    peak_bucket_size: int = 4

    # Factor de combinación para Hi-Res.
    high_resolution_factor: int = 4


class AcquisitionProcessor:
    """Coordinador de los modos de adquisición."""

    SAMPLING = "sampling"
    PEAK_DETECT = "peak_detect"
    AVERAGE = "average"
    ENVELOPE = "envelope"
    FASTACT = "fastact"
    HIGH_RESOLUTION = "high_resolution"
    ROLL = "roll"

    MODES = (
        SAMPLING,
        PEAK_DETECT,
        AVERAGE,
        ENVELOPE,
        FASTACT,
        HIGH_RESOLUTION,
        ROLL,
    )

    AVERAGE_OPTIONS = (4, 16, 32, 64, 128, 256)
    ENVELOPE_OPTIONS = AVERAGE_OPTIONS

    DISPLAY_MODES = (FASTACT, ROLL)

    def __init__(self, config=None):
        self.config = (
            replace(config)
            if config is not None
            else AcquisitionConfig()
        )

        self._validate_config(self.config)

        # Estado independiente para CH1 y CH2.
        self._states = {}

        # Algoritmos registrados.
        self._processors = {
            self.SAMPLING: process_sampling,
            self.PEAK_DETECT: process_peak_detect,
            self.AVERAGE: process_average,
            self.ENVELOPE: process_envelope,
        }
    # ============================================================
    # VALIDACIÓN
    # ============================================================

    @staticmethod
    def _positive_integer(value):
        return (
            isinstance(value, (int, np.integer))
            and not isinstance(value, (bool, np.bool_))
            and value > 0
        )

    def _validate_config(self, config):

        if config.mode not in self.MODES:
            raise ValueError(
                f"Modo de adquisición no válido: {config.mode}"
            )

        if (
            not self._positive_integer(config.average_count)
            or config.average_count not in self.AVERAGE_OPTIONS
        ):
            raise ValueError(
                "average_count debe ser uno de: "
                "4, 16, 32, 64, 128 o 256"
            )

        if (not self._positive_integer(config.envelope_count)
                or config.envelope_count not in self.ENVELOPE_OPTIONS):
            raise ValueError("envelope_count debe ser 4, 16, 32, 64, 128 o 256")

        if config.peak_bucket_size not in (2, 4, 8, 16):
            raise ValueError("peak_bucket_size debe ser 2, 4, 8 o 16")

        for name in (
            "peak_bucket_size",
            "high_resolution_factor",
        ):
            value = getattr(config, name)

            if not self._positive_integer(value):
                raise ValueError(
                    f"{name} debe ser un entero positivo"
                )

    # ============================================================
    # CONFIGURACIÓN
    # ============================================================

    def set_mode(self, mode):
        """Selecciona el modo de adquisición."""

        self.configure(mode=mode)

    def set_average_count(self, count):
        """
        Configura la cantidad de adquisiciones
        utilizadas por el modo Average.

        Valores permitidos:
            4, 16, 32, 64, 128, 256
        """

        self.configure(average_count=count)

    def set_envelope_count(self, count):
        self.configure(envelope_count=count)

    def get_envelope_count(self):
        return self.config.envelope_count

    def configure(self, **kwargs):
        """
        Actualiza la configuración de manera segura.

        Si cambia algún parámetro, reinicia los
        estados acumulados de los canales.
        """

        valid_fields = set(
            AcquisitionConfig.__dataclass_fields__
        )

        for key in kwargs:
            if key not in valid_fields:
                raise ValueError(
                    f"Parámetro desconocido: {key}"
                )

        new_config = replace(self.config, **kwargs)

        self._validate_config(new_config)

        if new_config != self.config:
            self.config = new_config
            self.reset()

    def get_mode(self):
        """Devuelve el modo seleccionado."""

        return self.config.mode

    def get_average_count(self):
        """Devuelve la cantidad de promedios configurada."""

        return self.config.average_count

    # ============================================================
    # REGISTRO DE ALGORITMOS
    # ============================================================

    def register_processor(self, mode, processor):
        """
        Registra el algoritmo correspondiente a un modo.

        El algoritmo debe aceptar:
            processor(samples, channel, config, state)

        Sampling, Peak Detect, Average y Envelope ya vienen registrados.

        Los demás se registrarán al implementar
        los archivos de acquisition/modes/.
        """

        if mode not in self.MODES:
            raise ValueError(
                f"Modo desconocido: {mode}"
            )

        if mode in self.DISPLAY_MODES:
            raise ValueError(
                f"{mode} se implementará mediante "
                "la estrategia de visualización"
            )

        if not callable(processor):
            raise TypeError(
                "El procesador debe ser una función callable"
            )

        self._processors[mode] = processor

        self.reset()

    # ============================================================
    # ESTADOS POR CANAL
    # ============================================================

    def reset(self, channel=None):
        """
        Reinicia los estados acumulados.

        channel=None:
            Reinicia CH1 y CH2.

        channel=1:
            Reinicia solamente CH1.

        channel=2:
            Reinicia solamente CH2.
        """

        if channel is None:
            self._states.clear()
            return

        self._validate_channel(channel)

        self._states.pop(channel, None)

    @staticmethod
    def _validate_channel(channel):

        if channel not in (1, 2):
            raise ValueError(
                "El canal debe ser 1 o 2"
            )

    def _get_state(self, channel):

        if channel not in self._states:
            self._states[channel] = {}

        return self._states[channel]

    # ============================================================
    # PROCESAMIENTO
    # ============================================================

    def process(self, samples, channel=1):
        """
        Procesa una adquisición completa.

        Parameters
        ----------
        samples:
            Vector NumPy 1D de una captura.

        channel:
            1 para CH1.
            2 para CH2.

        Returns
        -------
        Resultado del algoritmo seleccionado.

        IMPORTANTE:
            Average y Envelope necesitarán capturas
            completas, alineadas temporalmente.
            No se deben pasar fragmentos USB arbitrarios.
        """

        self._validate_channel(channel)

        data = np.asarray(
            samples,
            dtype=np.float32,
        )

        if data.ndim != 1:
            raise ValueError(
                "Las muestras deben formar un vector 1D"
            )

        if data.size == 0 and self.config.mode != self.PEAK_DETECT:
            if self.config.mode == self.ENVELOPE:
                return EnvelopeResult(data.copy(), data.copy())
            return data.copy()

        mode = self.config.mode

        if mode in self.DISPLAY_MODES:
            raise NotImplementedError(
                f"El modo {mode} requiere integración "
                "con el sistema de visualización"
            )

        processor = self._processors.get(mode)

        if processor is None:
            raise NotImplementedError(
                f"El algoritmo del modo {mode} "
                "todavía no está implementado"
            )

        state = self._get_state(channel)

        return processor(
            data,
            channel,
            self.config,
            state,
        )

    # ============================================================
    # INFORMACIÓN
    # ============================================================

    def get_config(self):
        """Devuelve una copia de la configuración."""

        return replace(self.config)

    def get_state(self, channel=1):
        """
        Devuelve una copia independiente del estado del canal.

        Pensado para diagnóstico. No modifica
        el estado interno del procesador.
        """

        self._validate_channel(channel)

        state = self._states.get(channel, {})

        return deepcopy(state)

    def get_progress(self, channel=1):
        """Capturas acumuladas y objetivo; no copia los vectores del promedio."""
        self._validate_channel(channel)
        state = self._states.get(channel, {})
        target = {self.AVERAGE: self.config.average_count,
                  self.ENVELOPE: self.config.envelope_count}.get(self.config.mode, 1)
        return int(state.get("count", 0)), target

