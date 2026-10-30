"""Coordina transporte, comandos y decodificador de la Blackpill.

DeviceSession no crea hilos: el lector llama a poll() repetidamente.
Usar desde el hilo de comunicación, no desde el hilo de la interfaz.
Las operaciones se serializan para no modificar el parser mientras lee.
El transporte debe tener timeout de lectura finito.

stream_on y stream_channel indican lo SOLICITADO, no una confirmación
del firmware. Las tramas recibidas conservan su propia identidad de canal.
"""
from __future__ import annotations

import threading

from . import commands
from .commands import Command
from .errors import CommunicationError
from .framing import FrameParser


class DeviceSession:
    def __init__(self, transport, parser=None):
        self.transport = transport
        self.parser = parser if parser is not None else FrameParser()
        self.stream_on = False
        self.stream_channel = None  # 'L', 'R', 'LR' o None si no se solicita stream
        self._lock = threading.RLock()

    @property
    def is_open(self):
        return self.transport.is_open

    def _require_open(self):
        if not self.transport.is_open:
            raise CommunicationError("La sesión está cerrada. Llamá primero a open().")

    def open(self):
        """Abre el transporte y comienza una sesión local nueva.

        No inicia el stream ni asegura que la placa estuviera detenida.
        Si ya está abierto, no modifica el estado ni los bytes pendientes.
        """
        with self._lock:
            if self.transport.is_open:
                return
            self.transport.open()
            self.parser.reset(clear_stats=True)
            self.stream_on = False
            self.stream_channel = None

    def close(self, stop_stream=True):
        """Intenta detener el stream solicitado y cierra incluso si falla el envío.

        stop_stream=False solo cierra el transporte: no ordena parar la placa.
        Las estadísticas del parser se conservan hasta la próxima apertura.
        """
        with self._lock:
            try:
                if self.transport.is_open and stop_stream and self.stream_on:
                    try:
                        self.send(commands.stream(False))
                    except CommunicationError:
                        # Por ejemplo, cable desconectado: igualmente cerrar.
                        pass
            finally:
                try:
                    self.transport.close()
                finally:
                    self.stream_on = False
                    self.stream_channel = None
                    self.parser.reset()

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()

    def send(self, command):
        """Envía Command o texto y devuelve el Command enviado.

        Actualiza el estado solicitado solo si write() termina sin error.
        No espera ACK: STREAM no tiene confirmación en este firmware.
        No descarta bytes ni borra la secuencia: el firmware mantiene un
        contador global para audio y texto, incluso al cambiar de canal.
        """
        cmd = command if isinstance(command, Command) else commands.raw(command)
        with self._lock:
            self._require_open()
            self.transport.write(cmd.wire)
            state = commands.stream_state(cmd.text)
            if state is not None:
                self.stream_on = state
                self.stream_channel = {
                    "STREAM:L": "L", "STREAM:R": "R", "STREAM:1": "LR",
                }.get(cmd.text)
        return cmd

    def start_stream(self, channel="LR"):
        """Solicita L (CH1), R (CH2) o LR (ambos).

        Sin argumentos mantiene estéreo, como la versión original.
        Descarta la entrada local pendiente y reinicia el parser conservando
        estadísticas. El canal se valida ANTES de descartar datos.

        Pueden llegar tramas anteriores aún en tránsito en el firmware/USB.
        El lector debe usar frame.channels para identificar lo recibido;
        este método no garantiza un corte temporal exacto ni espera audio.
        """
        cmd = commands.stream(True, channel)
        with self._lock:
            self._require_open()
            self.transport.reset_input()
            self.parser.reset()
            return self.send(cmd)

    def stop_stream(self):
        """Envía STREAM:0 y mantiene el puerto abierto.

        poll() puede seguir recibiendo texto o audio que estaba en tránsito.
        """
        return self.send(commands.stream(False))

    def poll(self):
        """Lee bytes y devuelve una lista de AudioFrame/TextFrame completos.

        Puede devolver [] por timeout o por una trama todavía incompleta.
        No descarta texto ni filtra canales; eso corresponde al lector.
        """
        with self._lock:
            self._require_open()
            data = self.transport.read()
            return self.parser.feed(data) if data else []
