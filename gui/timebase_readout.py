"""Texto de lectura temporal del osciloscopio; no depende de Qt."""

from math import isfinite


def _number(value):
    """Hasta seis cifras significativas, suficientes para el Vernier."""
    return f"{value:.6g}"


def format_time(seconds, *, signed=False):
    """Da formato a un tiempo en s, ms, µs o ns."""
    seconds = float(seconds)
    if not isfinite(seconds):
        raise ValueError("Tiempo no finito")
    magnitude = abs(seconds)
    if magnitude == 0:
        scale, unit = 1.0, "s"
    elif magnitude < 1e-6:
        scale, unit = 1e9, "ns"
    elif magnitude < 1e-3:
        scale, unit = 1e6, "µs"
    elif magnitude < 1.0:
        scale, unit = 1e3, "ms"
    else:
        scale, unit = 1.0, "s"
    amount = seconds * scale
    prefix = "+" if signed and amount >= 0 else ""
    return f"{prefix}{_number(amount)} {unit}"


def format_timebase_readout(base_seconds, zoom=1.0, delay_seconds=0.0, *, vernier=False):
    """Conserva por separado la base de adquisición y la escala visible."""
    base = float(base_seconds)
    zoom = float(zoom)
    delay = float(delay_seconds)
    if not all(isfinite(x) for x in (base, zoom, delay)) or base <= 0 or zoom < 1.0:
        raise ValueError("Base de tiempo / zoom / delay inválidos")
    fields = [f"TIME/DIV  {format_time(base)}/div"]
    if vernier:
        fields.append("FINO")
    if abs(zoom - 1.0) > 1e-9:
        fields.append(f"ZOOM ×{_number(zoom)}")
        fields.append(f"VISTA  {format_time(base / zoom)}/div")
    if abs(delay) > 1e-12:
        fields.append(f"DELAY  {format_time(delay, signed=True)}")
    return "   ·   ".join(fields)
