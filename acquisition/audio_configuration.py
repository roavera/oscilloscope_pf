"""Configuración de audio; independiente de Blackpill y simulador."""
import math
import re
import struct
import sys


def device_info(device):
    kind, ident = device if isinstance(device, (tuple, list)) else ('input', device)
    if kind == 'loopback':
        import soundcard as sc
        mic = sc.get_microphone(ident, include_loopback=True)
        if not getattr(mic, 'isloopback', False):
            raise ValueError('El dispositivo no es loopback')
        channels = mic.channels
        return kind, str(mic.id), str(mic.name), channels if isinstance(channels, int) else len(channels)
    import sounddevice as sd
    info = sd.query_devices(ident, kind='input')
    host = sd.query_hostapis(info['hostapi'])['name']
    return kind, str(host) + '|' + str(info['name']), str(info['name']), int(info['max_input_channels'])


def default_rate(device):
    kind, ident = device if isinstance(device, (tuple, list)) else ('input', device)
    if kind != 'loopback':
        import sounddevice as sd
        return float(sd.query_devices(ident, kind='input')['default_samplerate'])
    # Formato predeterminado del endpoint de reproducción de Windows.
    # No confundir esta propiedad con una consulta directa a GetMixFormat.
    if sys.platform != 'win32':
        raise ValueError('Loopback automático disponible en Windows; elegí Fs manual')
    import winreg
    match = re.search(r'\{[0-9a-fA-F-]{36}\}$', str(ident))
    if not match:
        raise ValueError('Identificador WASAPI desconocido; elegí Fs manual')
    path = r'SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Render' + '\\' + match.group() + r'\Properties'
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as key:
            data, _ = winreg.QueryValueEx(key, '{f19f064d-082c-4e27-bc73-6882a1bb8e4c},0')
        # PKEY_AudioEngine_DeviceFormat: WAVEFORMATEX blob, a veces precedido por PROPVARIANT.
        for offset in (0, 8):
            if len(data) >= offset + 16:
                tag, nch, rate, avg, align, bits = struct.unpack_from('<HHIIHH', data, offset)
                if tag in (1, 3, 65534) and 1 <= nch <= 32 and 8000 <= rate <= 768000 and avg == rate * align and align > 0:
                    return float(rate)
    except OSError:
        pass
    raise ValueError('No se pudo leer el formato de Windows; elegí Fs manual')


def resolve_rate(device, channels, requested=None):
    kind, ident = device if isinstance(device, (tuple, list)) else ('input', device)
    _, _, _, available = device_info(device)
    if not 1 <= channels <= available:
        raise ValueError(f'El dispositivo ofrece {available} canal(es)')
    rate = float(default_rate(device) if requested is None else requested)
    if not math.isfinite(rate) or not 8000 <= rate <= 768000 or rate != int(rate):
        raise ValueError('Frecuencia de audio inválida')
    if kind != 'loopback':
        import sounddevice as sd
        sd.check_input_settings(device=ident, channels=channels, dtype='float32', samplerate=rate)
    # SoundCard no ofrece check_input_settings: se valida al abrir el recorder.
    return rate


def profile_key(device, rate, channels, gain_setting):
    import json
    kind, ident, name, _ = device_info(device)
    if kind == 'input':
        import sounddevice as sd
        matches = [d for d in sd.query_devices() if d['max_input_channels'] > 0 and str(sd.query_hostapis(d['hostapi'])['name']) + '|' + str(d['name']) == ident]
        if len(matches) != 1:
            raise ValueError('Identidad ambigua: hay dispositivos con el mismo nombre y API')
    return json.dumps([kind, ident, int(rate), int(channels), str(gain_setting)], ensure_ascii=False)
