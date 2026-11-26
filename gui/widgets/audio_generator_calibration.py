"""Calibración de entradas físicas de audio con generador externo."""
import numpy as np
from PySide6.QtWidgets import QInputDialog, QMessageBox
from acquisition.audio_configuration import profile_key, device_info


def calibrate(window):
    scope = window.oscilloscope
    manager = scope.acquisition
    try:
        if manager.source != manager.AUDIO or not manager.is_running:
            raise ValueError('Iniciá una entrada física de audio antes de calibrar.')
        kind, _, name, _ = device_info(manager.device)
        if kind != 'input':
            raise ValueError('Loopback no admite calibración en voltios físicos.')
        setting, ok = QInputDialog.getText(window, 'Condiciones de calibración',
            'Identificá la ganancia de entrada (Windows, interfaz, etc.). No la cambies durante la calibración.',
            text=getattr(manager, 'audio_gain_setting', ''))
        if not ok:
            return
        setting = setting.strip()
        if not setting:
            raise ValueError('Identificá las condiciones de ganancia.')
        rate = manager.sample_rate
        channels = manager.channels
        key = profile_key(manager.device, rate, channels, setting)
        result = {}
        def capture(ch, reference):
            # Se lee una copia de las muestras originales, antes de filtros y calibración.
            x = np.asarray(manager.get_data(channel=ch-1, count=int(rate * 0.25)), dtype=float).reshape(-1)
            if len(x) < int(rate * 0.2) or not np.isfinite(x).all():
                raise ValueError('No hay suficientes muestras RAW válidas.')
            if np.max(np.abs(x)) >= .98:
                raise ValueError('Señal próxima a saturación. Reducí la amplitud.')
            t = np.arange(len(x)) / rate
            w = 2 * np.pi * 1000 * t
            a = np.column_stack((np.sin(w), np.cos(w), np.ones(len(x))))
            coeff = np.linalg.lstsq(a, x, rcond=None)[0]
            amp = float(np.hypot(coeff[0], coeff[1]))
            if amp < .005 or np.sqrt(np.mean((x-a@coeff)**2)) > .05 * amp:
                raise ValueError('Señal insuficiente o no senoidal estable de 1 kHz. Revisá conexión, ganancia y frecuencia.')
            return 2*amp, float(coeff[2])
        for ch in range(1, channels+1):
            values = []
            for step in (1, 2):
                ref, ok = QInputDialog.getDouble(window, f'CH{ch} — referencia {step}',
                    'Conectá el generador al canal indicado. Seno 1 kHz, offset 0 V. Configurá la carga correcta (High Z si corresponde). Introducí Vpp real esperado en la entrada. Usá una amplitud distinta para verificar.',
                    .2 if step == 1 else .4, .001, 100.0, 5)
                if not ok:
                    return
                if QMessageBox.question(window, 'Capturar RAW', '¿La señal ya está estable desde hace al menos un segundo?') != QMessageBox.StandardButton.Yes:
                    return
                pp, mean = capture(ch, ref)
                values.append((ref, pp, mean))
            v1, x1, m1 = values[0]
            v2, x2, m2 = values[1]
            if abs(v2-v1) < .2*v1:
                raise ValueError('Usá referencias que difieran al menos 20 %.')
            gain = v1/x1
            error = abs(gain*x2-v2)/v2
            if error > .05:
                raise ValueError(f'CH{ch}: error de verificación {error:.1%}; supera 5 %. No se guardó el perfil.')
            result[f'ch{ch}'] = dict(gain_v_per_unit=gain, offset_volts=-gain*m1, verified=True,
                method='generator_1kHz', verification_error=error)
        if QMessageBox.question(window, 'Guardar calibración',
                f'{name} — {rate:g} Hz. Verificación relativa al generador superada (5 %). ¿Guardar y reiniciar adquisición?') != QMessageBox.StandardButton.Yes:
            return
        scope.disconnect_acquisition()
        cal = scope.voltage_calibration
        old = cal.audio_profiles.get(key)
        cal.audio_profiles[key] = result
        try:
            cal.save()
        except Exception:
            if old is None:
                cal.audio_profiles.pop(key, None)
            else:
                cal.audio_profiles[key] = old
            scope.start_acquisition()
            raise
        manager.audio_gain_setting = setting
        manager.audio_profile_key = key
        scope.start_acquisition()
    except Exception as exc:
        QMessageBox.warning(window, 'Calibración', str(exc))
