"""
Herramienta de consola para probar la placa sin abrir la aplicación.

    python -m audio_analyzer.communications ports                       puertos serie del sistema (marca la Black Pill)
    python -m audio_analyzer.communications ping                        PING -> PONG y cuánto tardó
    python -m audio_analyzer.communications monitor --seconds 5         empieza el stream y muestra nivel, tono y pérdidas
    python -m audio_analyzer.communications send LFREQ:440.0 LAMP:30    manda comandos (y escucha las respuestas de texto)
    python -m audio_analyzer.communications commands                    catálogo de comandos

Opciones comunes:  --port COM5  (si no, la busca por VID:PID)   --simulated  (usa la placa simulada, sin hardware)
El puerto lo puede abrir un solo programa a la vez: cerrar el analizador antes de usar esta herramienta.
"""
from __future__ import annotations

import argparse
import sys
import time

import numpy as np

from audio_analyzer.config import defaults as cfg
from . import commands
from .errors import CommandError, CommunicationError
from .framing import AudioFrame, TextFrame
from .session import DeviceSession
from .simulator import SimulatedTransport
from .transport import SerialTransport, describe_ports, find_blackpill_port, list_serial_ports

TONE_WINDOW = 16384            # muestras que se usan para estimar el tono


def _transport(args):
    if args.simulated:
        return SimulatedTransport()
    return SerialTransport(find_blackpill_port(cfg.BLACKPILL_USB_IDS, args.port or cfg.BLACKPILL_PORT))


def _dbfs(x):
    return 20.0 * np.log10(max(float(x), 1e-12))


def _tone(x, fs):
    """Frecuencia del pico más alto [Hz] por FFT con ventana de Hann e interpolación parabólica (solo orientativa)."""
    n = len(x)
    if n < 1024:
        return None
    w = np.hanning(n)
    mag = np.abs(np.fft.rfft(x * w))
    k = int(np.argmax(mag[1:-1])) + 1
    a, b, c = np.log(mag[k - 1] + 1e-30), np.log(mag[k] + 1e-30), np.log(mag[k + 1] + 1e-30)
    den = a - 2.0 * b + c
    delta = 0.5 * (a - c) / den if den != 0 else 0.0
    return (k + delta) * fs / n


# ======================================================================================
#  Subcomandos
# ======================================================================================
def cmd_ports(args):
    ports = list_serial_ports(cfg.BLACKPILL_USB_IDS)
    if not ports:
        print(describe_ports(ports))
        return 1
    for p in ports:
        mark = "  <-- parece la Black Pill" if p.likely else ""
        print(f"  {p}{mark}")
    return 0


def cmd_ping(args):
    with DeviceSession(_transport(args)) as s:
        t0 = time.perf_counter()
        s.send(commands.ping())
        while time.perf_counter() - t0 < args.timeout:
            for fr in s.poll():
                if isinstance(fr, TextFrame) and fr.text == commands.ping().reply:
                    print(f"PONG en {(time.perf_counter() - t0) * 1000:.1f} ms  ({s.transport.description})")
                    return 0
    print(f"La placa no contestó el PING en {args.timeout:g} s.")
    return 1


def cmd_monitor(args):
    col = {"L": 0, "R": 1}[args.channel.upper()]
    fs = cfg.BLACKPILL_FS if args.fs is None else args.fs
    with DeviceSession(_transport(args)) as s:
        s.start_stream()
        print(f"Canal {args.channel.upper()}, fs nominal {fs:.2f} Hz, {args.seconds:g} s  ({s.transport.description})")
        t0 = last = time.perf_counter()
        keep = np.zeros(0, dtype=np.float32)
        frames = samples = 0
        got_audio = False
        while True:
            now = time.perf_counter()
            if now - t0 >= args.seconds:
                break
            for fr in s.poll():
                if isinstance(fr, AudioFrame):
                    got_audio = True
                    frames += 1
                    samples += len(fr.samples)
                    keep = np.concatenate((keep, fr.samples[:, col]))[-TONE_WINDOW:]
                elif isinstance(fr, TextFrame):
                    print(f"  texto de la placa: {fr.text!r}")
            if now - last >= 1.0:
                last = now
                st = s.parser.stats
                if len(keep):
                    peak, rms = _dbfs(np.max(np.abs(keep))), _dbfs(np.sqrt(np.mean(keep.astype(np.float64) ** 2)))
                    f0 = _tone(keep, fs)
                    tone = f"{f0:9.1f} Hz" if f0 else "     ---"
                    print(f"  t={now - t0:4.1f} s  tramas={frames:5d}  muestras={samples:8d}  perdidas={st.lost_frames:3d}  "
                          f"pico={peak:7.2f} dBFS  rms={rms:7.2f} dBFS  tono~{tone}")
                else:
                    print(f"  t={now - t0:4.1f} s  todavia no llego audio")
                frames = 0
        elapsed = time.perf_counter() - t0
        st = s.parser.stats
        s.stop_stream()
    print("\nResumen del enlace")
    print(f"  bytes recibidos ...... {st.bytes_in}  ({st.bytes_in / elapsed / 1000:.1f} kB/s)")
    print(f"  tramas de audio ...... {st.audio_frames}  ({st.audio_samples} muestras por canal, "
          f"{st.audio_samples / elapsed:.0f} muestras/s)")
    print(f"  tramas perdidas ...... {st.lost_frames}  en {st.loss_events} saltos de seq")
    print(f"  bytes descartados .... {st.junk_bytes}  ({st.resyncs} resincronizaciones, {st.false_syncs} falsos AA 55)")
    if not got_audio:
        print("\nNo llegó audio. Revisar el puerto con 'ping' y que el firmware esté corriendo.")
        return 1
    ratio = st.audio_samples / elapsed / fs
    if abs(ratio - 1.0) > 0.03:
        print(f"\nAviso: llegan {st.audio_samples / elapsed:.0f} muestras/s y la fs configurada es {fs:.2f} Hz. "
              f"Si no coinciden, el eje de frecuencias del espectro va a estar mal.")
    return 0


def cmd_send(args):
    cmds = [commands.raw(t) for t in args.commands]          # valida todo antes de abrir el puerto
    with DeviceSession(_transport(args)) as s:
        for c in cmds:
            s.send(c)
            print(f"enviado: {c.text}")
        end = time.perf_counter() + args.listen
        while time.perf_counter() < end:
            for fr in s.poll():
                if isinstance(fr, TextFrame):
                    print(f"  la placa contesta: {fr.text!r}")
    return 0


def cmd_commands(args):
    for syntax, func, what, source in commands.COMMAND_TABLE:
        print(f"  {syntax:<38} {func:<24} {what}   [{source}]")
    return 0


# ======================================================================================
def build_parser():
    ap = argparse.ArgumentParser(prog="python -m audio_analyzer.communications",
                                 description="Herramienta de consola para la Black Pill.")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--port", help="puerto serie (por ejemplo COM5). Si no se da, se busca por VID:PID")
    common.add_argument("--simulated", action="store_true", help="usar la placa simulada (sin hardware)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("ports", help="listar los puertos serie").set_defaults(func=cmd_ports)

    p = sub.add_parser("ping", parents=[common], help="PING -> PONG")
    p.add_argument("--timeout", type=float, default=1.0, help="segundos de espera (1)")
    p.set_defaults(func=cmd_ping)

    p = sub.add_parser("monitor", parents=[common], help="empezar el stream y mostrar nivel, tono y pérdidas")
    p.add_argument("--seconds", type=float, default=5.0, help="duración (5)")
    p.add_argument("--channel", choices=("L", "R", "l", "r"), default=cfg.BLACKPILL_CHANNEL, help="canal que se mide")
    p.add_argument("--fs", type=float, default=None, help=f"fs nominal [Hz] (por defecto la de config: {cfg.BLACKPILL_FS:.2f})")
    p.set_defaults(func=cmd_monitor)

    p = sub.add_parser("send", parents=[common], help="mandar comandos")
    p.add_argument("commands", nargs="+", help='líneas de comando, por ejemplo "LFREQ:440.0" "LAMP:30"')
    p.add_argument("--listen", type=float, default=0.3, help="segundos que se escuchan respuestas de texto (0,3)")
    p.set_defaults(func=cmd_send)

    sub.add_parser("commands", help="mostrar el catálogo de comandos").set_defaults(func=cmd_commands)
    return ap


def main(argv=None):
    try:
        sys.stdout.reconfigure(errors="replace")             # consolas que no pueden mostrar algún carácter
    except Exception:
        pass
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except CommandError as e:
        print(f"Comando inválido: {e}")
        return 2
    except CommunicationError as e:
        print(e)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
