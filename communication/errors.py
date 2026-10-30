"""Errores propios de la comunicación con la placa. Todos traen un mensaje pensado para mostrarse tal cual."""


class CommunicationError(Exception):
    """Cualquier falla del enlace con la placa."""


class PortNotFound(CommunicationError):
    """No hay ningún puerto serie que parezca la Black Pill."""


class LinkLost(CommunicationError):
    """Se perdió el enlace a mitad de la sesión (cable desenchufado, placa reiniciada, puerto cerrado)."""


class NoAudio(CommunicationError):
    """El puerto se abrió, pero la placa no manda audio."""


class CommandError(ValueError):
    """Comando mal armado: argumento fuera de rango, línea demasiado larga o con caracteres no ASCII."""
