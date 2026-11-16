"""Integra mediciones sin alterar adquisición, trigger ni datos del gráfico."""
from processing.measurements import (measure_amplitude, measure_timing,
                                     measure_transients, measure_interchannel)


class MeasurementsMixin:
    def _clear_measurements(self):
        self._measurement_results = [None, None]
        self._measurement_timing = [None, None]
        self._measurement_transients = [None, None]
        self._measurement_interchannel = None
        self._measurement_units = ["u.a.", "u.a."]
        self._measurement_mode = None
        self._measurement_source = None
        self._refresh_measurements()

    def _capture_measurements(self, samples):
        mode = self.acquisition_processor.get_mode()
        if mode not in ("sampling", "average", "high_resolution", "peak_detect"):
            self._clear_measurements()
            return
        active = self.acquisition.active_channels
        source = self.acquisition.source
        physical = self.voltage_calibration.as_dict()["blackpill_usb"]
        # Hi-Res reduce la cantidad de muestras y la frecuencia efectiva.
        factor = self._last_high_resolution_factor if mode == "high_resolution" else 1
        rate = self.sample_rate / factor
        self._measurement_results = [
            measure_amplitude(samples[:, ch], rate) if active[ch] else None
            for ch in (0, 1)
        ]
        self._measurement_timing = [
            measure_timing(samples[:, ch], rate) if active[ch] else None
            for ch in (0, 1)
        ]
        self._measurement_transients = [
            measure_transients(samples[:, ch], rate) if active[ch] else None
            for ch in (0, 1)
        ]
        self._measurement_interchannel = (
            measure_interchannel(samples[:, 0], samples[:, 1], rate)
            if all(active) else None
        )
        self._measurement_units = [
            "V" if source == "simulator" or (
                source == "blackpill_usb" and physical[f"ch{ch + 1}"]["verified"]
            ) else "u.a." for ch in (0, 1)
        ]
        self._measurement_progress = self.acquisition_processor.get_progress()
        self._measurement_mode = mode
        self._measurement_source = source
        self._refresh_measurements()

    def _refresh_measurements(self):
        mode = self.acquisition_processor.get_mode()
        source = self.acquisition.source
        results = getattr(self, "_measurement_results", [None, None])
        timing = getattr(self, "_measurement_timing", [None, None])
        transients = getattr(self, "_measurement_transients", [None, None])
        interchannel = getattr(self, "_measurement_interchannel", None)
        units = getattr(self, "_measurement_units", ["u.a.", "u.a."])
        active = self.acquisition.active_channels
        supported = mode in ("sampling", "average", "high_resolution", "peak_detect")
        same_capture = (getattr(self, "_measurement_mode", None) == mode and
                        getattr(self, "_measurement_source", None) == source)
        notes = []
        for ch in (0, 1):
            if not supported:
                results[ch] = None
                timing[ch] = None
                transients[ch] = None
                interchannel = None
                note = "Mediciones no disponibles en este modo en esta versión"
            elif not active[ch]:
                results[ch] = None
                timing[ch] = None
                transients[ch] = None
                interchannel = None
                note = "Canal sin datos o desactivado"
            elif not same_capture or results[ch] is None:
                results[ch] = None
                timing[ch] = None
                transients[ch] = None
                interchannel = None
                note = "Sin captura válida"
            else:
                if self._audio_error is not None or self._connection_state != "connected":
                    note = "Última captura · fuente desconectada o con error"
                elif not self.running:
                    note = "STOP · captura congelada"
                elif not self.trigger_found and self.trigger_mode in ("Normal", "Single"):
                    note = "Última captura · esperando disparo"
                else:
                    note = "Captura completa"
                if mode == "average":
                    count, target = self._measurement_progress
                    note += f" · señal promediada ({count}/{target})"
                elif mode == "high_resolution":
                    note += " · señal Hi-Res"
                elif mode == "peak_detect":
                    note += " · muestras originales de Peak Detect"
                if source == "audio":
                    note += " · unidades digitales"
                elif source == "blackpill_usb" and units[ch] != "V":
                    note += " · escala sin calibración verificada"
                elif source == "simulator":
                    note += " · voltios simulados"
            notes.append(note)
        self.controls.measurement_controls.set_readings(
            results, units, notes, timing, transients, interchannel
        )
