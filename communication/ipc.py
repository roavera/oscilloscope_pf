"""
El canal de comandos entre la GUI y el proceso de captura.

El puerto serie lo tiene abierto el PROCESO DE CAPTURA (así el audio no se frena cuando la GUI redibuja). La GUI
no puede abrir el mismo puerto, entonces le pasa los comandos por una cola y recibe por otra los avisos:

    GUI (DeviceClient)  ──requests──►  proceso de captura (worker.py)  ──►  puerto serie  ──►  placa
                        ◄───events───                                  ◄──  tramas de texto, pérdidas, estadísticas

Las dos colas se crean nuevas en cada Run (si el proceso de captura se mata a la fuerza, una cola puede quedar
con el candado tomado) y NUNCA bloquean: si se llenan, el mensaje nuevo se descarta. Por eso conviene llamar a
poll() seguido; `AudioEngine.device` lo hace cada vez que se lo consulta.

Eventos captura -> GUI (tuplas simples):
    ("sent",  req_id, pos, t, texto)   el comando salió por el puerto cuando ya habían entrado `pos` muestras al buffer
    ("text",  texto, pos, t)           trama de texto de la placa (por ejemplo "PONG")
    ("loss",  pos, tramas, t)          faltaron `tramas` tramas de audio justo en la muestra `pos` (varios saltos
                                       seguidos se juntan en un solo aviso para no inundar la cola)
    ("stats", dict)                    contadores del enlace (LinkStats + fs medida), una vez por segundo
    ("error", req_id, mensaje)         un comando no se pudo mandar
    ("channel", canal, pos, t)         el lector pasó a entregar el canal "L" o "R" desde la muestra `pos`

Pedidos GUI -> captura: (req_id, texto) es un comando para la placa; ("channel", "L"|"R") es para el lector
(qué canal de la placa pasa al buffer) y no viaja por el puerto.
`pos` cuenta muestras mono desde el Run, igual que H_TOTAL del buffer compartido: sirve para ubicar en el audio
el instante en que se mandó un comando (con la demora del USB y del lazo principal del firmware, ver PROTOCOLO.md).
`t` es time.perf_counter() del proceso de captura (en Windows, Linux y macOS es el mismo reloj en todos los procesos).
"""
from __future__ import annotations

import queue
import time
from collections import OrderedDict, deque
from dataclasses import dataclass

from . import commands
from .commands import Command


class ControlChannel:
    """El par de colas. Lo crea la GUI (con el contexto 'spawn' del motor) y se le pasa al proceso de captura."""

    TAKE_LIMIT = 64                                      # pedidos que el proceso de captura atiende por vuelta

    def __init__(self, ctx, max_requests=256, max_events=1024):
        self._requests = ctx.Queue(max_requests)
        self._events = ctx.Queue(max_events)
        self._closed = False
        self.dropped_events = 0
        self._no_join()

    def _no_join(self):
        # Un proceso que puso datos en una cola espera, al terminar, a que se vacíen: si el otro lado ya no lee,
        # se colgaría al cerrar. Con esto no espera. (Hay que repetirlo en el proceso hijo: ver __setstate__.)
        self._requests.cancel_join_thread()
        self._events.cancel_join_thread()

    def __getstate__(self):                              # se llama al pasárselo al proceso de captura
        return {"_requests": self._requests, "_events": self._events, "_closed": False, "dropped_events": 0}

    def __setstate__(self, state):                       # ... y esto, ya en el proceso de captura
        self.__dict__.update(state)
        self._no_join()

    # --- lado GUI -----------------------------------------------------------------
    def put_request(self, request):
        if self._closed:
            return False
        try:
            self._requests.put_nowait(request)
            return True
        except (queue.Full, ValueError, OSError):        # llena, o ya cerrada
            return False

    def drain_events(self):
        out = []
        if self._closed:
            return out
        while True:
            try:
                out.append(self._events.get_nowait())
            except (queue.Empty, ValueError, OSError):
                return out

    # --- lado captura -------------------------------------------------------------
    def take_requests(self):
        out = []
        while len(out) < self.TAKE_LIMIT:
            try:
                out.append(self._requests.get_nowait())
            except (queue.Empty, ValueError, OSError):
                break
        return out

    def emit(self, event):
        try:
            self._events.put_nowait(event)
        except (queue.Full, ValueError, OSError):
            self.dropped_events += 1

    # --- cierre -------------------------------------------------------------------
    def close(self):
        self._closed = True
        for q in (self._requests, self._events):
            try:
                q.close()
            except Exception:
                pass


@dataclass
class SentMark:
    """Cuándo salió un comando, medido en muestras del buffer de audio (ver el docstring del módulo)."""
    req_id: int
    text: str
    position: int
    t: float


class DeviceClient:
    """
    Lo que usa la GUI para hablarle a la placa mientras la captura está en marcha. Llamar a poll() seguido (por
    ejemplo desde el temporizador de la ventana) para recibir los avisos: nunca bloquea.

        cid = engine.device.send(commands.set_frequency("L", 440))
        ...
        engine.device.poll();  engine.device.sent[cid].position   # en qué muestra salió
    """

    SENT_KEEP = 256

    def __init__(self, ctx):
        self.channel = ControlChannel(ctx)               # esto es lo que se le pasa al proceso de captura
        self._next_id = 1
        self.sent = OrderedDict()                        # req_id -> SentMark (los últimos SENT_KEEP)
        self.texts = deque(maxlen=50)                    # (texto, pos, t) de las tramas de texto recibidas
        self.losses = deque(maxlen=100)                  # (pos, tramas, t) de cada salto de seq
        self.errors = deque(maxlen=20)                   # (req_id, mensaje)
        self.stats = {}                                  # último resumen del enlace
        self.audio_channel = None                        # canal que confirmó el lector ("L" / "R"), None hasta que avise

    @property
    def closed(self):
        return self.channel._closed

    def send(self, command):
        """
        Encola un comando (un Command o una línea de texto) para que lo escriba el proceso de captura. Devuelve su
        id, o None si no se pudo (cola llena, o la captura ya terminó). Un texto inválido levanta CommandError acá mismo.
        """
        cmd = command if isinstance(command, Command) else commands.raw(command)
        req_id = self._next_id
        if not self.channel.put_request((req_id, cmd.text)):
            return None
        self._next_id += 1
        return req_id

    def set_channel(self, channel):
        """
        Pide que el buffer pase a recibir el canal "L" o "R" de la placa (desde la próxima trama). Devuelve False si
        no se pudo encolar. La confirmación llega como evento "channel" (y queda en self.audio_channel).
        """
        ch = str(channel).upper()
        if ch not in ("L", "R"):
            raise ValueError(f"Canal inválido: {channel!r} (usar 'L' o 'R').")
        return self.channel.put_request(("channel", ch))

    def poll(self):
        """Procesa los avisos que haya llegado y los devuelve (por si quien llama quiere mirarlos)."""
        events = self.channel.drain_events()
        for ev in events:
            kind = ev[0]
            if kind == "sent":
                _, req_id, pos, t, text = ev
                self.sent[req_id] = SentMark(req_id, text, pos, t)
                while len(self.sent) > self.SENT_KEEP:
                    self.sent.popitem(last=False)
            elif kind == "text":
                self.texts.append(ev[1:])
            elif kind == "loss":
                self.losses.append(ev[1:])
            elif kind == "stats":
                self.stats = ev[1]
            elif kind == "error":
                self.errors.append(ev[1:])
            elif kind == "channel":
                self.audio_channel = ev[1]
        return events

    def wait_text(self, expected, timeout=1.0):
        """Espera una trama de texto igual a `expected` (por ejemplo "PONG"). Bloquea: para scripts y pruebas, no para la GUI."""
        end = time.perf_counter() + timeout
        while True:
            for ev in self.poll():
                if ev[0] == "text" and ev[1] == expected:
                    return True
            if time.perf_counter() >= end:
                return False
            time.sleep(0.005)

    def wait_sent(self, req_id, timeout=1.0):
        """Espera el aviso de que el comando `req_id` salió y devuelve su SentMark (None si no llegó a tiempo)."""
        end = time.perf_counter() + timeout
        while True:
            self.poll()
            if req_id in self.sent:
                return self.sent[req_id]
            if time.perf_counter() >= end:
                return None
            time.sleep(0.005)

    def close(self):
        self.channel.close()
