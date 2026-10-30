"""
Comandos PC -> placa. Cada comando es UNA línea de texto ASCII terminada en '\\n' (nunca '\\r\\n'):

    LFREQ:1000.0\\n      LAMP:50\\n      LON\\n      STREAM:1\\n      PING\\n

La placa los acumula en un buffer de 128 bytes y, cuando llega el '\\n', los interpreta con strcmp/strncmp
(distingue mayúsculas de minúsculas). Un comando que no conoce lo IGNORA en silencio: no hay mensaje de
error ni confirmación, así que "no pasó nada" puede ser un comando mal escrito.

Para AGREGAR un comando: escribí una función como las de abajo (valida los argumentos y devuelve un
`Command`) y sumá una fila a COMMAND_TABLE. Si cambia el estado de transmisión,
actualizá también stream_state() y el manejo de ese estado en la sesión.
Este módulo construye bytes; no abre el puerto ni espera respuestas.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum, IntEnum

from .errors import CommandError
from .protocol import COMMAND_TERMINATOR, MAX_COMMAND_LEN


class Channel(str, Enum):
    LEFT = "L"
    RIGHT = "R"


class Waveform(IntEnum):
    """Forma de onda del generador (el número es el que viaja en LWAVE:<n> / RWAVE:<n>)."""
    SINE = 0
    SQUARE = 1
    TRIANGLE = 2
    CHIRP = 3


class OutputMode(str, Enum):
    DIFFERENTIAL = "DIFF"
    SINGLE_ENDED = "SE"


# ======================================================================================
#  El comando en sí
# ======================================================================================
@dataclass(frozen=True)
class Command:
    text: str                      # la línea sin el '\n', por ejemplo "LFREQ:1000.0"
    reply: str | None = None       # texto con el que la placa contesta, si contesta (PING -> "PONG")

    def __post_init__(self):
        t = self.text
        if not t:
            raise CommandError("Comando vacío.")
        if "\n" in t or "\r" in t:
            raise CommandError("El comando no puede tener saltos de línea: el '\\n' lo agrega el protocolo al final.")
        try:
            t.encode("ascii")
        except UnicodeEncodeError:
            raise CommandError(f"El comando tiene caracteres que no son ASCII: {t!r}") from None
        if len(t) > MAX_COMMAND_LEN:
            raise CommandError(f"Comando demasiado largo ({len(t)} caracteres; el máximo es {MAX_COMMAND_LEN}).")

    @property
    def wire(self):
        """Los bytes que se escriben en el puerto."""
        return self.text.encode("ascii") + COMMAND_TERMINATOR

    def __str__(self):
        return self.text


# ======================================================================================
#  Validación y formato de argumentos
# ======================================================================================
def _channel(ch):
    try:
        return Channel(str(getattr(ch, "value", ch)).upper())
    except ValueError:
        raise CommandError(f"Canal inválido: {ch!r} (usar 'L' o 'R').") from None


def _number(x, name, minimum=None, maximum=None, exclusive_min=False):
    try:
        v = float(x)
    except (TypeError, ValueError):
        raise CommandError(f"{name} tiene que ser un número (llegó {x!r}).") from None
    if not math.isfinite(v):
        raise CommandError(f"{name} tiene que ser un número finito (llegó {x!r}).")
    if minimum is not None and (v <= minimum if exclusive_min else v < minimum):
        raise CommandError(f"{name} tiene que ser {'mayor que' if exclusive_min else 'al menos'} {minimum} (llegó {v}).")
    if maximum is not None and v > maximum:
        raise CommandError(f"{name} no puede pasar de {maximum} (llegó {v}).")
    return v


def _num(v):
    """Número como texto para la línea: sin notación científica y con al menos un decimal (1000 -> '1000.0')."""
    s = f"{v:.6f}".rstrip("0")
    if s.endswith("."):
        s += "0"
    if float(s) == 0.0 and v != 0.0:
        raise CommandError(f"El valor {v} es demasiado chico para el protocolo (se redondearía a cero).")
    return s


# ======================================================================================
#  Generador de señales (salida del PCM3060)
# ======================================================================================
def set_frequency(channel, hz):
    """LFREQ:<Hz> / RFREQ:<Hz>  -  frecuencia de la señal del canal (la placa usa atof)."""
    ch = _channel(channel)
    return Command(f"{ch.value}FREQ:{_num(_number(hz, 'La frecuencia', 0, exclusive_min=True))}")


def set_amplitude(channel, percent):
    """LAMP:<0-100> / RAMP:<0-100>  -  amplitud en % del fondo de escala (entero)."""
    ch = _channel(channel)
    p = _number(percent, "La amplitud", 0, 100)
    return Command(f"{ch.value}AMP:{int(round(p))}")


def output_on(channel):
    """LON / RON  -  enciende la salida del canal."""
    return Command(f"{_channel(channel).value}ON")


def output_off(channel):
    """LOFF / ROFF  -  apaga la salida del canal."""
    return Command(f"{_channel(channel).value}OFF")


def set_waveform(channel, waveform):
    """LWAVE:<0-3> / RWAVE:<0-3>  -  0 seno, 1 cuadrada, 2 triangular, 3 chirp."""
    ch = _channel(channel)
    try:
        w = Waveform(int(waveform))
    except (TypeError, ValueError):
        raise CommandError(f"Forma de onda inválida: {waveform!r} (0 a 3).") from None
    return Command(f"{ch.value}WAVE:{int(w)}")


def set_chirp(channel, f_start, f_stop, duration):
    """LCHIRP:<f0>,<f1>,<seg> / RCHIRP:...  -  parámetros del barrido de frecuencia (f0 -> f1 en <seg> segundos)."""
    ch = _channel(channel)
    f0 = _number(f_start, "La frecuencia inicial", 0, exclusive_min=True)
    f1 = _number(f_stop, "La frecuencia final", 0, exclusive_min=True)
    d = _number(duration, "La duración", 0, exclusive_min=True)
    return Command(f"{ch.value}CHIRP:{_num(f0)},{_num(f1)},{_num(d)}")


def set_output_mode(mode):
    """DIFF / SE  -  salida diferencial o simple."""
    try:
        m = OutputMode(str(getattr(mode, "value", mode)).upper())
    except ValueError:
        raise CommandError(f"Modo de salida inválido: {mode!r} ('DIFF' o 'SE').") from None
    return Command(m.value)


# ======================================================================================
#  Códec y envío de audio
# ======================================================================================
def codec_adc(on):
    """ADC:<0|1>  -  enciende o apaga el ADC del PCM3060."""
    return Command(f"ADC:{1 if on else 0}")


def codec_dac(on):
    """DAC:<0|1>  -  enciende o apaga el DAC del PCM3060."""
    return Command(f"DAC:{1 if on else 0}")


def stream(on, channel="LR"):
    """Prepara el comando de transmisión del ADC; no lo envía.

    stream(True)       -> STREAM:1 (estéreo, compatible con el uso anterior)
    stream(True, "L")  -> STREAM:L (CH1)
    stream(True, "R")  -> STREAM:R (CH2)
    stream(False)      -> STREAM:0 (detiene cualquier modo)

    channel acepta L, R o LR; también Channel.LEFT / Channel.RIGHT.
    on acepta bool o los enteros 0/1. No usar cadenas como "False".
    Detener la transmisión no apaga el ADC ni las salidas del generador.
    """
    if not isinstance(on, (bool, int)) or on not in (0, 1):
        raise CommandError("El estado de transmisión debe ser True/False o 1/0.")
    ch = str(getattr(channel, "value", channel)).strip().upper()
    if ch not in ("L", "R", "LR"):
        raise CommandError(f"Canal de transmisión inválido: {channel!r} (usar 'L', 'R' o 'LR').")
    if not on:
        return Command("STREAM:0")
    return Command({"L": "STREAM:L", "R": "STREAM:R", "LR": "STREAM:1"}[ch])


def alin():
    """Consulta la alineación del ADC: responde ALIN:corridos,directos.

    Los contadores los produce el firmware. No se modifica la alineación.
    reply queda en None porque el texto completo es variable; el receptor
    deberá reconocer la respuesta con text.startswith("ALIN:").
    """
    return Command("ALIN")


def ping():
    """PING  -  la placa contesta con una trama de texto «PONG» (sirve para probar el enlace)."""
    return Command("PING", reply="PONG")


def raw(text):
    """Un comando cualquiera, sin más control que el de línea (para probar comandos que todavía no tienen función)."""
    return Command(str(text).strip())


def stream_state(text):
    """Estado SOLICITADO por un comando; no confirma ejecución en la placa.

    Reconoce mono y estéreo. Acepta texto o un objeto Command.
    Devuelve None cuando no es un comando de transmisión conocido.
    """
    return {
        "STREAM:1": True,
        "STREAM:L": True,
        "STREAM:R": True,
        "STREAM:0": False,
    }.get(str(text).strip())


# (sintaxis, función, qué hace, de dónde sale). Es documentación: la usa la herramienta de consola.
COMMAND_TABLE = (
    ("LFREQ:<Hz>   RFREQ:<Hz>", "set_frequency", "frecuencia de la señal de cada canal", "comandos.py"),
    ("LAMP:<0-100>   RAMP:<0-100>", "set_amplitude", "amplitud de cada canal, en % del fondo de escala", "comandos.py"),
    ("LON   LOFF   RON   ROFF", "output_on / output_off", "enciende o apaga la salida de cada canal", "comandos.py"),
    ("LWAVE:<0-3>   RWAVE:<0-3>", "set_waveform", "forma de onda: 0 seno, 1 cuadrada, 2 triangular, 3 chirp", "comandos.py"),
    ("LCHIRP:<f0>,<f1>,<s>   RCHIRP:...", "set_chirp", "barrido de f0 a f1 en <s> segundos", "comandos.py"),
    ("DIFF   SE", "set_output_mode", "salida diferencial o simple", "comandos.py"),
    ("ADC:<0|1>   DAC:<0|1>", "codec_adc / codec_dac", "enciende o apaga el ADC / el DAC del PCM3060", "comandos.py"),
    ("STREAM:<0|1|L|R>", "stream", "detiene o inicia audio estéreo / mono L / mono R", "usbd_cdc_if.c"),
    ("ALIN", "alin", "consulta contadores de alineación del ADC", "stream.c + usbd_cdc_if.c"),
    ("PING", "ping", "la placa contesta con una trama de texto «PONG»", "comandos.py + viaje_de_datos.html"),
)
