"""Metadatos de la captura mostrada, independientes del próximo modo elegido."""
from dataclasses import dataclass


@dataclass(frozen=True)
class CaptureView:
    mode: str
    sample_rate: float
    trigger_sample: float | None
