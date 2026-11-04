"""Responsabilidades internas de OscilloscopeWidget.

Los mixins comparten el estado inicializado por el widget; no se instancian
por separado y no crean QObject, señales ni hilos adicionales.
El punto de entrada público sigue siendo gui.oscilloscope_widget.
"""
