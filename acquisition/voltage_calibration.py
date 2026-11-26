"""Perfiles de escala vertical del osciloscopio.

Las muestras de entrada son floats normalizados decodificados de PCM24, no V.
La señal de trabajo se expresa como V = G * raw + offset, por canal.
La Blackpill simulada representa un ADC virtual de +/-3 V; la Blackpill
física NO recibe una escala nominal inventada hasta realizar calibración.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import os
import tempfile

import numpy as np

SIMULATOR_FULL_SCALE_VOLTS = 3.0
CALIBRATION_PATH = Path(__file__).resolve().parents[1] / "config" / "calibration.json"

# Coinciden con las constantes de AcquisitionManager. Evitamos imports cíclicos.
SOURCE_AUDIO = "audio"
SOURCE_SIMULATOR = "simulator"
SOURCE_BLACKPILL = "blackpill_usb"


@dataclass(frozen=True)
class ChannelCalibration:
    gain_v_per_unit: float = 1.0
    offset_volts: float = 0.0

    def __post_init__(self):
        gain = float(self.gain_v_per_unit)
        offset = float(self.offset_volts)
        if not math.isfinite(gain) or gain == 0:
            raise ValueError("La ganancia debe ser finita y distinta de cero")
        if not math.isfinite(offset):
            raise ValueError("El offset debe ser finito")
        object.__setattr__(self, "gain_v_per_unit", gain)
        object.__setattr__(self, "offset_volts", offset)


class VoltageCalibration:
    """Escalas por fuente y canal. Solo las de la Blackpill física son editables.

    Sounddevice conserva su amplitud digital, sin asignar voltios físicos.
    La simulación usa exactamente el rango virtual del codificador PCM24.
    """

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else CALIBRATION_PATH
        self._physical = {1: ChannelCalibration(), 2: ChannelCalibration()}
        self._verified = {1: False, 2: False}
        self.audio_profiles = {}
        self._audio_key = None
        self._audio_channels = 1
        self.load()

    def load(self):
        if not self.path.is_file():
            return
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("version") != 1:
            raise ValueError("Formato de config/calibration.json inválido")
        physical = payload.get("blackpill_usb", {})
        configured = {}
        verified = {}
        for channel in (1, 2):
            item = physical.get(f"ch{channel}", {})
            configured[channel] = ChannelCalibration(
                item.get("gain_v_per_unit", 1.0), item.get("offset_volts", 0.0)
            )
            verified[channel] = bool(item.get("verified", False))
        self._physical, self._verified = configured, verified
        self.audio_profiles = payload.get('audio_profiles', {})
        if not isinstance(self.audio_profiles, dict):
            raise ValueError('Perfiles de audio inválidos')

    def select_audio_profile(self, key, channels):
        self._audio_key = key
        self._audio_channels = int(channels)

    def _audio_verified(self):
        profile = self.audio_profiles.get(self._audio_key, {})
        return all(bool(profile.get(f'ch{ch}', {}).get('verified', False))
                   for ch in range(1, self._audio_channels + 1))


    def profile(self, source: str, channel: int) -> ChannelCalibration:
        if channel not in (1, 2):
            raise ValueError("Canal inválido")
        if source == SOURCE_SIMULATOR:
            return ChannelCalibration(SIMULATOR_FULL_SCALE_VOLTS, 0.0)
        if source == SOURCE_BLACKPILL:
            return self._physical[channel]
        if source == SOURCE_AUDIO:
            if self._audio_verified() and channel <= self._audio_channels:
                item = self.audio_profiles[self._audio_key][f'ch{channel}']
                return ChannelCalibration(item['gain_v_per_unit'], item['offset_volts'])
            return ChannelCalibration()
        raise ValueError(f"Fuente de adquisición desconocida: {source}")

    def apply(self, samples, source: str) -> np.ndarray:
        """Devuelve una COPIA en unidades físicas (o digitales para audio)."""
        raw = np.asarray(samples, dtype=np.float32)
        if raw.ndim != 2 or raw.shape[1] != 2 or not np.isfinite(raw).all():
            raise ValueError("Calibración requiere un array finito (N, 2)")
        out = np.empty_like(raw)
        for index in (0, 1):
            profile = self.profile(source, index + 1)
            out[:, index] = (raw[:, index].astype(np.float64) *
                             profile.gain_v_per_unit + profile.offset_volts)
        return out

    def status(self, source: str) -> str:
        if source == SOURCE_SIMULATOR:
            return "Simulación ±3 V (escala virtual)"
        if source == SOURCE_BLACKPILL:
            if all(self._verified.values()):
                return "Blackpill CH1/CH2 calibrados"
            if any(self._verified.values()):
                label = ", ".join(
                    f"CH{ch} " + ("calibrado" if self._verified[ch] else "sin calibrar")
                    for ch in (1, 2)
                )
                return "Blackpill " + label
            return "Blackpill sin calibrar"
        if source == SOURCE_AUDIO:
            return "Audio calibrado" if self._audio_verified() else "Audio: unidades digitales"
        raise ValueError("Fuente desconocida")

    def has_volts(self, source: str) -> bool:
        return (source == SOURCE_AUDIO and self._audio_verified()) or source == SOURCE_SIMULATOR or (source == SOURCE_BLACKPILL and
                all(self._verified.values()))

    def set_physical(self, channel: int, gain_v_per_unit: float, offset_volts: float,
                     *, verified: bool = False, save: bool = True):
        if channel not in (1, 2):
            raise ValueError("Canal inválido")
        updated = ChannelCalibration(gain_v_per_unit, offset_volts)
        self._physical[channel] = updated
        self._verified[channel] = bool(verified)
        if save:
            self.save()

    def as_dict(self):
        return {"version": 1, "audio_profiles": self.audio_profiles, "blackpill_usb": {
            f"ch{ch}": {"gain_v_per_unit": self._physical[ch].gain_v_per_unit,
                        "offset_volts": self._physical[ch].offset_volts,
                        "verified": self._verified[ch]}
            for ch in (1, 2)}}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = None
        try:
            with tempfile.NamedTemporaryFile("w", dir=self.path.parent,
                                             encoding="utf-8", delete=False) as f:
                temp = f.name
                json.dump(self.as_dict(), f, indent=2, ensure_ascii=False)
                f.write("\n")
            os.replace(temp, self.path)
        finally:
            if temp is not None and os.path.exists(temp):
                os.unlink(temp)


def simulator_volts_to_normalized(settings: dict) -> dict:
    """Convierte SOLO los tres parámetros de interfaz expresados en V.

    El protocolo de comunicación y configure_simulator() siguen normalizados.
    Una señal por encima de +/-3 V se satura como en un ADC real.
    """
    converted = dict(settings)
    for name in ("amplitude", "offset", "noise"):
        if name in converted:
            value = float(converted[name])
            if not math.isfinite(value):
                raise ValueError(f"{name} debe ser finito")
            converted[name] = value / SIMULATOR_FULL_SCALE_VOLTS
    return converted
