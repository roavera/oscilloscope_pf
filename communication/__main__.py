
"""
Herramienta de consola para la comunicación con Blackpill.

Proyecto: oscilloscope_pf
Módulo: communication/__main__.py

Permite:
    - Listar puertos USB COM.
    - Verificar comunicación mediante PING/PONG.
    - Monitorear CH1 (L), CH2 (R) o ambos (LR).
    - Medir frecuencia, pico y RMS.
    - Detectar pérdidas de tramas.
    - Enviar comandos al firmware.
    - Probar todo mediante la Blackpill simulada.

Ejemplos:

    python -m communication ports

    python -m communication ping --simulated

    python -m communication monitor --simulated --channel L

    python -m communication monitor --simulated --channel R

    python -m communication monitor --simulated --channel LR

    python -m communication monitor --port COM5 --channel L

    python -m communication send --simulated LFREQ:1000 LAMP:50

    python -m communication commands
"""

from __future__ import annotations

import argparse
import sys
import time

import numpy as np

from . import commands
from .errors import CommandError, CommunicationError
from .framing import AudioFrame, TextFrame
from .protocol import FIRMWARE_FS
from .session import DeviceSession
from .simulator import SimulatedTransport
from .transport import (
    DEFAULT_USB_IDS,
    SerialTransport,
    describe_ports,
    find_blackpill_port,
    list_serial_ports,
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

DEFAULT_CHANNEL = "L"
DEFAULT_FS = FIRMWARE_FS
DEFAULT_SECONDS = 5.0

TONE_WINDOW = 16384


# ============================================================
# TRANSPORTE
# ============================================================

def _transport(args):
    """
    Selecciona el transporte de comunicación.

    simulated=True:
        Utiliza la Blackpill simulada.

    simulated=False:
        Utiliza el puerto USB COM real.
    """

    if args.simulated:
        return SimulatedTransport()

    port = find_blackpill_port(
        DEFAULT_USB_IDS,
        args.port,
    )

    return SerialTransport(port)


# ============================================================
# MEDICIONES
# ============================================================

def _dbfs(value):
    """Convierte amplitud normalizada a dBFS."""

    return 20.0 * np.log10(
        max(float(value), 1e-12)
    )


def _measure_signal(samples, fs):
    """
    Calcula pico, RMS y frecuencia dominante.

    samples:
        Array NumPy de un canal.

    fs:
        Frecuencia de muestreo nominal.

    Retorna:
        peak_dbfs, rms_dbfs, frequency
    """

    if len(samples) == 0:
        return None, None, None

    x = np.asarray(
        samples,
        dtype=np.float64,
    )

    peak = np.max(np.abs(x))
    rms = np.sqrt(np.mean(x ** 2))

    peak_dbfs = _dbfs(peak)
    rms_dbfs = _dbfs(rms)

    frequency = _tone(x, fs)

    return peak_dbfs, rms_dbfs, frequency


def _tone(samples, fs):
    """
    Estima la frecuencia dominante mediante FFT.

    Aplica ventana de Hann e interpolación parabólica.
    Es una estimación orientativa.
    """

    n = len(samples)

    if n < 1024:
        return None

    x = np.asarray(samples, dtype=np.float64)

    # Eliminar componente continua
    x = x - np.mean(x)

    window = np.hanning(n)

    spectrum = np.abs(
        np.fft.rfft(x * window)
    )

    if len(spectrum) < 4:
        return None

    # Excluir DC y Nyquist
    useful = spectrum[1:-1]

    if not np.any(useful > 0):
        return None

    k = int(np.argmax(useful)) + 1

    # Interpolación parabólica logarítmica
    a = np.log(spectrum[k - 1] + 1e-30)
    b = np.log(spectrum[k] + 1e-30)
    c = np.log(spectrum[k + 1] + 1e-30)

    denominator = a - 2.0 * b + c

    delta = 0.0

    if denominator != 0:
        delta = 0.5 * (a - c) / denominator
        delta = float(np.clip(delta, -0.5, 0.5))

    frequency = (k + delta) * fs / n

    return frequency


# ============================================================
# LISTAR PUERTOS
# ============================================================

def cmd_ports(args):
    """Lista los puertos serie disponibles."""

    ports = list_serial_ports(DEFAULT_USB_IDS)

    print("\nPUERTOS SERIE DISPONIBLES")
    print("-" * 50)

    if not ports:
        print(describe_ports(ports))
        return 1

    for port in ports:

        print(port)

        if port.likely:
            print("  Posible Blackpill detectada")

    return 0


# ============================================================
# PING / PONG
# ============================================================

def cmd_ping(args):
    """Verifica que el dispositivo responda PONG."""

    print("\nPRUEBA DE COMUNICACIÓN")
    print("-" * 50)

    with DeviceSession(_transport(args)) as session:

        print(f"Transporte: {session.transport.description}")

        start = time.perf_counter()

        session.send(commands.ping())

        while time.perf_counter() - start < args.timeout:

            frames = session.poll()

            for frame in frames:

                if isinstance(frame, TextFrame):

                    if frame.text == "PONG":

                        elapsed = (
                            time.perf_counter() - start
                        ) * 1000.0

                        print("Respuesta: PONG")
                        print(f"Tiempo: {elapsed:.2f} ms")
                        print("Comunicación correcta")

                        return 0

    print("No se recibió PONG.")
    return 1


# ============================================================
# MONITOREO DE AUDIO
# ============================================================

def cmd_monitor(args):
    """
    Recibe y analiza las tramas de audio.

    Modos:
        L  -> CH1
        R  -> CH2
        LR -> ambos canales
    """

    channel = args.channel.upper()

    fs = (
        DEFAULT_FS
        if args.fs is None
        else args.fs
    )

    if not np.isfinite(fs) or fs <= 0:
        raise ValueError("Fs debe ser positiva y finita.")

    if not np.isfinite(args.seconds) or args.seconds <= 0:
        raise ValueError("La duración debe ser positiva.")

    selected_channels = (
        ("L", "R")
        if channel == "LR"
        else (channel,)
    )

    # Historial independiente para cada canal
    buffers = {
        ch: np.empty(0, dtype=np.float32)
        for ch in selected_channels
    }

    total_frames = 0
    total_samples = 0
    got_audio = False

    print("\nMONITOR DE ADQUISICIÓN BLACKPILL")
    print("=" * 60)
    print(f"Canal seleccionado: {channel}")
    print(f"Frecuencia nominal: {fs:.2f} Hz")
    print(f"Duración: {args.seconds:.1f} s")
    print("=" * 60)

    with DeviceSession(_transport(args)) as session:

        print(f"Transporte: {session.transport.description}")

        # Iniciar transmisión del canal solicitado
        session.start_stream(channel)

        start = time.perf_counter()
        last_report = start

        while True:

            now = time.perf_counter()

            if now - start >= args.seconds:
                break

            frames = session.poll()

            for frame in frames:

                # ----------------------------------------
                # TRAMA DE TEXTO
                # ----------------------------------------

                if isinstance(frame, TextFrame):

                    print(f"Texto recibido: {frame.text}")
                    continue

                # ----------------------------------------
                # TRAMA DE AUDIO
                # ----------------------------------------

                if not isinstance(frame, AudioFrame):
                    continue

                # Verificar identidad de canales
                if not all(
                    ch in frame.channels
                    for ch in selected_channels
                ):
                    continue

                got_audio = True

                total_frames += 1
                total_samples += len(frame.samples)

                for ch in selected_channels:

                    col = frame.channels.index(ch)

                    samples = frame.samples[:, col]

                    buffers[ch] = np.concatenate(
                        (
                            buffers[ch],
                            samples,
                        )
                    )[-TONE_WINDOW:]

            # --------------------------------------------
            # REPORTE PERIÓDICO
            # --------------------------------------------

            if now - last_report >= 1.0:

                last_report = now

                elapsed = now - start

                stats = session.parser.stats

                print(
                    f"\nTiempo: {elapsed:.1f} s | "
                    f"Tramas: {total_frames} | "
                    f"Muestras/canal: {total_samples} | "
                    f"Pérdidas: {stats.lost_frames}"
                )

                for ch in selected_channels:

                    data = buffers[ch]

                    if len(data) == 0:

                        print(
                            f"  CH {ch}: esperando muestras..."
                        )
                        continue

                    peak, rms, freq = _measure_signal(
                        data,
                        fs,
                    )

                    freq_text = (
                        f"{freq:.2f} Hz"
                        if freq is not None
                        else "---"
                    )

                    print(
                        f"  CH {ch}: "
                        f"Pico={peak:.2f} dBFS | "
                        f"RMS={rms:.2f} dBFS | "
                        f"Frecuencia={freq_text}"
                    )

        elapsed = time.perf_counter() - start

        # Copiar estadísticas antes de cerrar
        stats = session.parser.stats

        bytes_in = stats.bytes_in
        audio_frames = stats.audio_frames
        audio_samples = stats.audio_samples
        lost_frames = stats.lost_frames
        loss_events = stats.loss_events
        junk_bytes = stats.junk_bytes
        resyncs = stats.resyncs

        session.stop_stream()

    # ====================================================
    # RESUMEN FINAL
    # ====================================================

    print("\nRESUMEN DE ADQUISICIÓN")
    print("=" * 60)

    print(f"Tiempo: {elapsed:.2f} s")
    print(f"Canales: {channel}")
    print(f"Tramas recibidas: {audio_frames}")
    print(f"Muestras por canal: {audio_samples}")
    print(f"Tramas perdidas: {lost_frames}")
    print(f"Eventos de pérdida: {loss_events}")
    print(f"Bytes recibidos: {bytes_in}")
    print(f"Bytes descartados: {junk_bytes}")
    print(f"Resincronizaciones: {resyncs}")

    if not got_audio:

        print("\nNo se recibieron muestras de audio.")
        return 1

    measured_fs = audio_samples / elapsed

    print(
        f"Fs efectiva aproximada: "
        f"{measured_fs:.2f} muestras/s"
    )

    difference = abs(
        measured_fs - fs
    ) / fs

    if difference > 0.03:

        print(
            "\nAviso: la tasa media recibida difiere "
            "más del 3 % de la frecuencia nominal."
        )
        print(
            "Puede deberse al inicio de la captura, "
            "pérdidas de tramas o problemas de comunicación."
        )

    return 0


# ============================================================
# ENVIAR COMANDOS
# ============================================================

def cmd_send(args):
    """Envía comandos ASCII al dispositivo."""

    command_list = [
        commands.raw(text)
        for text in args.commands
    ]

    print("\nENVÍO DE COMANDOS")
    print("-" * 50)

    with DeviceSession(_transport(args)) as session:

        for command in command_list:

            session.send(command)

            print(f"Enviado: {command.text}")

        end = time.perf_counter() + args.listen

        while time.perf_counter() < end:

            frames = session.poll()

            for frame in frames:

                if isinstance(frame, TextFrame):

                    print(
                        f"Respuesta: {frame.text}"
                    )

    return 0


# ============================================================
# CATÁLOGO DE COMANDOS
# ============================================================

def cmd_commands(args):
    """Muestra los comandos disponibles."""

    print("\nCOMANDOS BLACKPILL")
    print("=" * 70)

    for syntax, function, description, source in (
        commands.COMMAND_TABLE
    ):

        print(f"\nComando: {syntax}")
        print(f"Función: {function}")
        print(f"Descripción: {description}")
        print(f"Origen: {source}")

    return 0


# ============================================================
# ARGUMENTOS DE CONSOLA
# ============================================================

def build_parser():

    parser = argparse.ArgumentParser(
        prog="python -m communication",
        description=(
            "Herramienta de comunicación "
            "para la Blackpill del osciloscopio."
        ),
    )

    common = argparse.ArgumentParser(
        add_help=False
    )

    common.add_argument(
        "--port",
        default=None,
        help="Puerto USB COM, por ejemplo COM5.",
    )

    common.add_argument(
        "--simulated",
        action="store_true",
        help="Utilizar Blackpill simulada.",
    )

    sub = parser.add_subparsers(
        dest="cmd",
        required=True,
    )

    # ----------------------------------------
    # PORTS
    # ----------------------------------------

    p = sub.add_parser(
        "ports",
        help="Listar puertos serie.",
    )

    p.set_defaults(func=cmd_ports)

    # ----------------------------------------
    # PING
    # ----------------------------------------

    p = sub.add_parser(
        "ping",
        parents=[common],
        help="Verificar comunicación PING/PONG.",
    )

    p.add_argument(
        "--timeout",
        type=float,
        default=1.0,
    )

    p.set_defaults(func=cmd_ping)

    # ----------------------------------------
    # MONITOR
    # ----------------------------------------

    p = sub.add_parser(
        "monitor",
        parents=[common],
        help="Monitorear adquisición de audio.",
    )

    p.add_argument(
        "--seconds",
        type=float,
        default=DEFAULT_SECONDS,
    )

    p.add_argument(
        "--channel",
        type=str.upper,
        choices=("L", "R", "LR"),
        default=DEFAULT_CHANNEL,
        help="L=CH1, R=CH2, LR=ambos.",
    )

    p.add_argument(
        "--fs",
        type=float,
        default=None,
        help=(
            f"Frecuencia nominal de muestreo "
            f"(default {DEFAULT_FS:.2f} Hz)."
        ),
    )

    p.set_defaults(func=cmd_monitor)

    # ----------------------------------------
    # SEND
    # ----------------------------------------

    p = sub.add_parser(
        "send",
        parents=[common],
        help="Enviar comandos al firmware.",
    )

    p.add_argument(
        "commands",
        nargs="+",
        help="Comandos ASCII.",
    )

    p.add_argument(
        "--listen",
        type=float,
        default=0.3,
    )

    p.set_defaults(func=cmd_send)

    # ----------------------------------------
    # COMMANDS
    # ----------------------------------------

    p = sub.add_parser(
        "commands",
        help="Mostrar catálogo de comandos.",
    )

    p.set_defaults(func=cmd_commands)

    return parser


# ============================================================
# MAIN
# ============================================================

def main(argv=None):

    try:
        sys.stdout.reconfigure(
            errors="replace"
        )
    except Exception:
        pass

    parser = build_parser()
    args = parser.parse_args(argv)

    try:

        return args.func(args)

    except CommandError as exc:

        print(f"Comando inválido: {exc}")
        return 2

    except CommunicationError as exc:

        print(f"Error de comunicación: {exc}")
        return 1

    except ValueError as exc:

        print(f"Error de parámetros: {exc}")
        return 2

    except KeyboardInterrupt:

        print("\nOperación interrumpida.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
