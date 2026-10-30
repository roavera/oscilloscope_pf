# Protocolo PC ↔ Black Pill (STM32F411 + PCM3060, USB CDC)

El código que lo implementa es `protocol.py` (constantes y conversiones), `framing.py` (parser) y
`commands.py` (comandos). Este archivo explica el formato; si algo no coincide, manda el código.

## Placa → PC: tramas binarias (little-endian)

| offset | tamaño | campo | valor |
|---|---|---|---|
| 0 | 1 | sync | `0xAA` |
| 1 | 1 | sync | `0x55` |
| 2 | 1 | tipo | `0x01` audio · `0x02` texto |
| 3 | 1 | seq | contador de tramas de 8 bits (255 → 0). Sube también con las tramas descartadas y con las de texto |
| 4 | 2 | n | audio: frames estéreo (siempre **256**) · texto: caracteres (≤ 64) |
| 6 | … | payload | audio: n × `[L0 L1 L2 R0 R1 R2]` (24 bits con signo, LSB primero) · texto: ASCII imprimible, sin terminador |

* **fs = 97 656,25 Hz** (reloj del I2S). No viaja en el protocolo: está en `FIRMWARE_FS` y en
  `config/defaults.py` (`BLACKPILL_FS`). El lector mide cuántas muestras llegan por segundo y avisa si no coincide.
* Ancho de banda: 97 656,25 × 6 B ≈ 586 kB/s más encabezados (≈ 588 kB/s medido con el simulador).
* Normalización: muestra / 2²³ → [−1, 1). Fondo de escala = 0 dBFS.

### Cómo se validan las tramas (framing.py)

1. Se busca `AA 55`. Los bytes previos se cuentan como basura (`junk_bytes`).
2. El encabezado tiene que ser posible: audio con **n = 256 exacto** (`EXPECTED_AUDIO_FRAMES`), texto con n ≤ 64.
3. Una trama de texto tiene que ser ASCII imprimible.
4. Mientras se busca sincronismo, una trama de audio se acepta recién cuando la **siguiente** también empieza
   con `AA 55` (el audio llega sin pausas). Un `AA 55` casual dentro de los datos no pasa estas pruebas
   (`false_syncs`).
5. Un salto de `seq` = tramas perdidas (`lost_frames`). El lector informa la posición exacta del hueco y el
   analizador descarta lo anterior (una FFT con un hueco adentro no sirve).

No hay checksum: el USB protege el cable (CRC16 + reintentos), pero no protege contra un buffer pisado dentro
del firmware. **Propuesta para el firmware**: agregar un CRC (el F411 tiene CRC32 por hardware).

## PC → placa: comandos de texto

Una línea ASCII por comando, terminada **solo** en `\n` (máx. 127 caracteres). Distingue mayúsculas. Un comando
desconocido se ignora en silencio: no hay confirmación (salvo `PING` → `PONG`).

| Comando | Qué hace |
|---|---|
| `LFREQ:<Hz>` / `RFREQ:<Hz>` | frecuencia del generador de cada canal |
| `LAMP:<0-100>` / `RAMP:<0-100>` | amplitud en % del fondo de escala (entero) |
| `LON` `LOFF` `RON` `ROFF` | enciende / apaga la salida de cada canal |
| `LWAVE:<0-3>` / `RWAVE:<0-3>` | 0 seno · 1 cuadrada · 2 triangular · 3 chirp |
| `LCHIRP:<f0>,<f1>,<s>` / `RCHIRP:…` | barrido de f0 a f1 en s segundos |
| `DIFF` / `SE` | salida diferencial / simple |
| `ADC:<0|1>` / `DAC:<0|1>` | enciende / apaga el ADC / DAC del PCM3060 |
| `STREAM:<0|1>` | empieza / detiene el envío de audio |
| `PING` | la placa contesta una trama de texto `PONG` |

**Propuestas para el firmware**: contestar `OK <comando>` / `ERR <motivo>` a cada comando, y un `INFO?` que
devuelva fs, bits y versión de firmware (así la fs dejaría de estar fija en dos lugares).

## Herramienta de consola

```
python -m audio_analyzer.communications ports
python -m audio_analyzer.communications ping [--simulated]
python -m audio_analyzer.communications monitor --seconds 5 [--simulated]
python -m audio_analyzer.communications send LFREQ:440.0 LAMP:30
```
