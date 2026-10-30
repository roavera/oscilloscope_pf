"""
Comunicación con la placa (Black Pill STM32F411 + PCM3060, por USB CDC): recibir muestras y mandar comandos.
El protocolo completo, explicado campo por campo, está en PROTOCOLO.md.

  protocol.py   el protocolo escrito una sola vez: constantes, encabezado de trama, muestras de 24 bits <-> float
  framing.py    FrameParser: de bytes sueltos a tramas (resincroniza, cuenta pérdidas y basura)
  commands.py   catálogo de comandos PC -> placa: una función por comando, con validación
  transport.py  por dónde viajan los bytes: puerto serie real y búsqueda del COM por VID:PID
  session.py    DeviceSession: transporte + parser + envío de comandos (sin hilos ni Qt)
  simulator.py  placa simulada (FakeBlackPill) para desarrollar y probar sin hardware
  ipc.py        canal de comandos GUI -> proceso de captura, y avisos de vuelta (DeviceClient)
  worker.py     BlackPillReader: la fuente que enchufa acquisition/sources.py
  errors.py     las excepciones del paquete
  __main__.py   herramienta de consola:  python -m audio_analyzer.communications --help

Capas (cada una solo usa las de arriba): protocol -> framing / commands -> transport -> session -> worker / ipc.
Para AGREGAR un comando: una función en commands.py. Para AGREGAR un tipo de trama que mande la placa: una
entrada en protocol.py y su rama en framing.py. Para otra forma de conectarse (archivo grabado, socket...):
un Transport nuevo en transport.py. El resto no cambia.

Este paquete corre en el proceso de captura, así que no importa Qt ni scipy (solo numpy y, para el puerto real, pyserial).
"""
