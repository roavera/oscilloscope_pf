"""Lector Blackpill: sesión -> muestras normalizadas + avisos de continuidad.

No crea hilos ni dibuja: open/read_chunk/close deben ejecutarse en el hilo
(o proceso) de adquisición. No llamar sus métodos concurrentemente.

channel='L' o 'R': read_chunk devuelve float32 (N,), compatible con el lector
original. channel='LR': devuelve (N, 2), columnas L/R simultáneas.
La propiedad channels identifica las columnas/canal de la salida.

read_chunk() -> (samples, discontinuity, offset).
Si discontinuity es True, el historial debe cortarse antes de samples[offset:].
Si hay varios cortes, offset señala el ÚLTIMO: solo ese sufijo es continuo.
take_restart() avisa un cambio de canal/reinicio solicitado (offset 0).
No mezclar buffers de distintas selecciones de canal.

Requiere los protocol.py, framing.py, commands.py y session.py actualizados.
El simulator.py original solo admite STREAM:1; debe actualizarse para L/R.
"""
from __future__ import annotations

import time
import numpy as np

from . import commands
from .errors import CommandError, CommunicationError, NoAudio
from .framing import AudioFrame, TextFrame
from .protocol import FIRMWARE_FS
from .session import DeviceSession
from .transport import DEFAULT_USB_IDS, SerialTransport, find_blackpill_port

CHANNEL_COLUMN = {'L': 0, 'R': 1}  # Compatibilidad; no usar para indexar mono R.
STATS_PERIOD = 1.0
LOSS_EVENT_PERIOD = 0.1
PING_WAIT = 0.5
FS_SETTLE = 0.5
FS_WINDOW = 2.0


def _print_flush(message):
    print(message, flush=True)


def _channel(value):
    ch = str(getattr(value, 'value', value)).strip().upper()
    if ch not in ('L', 'R', 'LR'):
        raise CommandError(f"Canal inválido: {value!r}; usar L, R o LR.")
    return ch


class BlackPillReader:
    def __init__(self, ctrl=None, *, simulated=False, port=None,
                 usb_ids=DEFAULT_USB_IDS, fs=FIRMWARE_FS, channel='L',
                 first_data_timeout=3.0, stall_timeout=2.0, transport=None,
                 clock=time.perf_counter, log=None):
        self.channel = _channel(channel)
        self.fs = float(fs)
        self._first_data_timeout = float(first_data_timeout)
        self._stall_timeout = float(stall_timeout)
        if not all(np.isfinite(v) and v > 0 for v in
                   (self.fs, self._first_data_timeout, self._stall_timeout)):
            raise ValueError('Fs y timeouts deben ser positivos y finitos.')
        self._ctrl = ctrl
        self._simulated = simulated
        self._port = port
        self._usb_ids = usb_ids
        self._transport = transport
        self._clock = clock
        self._log = log or _print_flush
        self.session = None
        self.origin = ''
        self._reset_runtime()

    @property
    def channels(self):
        return ('L', 'R') if self.channel == 'LR' else (self.channel,)

    def _reset_runtime(self):
        self._out = []
        self._out_count = 0
        self._lost_flag = False
        self._cut_offset = 0
        self._restart_offset = None
        self._chunk_restart = None
        self._pos = 0
        self._last_audio_t = None
        self._first_audio_t = None
        self._stream_requested_t = None
        self._pong_seen = False
        self.texts = []
        self._pending_loss = None
        self._last_loss_emit = 0.0
        self._last_stats_t = 0.0
        self._discarded_audio_frames = 0
        self._reported_channel = None
        self._reset_rate()

    def _reset_rate(self):
        self.fs_measured = None
        self._rate_t0 = None
        self._rate_n0 = self._pos

    def _empty(self):
        shape = (0, 2) if self.channel == 'LR' else (0,)
        return np.empty(shape, dtype=np.float32)

    def open(self, should_stop=None):
        if self.session is not None:
            raise CommunicationError('El lector ya está abierto.')
        self._reset_runtime()
        if should_stop is not None and should_stop():
            return False
        transport = self._transport if self._transport is not None else self._make_transport()
        self.origin = transport.description
        self.session = DeviceSession(transport)
        try:
            self.session.open()
            self.session.start_stream(self.channel)
            self._stream_requested_t = self._clock()
            # Los pedidos de la GUI se atienden en read_chunk, después del arranque.
            if not self._wait_first_audio(should_stop):
                self.close()
                return False
            return True
        except BaseException:
            self.close()
            raise

    def close(self):
        s = self.session
        if s is None:
            return
        try:
            self._flush_loss()
            self._emit(('stats', self._stats(s)))
        finally:
            try:
                s.close()
            finally:
                self.session = None
                self._out.clear()
                self._out_count = 0

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()

    def _make_transport(self):
        if self._simulated:
            from .simulator import SimulatedTransport
            return SimulatedTransport(clock=self._clock)
        return SerialTransport(find_blackpill_port(self._usb_ids, self._port))

    def read_chunk(self):
        if self.session is None:
            raise CommunicationError('La Blackpill no está abierta: falta open().')
        self._serve_requests()
        self._poll()
        now = self._clock()
        self._check_stall(now)
        self._periodic(now)
        return self._take_output()

    def _poll(self):
        # El parser no da una posición por resincronización. Conservadoramente
        # descartar lo pendiente y marcar un corte al final de este lote.
        before = self.session.parser.stats.junk_bytes
        frames = self.session.poll()
        desync = self.session.parser.stats.junk_bytes > before
        if desync:
            self._out.clear()
            self._out_count = 0
        self._ingest(frames)
        if desync:
            self._out.clear()
            self._out_count = 0
            self._mark_cut()

    def _mark_cut(self):
        self._lost_flag = True
        self._cut_offset = self._out_count
        self._reset_rate()

    def _take_output(self):
        self._chunk_restart = None
        if not self._out:
            # Mantener el corte/reinicio hasta entregarlo junto con muestras.
            return self._empty(), False, 0
        x = self._out[0] if len(self._out) == 1 else np.concatenate(self._out, axis=0)
        lost, offset = self._lost_flag, self._cut_offset
        restart = self._restart_offset
        self._out = []
        self._out_count = 0
        # Si el corte vino DESPUÉS de la última muestra (p.ej. en texto),
        # se informa offset=len(x) y se conserva también para el próximo bloque.
        trailing_cut = lost and offset == len(x)
        self._lost_flag = trailing_cut
        self._cut_offset = 0
        self._restart_offset = None
        self._chunk_restart = restart
        return np.ascontiguousarray(x, dtype=np.float32), lost, offset

    def take_restart(self):
        value, self._chunk_restart = self._chunk_restart, None
        return value

    def _ingest(self, frames):
        now = self._clock()
        for fr in frames:
            # La secuencia es global: también puede faltar algo antes de texto.
            if fr.lost_before:
                self._mark_cut()
                self._note_loss(fr.lost_before, now)
            if isinstance(fr, TextFrame):
                if fr.text == 'PONG':
                    self._pong_seen = True
                self.texts.append((fr.text, self._pos))
                del self.texts[:-20]
                self._emit(('text', fr.text, self._pos, now))
            elif isinstance(fr, AudioFrame):
                # STREAM:0 puede dejar audio en tránsito: no incorporarlo.
                if self.session is not None and not self.session.stream_on:
                    continue
                if not all(ch in fr.channels for ch in self.channels):
                    self._discarded_audio_frames += 1
                    self._mark_cut()
                    continue
                if self.channel == 'LR':
                    x = fr.samples[:, [fr.channels.index('L'), fr.channels.index('R')]]
                else:
                    x = fr.samples[:, fr.channels.index(self.channel)]
                self._out.append(x)
                self._out_count += len(x)
                self._pos += len(x)
                self._last_audio_t = now
                if self._first_audio_t is None:
                    self._first_audio_t = now
                if self._reported_channel != self.channel:
                    self._reported_channel = self.channel
                    self._emit(('channel', self.channel, self._pos - len(x), now))

    def set_channel(self, channel):
        """Pedir otro canal desde el hilo lector; la GUI debe usar su cola.

        Descarta muestras pendientes de la selección anterior. El próximo
        bloque entregado tendrá take_restart()==0. Las tramas viejas con
        canales incompatibles se descartan, no se renombran como otro canal.
        """
        ch = _channel(channel)
        if ch == self.channel:
            return
        if self.session is not None and self.session.stream_on:
            self.session.send(commands.stream(True, ch))
            self._stream_requested_t = self._clock()
        self._apply_selection(ch)

    def _set_channel(self, channel):
        self.set_channel(channel)

    def _apply_selection(self, ch):
        self.channel = ch
        self._out.clear()
        self._out_count = 0
        self._cut_offset = 0
        self._restart_offset = 0
        self._last_audio_t = None
        self._reported_channel = None
        self._reset_rate()

    def _serve_requests(self):
        if self._ctrl is None:
            return
        for req_id, text in self._ctrl.take_requests():
            try:
                if req_id == 'channel':
                    self.set_channel(text)
                    continue
                cmd = self.session.send(text)
                state = commands.stream_state(cmd.text)
                if state is not None:
                    # También coordinar comandos STREAM enviados como texto.
                    ch = self.session.stream_channel if state else self.channel
                    self._apply_selection(ch)
                    self._stream_requested_t = self._clock() if state else None
                self._emit(('sent', req_id, self._pos, self._clock(), cmd.text))
            except CommandError as exc:
                self._emit(('error', req_id, str(exc)))

    def _wait_first_audio(self, should_stop):
        for duration, ping in ((self._first_data_timeout, False), (PING_WAIT, True)):
            if should_stop is not None and should_stop():
                return False
            if ping:
                self.session.send(commands.ping())
            end = self._clock() + duration
            while self._clock() < end:
                if should_stop is not None and should_stop():
                    return False
                self._poll()
                if self._out_count:
                    return True
        detail = 'Responde PONG, pero no llega audio del canal solicitado.' if self._pong_seen else 'Tampoco se recibió PONG.'
        raise NoAudio(f'No llegó audio válido para {self.channel} ({self.origin}). {detail}')

    def _check_stall(self, now):
        if not self.session.stream_on:
            return
        reference = self._last_audio_t if self._last_audio_t is not None else self._stream_requested_t
        if reference is not None and now - reference > self._stall_timeout:
            raise NoAudio(f'No llega audio válido para {self.channel} desde hace {now-reference:.1f} s ({self.origin}).')

    def _note_loss(self, frames, now):
        if self._pending_loss is None:
            self._pending_loss = [self._pos, 0, now]
        self._pending_loss[1] += frames

    def _flush_loss(self):
        if self._pending_loss is not None:
            pos, frames, when = self._pending_loss
            self._pending_loss = None
            self._emit(('loss', pos, frames, when))

    def _periodic(self, now):
        if now - self._last_loss_emit >= LOSS_EVENT_PERIOD:
            self._flush_loss()
            self._last_loss_emit = now
        self._measure_fs(now)
        if now - self._last_stats_t >= STATS_PERIOD:
            self._last_stats_t = now
            self._emit(('stats', self._stats(self.session)))

    def _measure_fs(self, now):
        # Tasa recibida aproximada; no mide el reloj del ADC ni calibra Fs.
        # No convertir saltos de seq a muestras: pueden incluir texto perdido.
        if not self.session.stream_on or self._last_audio_t is None:
            return
        if self._rate_t0 is None:
            self._rate_t0, self._rate_n0 = now, self._pos
        elif now - self._rate_t0 >= FS_WINDOW:
            self.fs_measured = (self._pos-self._rate_n0)/(now-self._rate_t0)
            self._rate_t0, self._rate_n0 = now, self._pos

    def link_stats(self):
        return self._stats(self.session) if self.session is not None else {}

    def _stats(self, session):
        d = session.parser.stats.as_dict()
        d.update(fs_measured=self.fs_measured, samples=self._pos,
                 lost_samples_est=None, channel=self.channel,
                 discarded_audio_frames=self._discarded_audio_frames,
                 dropped_events=getattr(self._ctrl, 'dropped_events', 0))
        return d

    def _emit(self, event):
        if self._ctrl is not None:
            self._ctrl.emit(event)
