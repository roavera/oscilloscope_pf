# CONTROL_HORIZONTAL_COMPLETO_V1
"""Escalas, posiciones, fuente y configuración de disparo de ambos canales."""

import numpy as np
from trigger.pulse_width import PulseWidthTrigger
from trigger.edge_trigger import Edge_Trigger
from trigger.timeout import TimeoutTrigger
from trigger.runt import RuntTrigger
from trigger.logic import LogicTrigger
from trigger.auto_level import estimate_auto_level


class ControlsMixin:
    """Colabora sobre el estado único inicializado por OscilloscopeWidget."""

    def reset_trigger_controls(self, _checked=False):
        self.set_trigger_type("edge")
        self.controls.trigger_controls.reset_pulse_width_settings()
        self.controls.trigger_controls.reset_advanced_settings()
        self.set_trigger_channel(1)
        self.set_trigger_level(0.0)
        self.set_trigger_slope("Rising")
        self.set_trigger_mode("Auto")
        self.set_trigger_holdoff(0.0)


    def reset_horizontal_controls(self, _checked=False):
        self.set_horizontal_zoom(1.0)
        self.set_horizontal_delay(0.0)
        self.set_time_per_division(0.001)
        self.set_horizontal_reference("Center")
        self.set_horizontal_position(0.0)


    def reset_vertical_controls(self, channel):
        if channel == 1:
            self.set_volts_per_division(0.02)
            self.set_vertical_position(0.0)
            self.controls.ch1_controls.visible_checkbox.setChecked(True)
        elif channel == 2:
            self.set_ch2_volts_per_division(0.02)
            self.set_ch2_position(0.0)
            self.controls.ch2_controls.visible_checkbox.setChecked(True)
        else:
            raise ValueError("El canal debe ser 1 o 2")


    def set_time_per_division(self, value):
        value = float(value)

        if not np.isfinite(value) or value <= 0:
            return
        if self.acquisition_processor.get_mode() != "roll":
            value = min(value, 0.05)  # Historial no-Roll limitado a < 1 s.

        if value != self.time_per_division:
            self._reset_processing()
            if self.acquisition_processor.get_mode() == "fastact":
                # Cambia el ancho de captura; la traza vieja deja de ser válida.
                self.last_acquisition = None
                self.last_math = None
                self.plot.clear_signal()
        self.time_per_division = value

        self.display_samples = max(
            2,
            int(
                self.sample_rate
                * self.time_per_division
                * self.horizontal_divisions
            ),
        )

        self.plot.set_time_per_division(value)
        self._apply_horizontal_view()
        if self.acquisition_processor.get_mode() == "roll":
            self._reset_roll_history()
        self.controls.set_time_per_division(value)

        if not self.running and self._frozen_horizontal_data is not None:
            self._redraw_frozen_horizontal()
        else:
            self._redraw_last_acquisition()
        self.update_controls_state()


    def set_horizontal_position(self, divisions):
        divisions = float(divisions)

        if not np.isfinite(divisions):
            return

        half_screen = self.horizontal_divisions / 2.0

        # Misma resolución que la perilla: 0.01 div.
        divisions = round(divisions, 2)

        self.horizontal_position_divisions = float(
            np.clip(divisions, -half_screen, half_screen)
        )

        # Cero divisiones corresponde al centro de la pantalla.
        self.trigger_position = (
            0.5
            + self.horizontal_position_divisions
            / self.horizontal_divisions
        )

        if (self.trigger.position != self.trigger_position and
                self.acquisition_processor.get_mode() != "roll"):
            self._reset_processing()
        self.trigger.set_position(self.trigger_position)
        self.plot.set_trigger_position(self.trigger_position)
        self._apply_horizontal_view()

        self.controls.set_horizontal_position(
            self.horizontal_position_divisions
        )

        if not self.running and self._frozen_horizontal_data is not None:
            self._redraw_frozen_horizontal()
        else:
            self._redraw_last_acquisition()
        self.update_controls_state()


    def set_ch2_volts_per_division(self, value):
        value = float(value)
        if not np.isfinite(value) or value <= 0:
            return
        if self.ch2_volts_per_division != value:
            self._clear_fastact_for_vertical_change()
        self.ch2_volts_per_division = value
        self.controls.ch2_controls.set_volts_per_division(value)
        self.plot.set_channel_settings(2, scale=value)
        self.update_trigger_range()


    def set_ch2_position(self, divisions):
        if not np.isfinite(divisions):
            return
        self._clear_fastact_for_vertical_change()
        self.ch2_position_divisions = float(np.clip(round(divisions, 2), -4, 4))
        self.controls.ch2_controls.set_position(self.ch2_position_divisions)
        self.plot.set_channel_settings(2, position=self.ch2_position_divisions)
        self.update_trigger_range()


    def set_trigger_holdoff(self, seconds):
        """Tiempo de espera entre disparos en segundos (0 = desactivado)."""
        seconds = float(seconds)
        if seconds != self.trigger_holdoff.seconds:
            self.trigger_holdoff.set_seconds(seconds)
            self._reset_processing()
            self.trigger_found = False
        self.controls.trigger_controls.set_holdoff(seconds)
        self.update_controls_state()

    def auto_trigger_level(self):
        """Calcula Auto Level al hacer clic; no cambia las muestras ni Volt/div."""
        from PySide6.QtWidgets import QMessageBox

        if self._closed:
            return
        channel = int(self.trigger_channel)
        if channel not in (1, 2) or channel > self.acquisition.channels:
            QMessageBox.information(self, "Auto Level", "El canal elegido no está adquirido.")
            return

        # En STOP usar preferentemente la captura congelada del usuario.
        frozen = getattr(self, "last_acquisition", None)
        if not self.running and frozen is not None:
            samples = np.asarray(frozen, dtype=np.float32)
        else:
            # El buffer guarda PCM24 normalizado; aplicar la MISMA calibración
            # que utilizan el trigger y los modos de adquisición.
            with self._buffer_lock:
                recent = self.buffer.get_data(min(
                    self.buffer.valid_samples,
                    max(32, int(round(self.sample_rate)))
                ))
            samples = (self.voltage_calibration.apply(recent, self.acquisition.source)
                       if len(recent) else np.empty((0, 2), dtype=np.float32))

        if samples.ndim != 2 or samples.shape[1] != 2:
            QMessageBox.information(self, "Auto Level", "La captura no tiene ambos canales alineados.")
            return
        level = estimate_auto_level(samples[:, channel - 1])
        if level is None:
            QMessageBox.information(
                self, "Auto Level",
                f"CH{channel}: no hay suficientes muestras o amplitud de señal "
                "para establecer un nivel automático."
            )
            return
        # Actualiza perilla, campo numérico, marcador y detector existente.
        self.set_trigger_level(level)

    def set_trigger_type(self, trigger_type):
        """Cambia de detector sin alterar niveles, escalas ni Holdoff.

        Edge se guarda aparte para conservar sus ajustes de acondicionamiento.
        El resto se reconstruye con la configuración del panel correspondiente.
        """
        kinds = ("edge", "pulse_width", "timeout", "runt", "logic")
        if trigger_type not in kinds:
            raise ValueError("Tipo de trigger no disponible")
        if trigger_type == "logic" and self.acquisition.channels < 2:
            self.controls.trigger_controls.set_trigger_type(self.trigger_kind)
            self.acquisition_error.emit("Logic requiere dos canales de entrada activos")
            return
        if trigger_type == self.trigger_kind:
            return
        if self.trigger_kind == "edge":
            self._edge_trigger_saved = self.trigger
        edge = getattr(self, "_edge_trigger_saved", None)
        if edge is None:
            edge = Edge_Trigger(level=self.trigger_level,
                                slope=self.trigger_slope,
                                position=self.trigger_position)
            self._edge_trigger_saved = edge
        settings = self.controls.trigger_controls
        common = dict(level=self.trigger_level, slope=self.trigger_slope,
                      position=self.trigger_position)
        if trigger_type == "edge":
            self.trigger = edge
            self.trigger.set_level(self.trigger_level)
            self.trigger.set_slope(self.trigger_slope)
            self.trigger.set_position(self.trigger_position)
        elif trigger_type == "pulse_width":
            self.trigger = PulseWidthTrigger(
                **common, sample_rate=self.sample_rate,
                hysteresis_fraction=edge.hysteresis_fraction,
                **settings.pulse_width_settings())
        elif trigger_type == "timeout":
            self.trigger = TimeoutTrigger(
                **common, sample_rate=self.sample_rate,
                **settings.timeout_settings())
        elif trigger_type == "runt":
            self.trigger = RuntTrigger(
                **common, sample_rate=self.sample_rate,
                **settings.runt_settings())
        else:
            self.trigger = LogicTrigger(**common, **settings.logic_settings())
        self.trigger_kind = trigger_type
        self._reset_processing()
        self.trigger_found = False
        settings.set_trigger_type(trigger_type)
        self.update_controls_state()

    def set_pulse_width_settings(self, settings):
        """Actualiza umbrales sin tocar datos, Volt/div o Time/div."""
        if self.trigger_kind != "pulse_width":
            return
        self.trigger.set_width_settings(**settings)
        self._reset_processing()
        self.trigger_found = False
        self.update_controls_state()

    def set_timeout_settings(self, settings):
        if self.trigger_kind != "timeout":
            return
        self.trigger.set_timeout_settings(**settings)
        self._reset_processing()
        self.trigger_found = False
        self.update_controls_state()

    def set_runt_settings(self, settings):
        if self.trigger_kind != "runt":
            return
        self.trigger.set_runt_settings(**settings)
        self._reset_processing()
        self.trigger_found = False
        self.update_controls_state()

    def set_logic_settings(self, settings):
        if self.trigger_kind != "logic":
            return
        self.trigger.set_logic_settings(**settings)
        self._reset_processing()
        self.trigger_found = False
        self.update_controls_state()

    def set_trigger_channel(self, channel):
        if channel not in (1, 2) or channel == self.trigger_channel:
            return
        self.trigger_channel = channel
        self._reset_processing()
        self.trigger_found = False
        self.plot.set_trigger_channel(channel)
        self.controls.trigger_controls.set_source(channel)
        # La última captura conserva su referencia; la próxima usa la nueva fuente.
        self.update_trigger_range()
        self.update_controls_state()


    def set_volts_per_division(self, value):
        value = float(value)

        if not np.isfinite(value) or value <= 0:
            return

        if self.volts_per_division != value:
            self._clear_fastact_for_vertical_change()
        self.volts_per_division = value

        self.plot.set_volts_per_division(value)
        self.controls.set_volts_per_division(value)

        self.set_vertical_position(
            self.vertical_position_divisions
        )


    def set_vertical_position(self, divisions):
        divisions = float(divisions)

        if not np.isfinite(divisions):
            return

        slider_value = max(
            -400,
            min(400, round(divisions * 100)),
        )

        if self.vertical_position_divisions != slider_value / 100.0:
            self._clear_fastact_for_vertical_change()
        self.vertical_position_divisions = slider_value / 100.0

        # Desplaza el rango visible, sin modificar las muestras.
        self.vertical_offset = (
            -self.vertical_position_divisions
            * self.volts_per_division
        )

        self.plot.set_vertical_offset(self.vertical_offset)

        self.controls.set_vertical_position(
            self.vertical_position_divisions
        )

        self.update_trigger_range()


    def update_trigger_range(self):
        scale = self.volts_per_division if self.trigger_channel == 1 else self.ch2_volts_per_division
        position = self.vertical_position_divisions if self.trigger_channel == 1 else self.ch2_position_divisions
        minimum = (-self.vertical_divisions / 2 - position) * scale
        maximum = (self.vertical_divisions / 2 - position) * scale

        self.controls.set_trigger_range(
            minimum,
            maximum,
        )


    def set_trigger_level(self, value):
        value = float(value)

        if not np.isfinite(value):
            return

        if value != self.trigger_level:
            self._reset_processing()
        self.trigger_level = value

        self.trigger.set_level(value)
        self.plot.set_trigger_level(value)
        self.controls.set_trigger_level(value)

        self.trigger_found = False
        self.update_controls_state()


    def set_trigger_slope(self, value):
        if value not in ("Rising", "Falling"):
            return

        if value != self.trigger_slope:
            self._reset_processing()
        self.trigger_slope = value

        self.trigger.set_slope(value)
        self.controls.set_trigger_slope(value)

        self.trigger_found = False
        self.update_controls_state()


    def set_trigger_mode(self, value):
        if value not in ("Auto", "Normal", "Single"):
            return

        if value == "Single":
            self.single()
            return

        if self.trigger_mode != value:
            self._reset_processing()
        self.trigger_mode = value
        self.single_mode = False
        self.trigger_found = False

        self.controls.set_trigger_mode(value)
        self.update_controls_state()
