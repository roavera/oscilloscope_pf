# Frecuencia y período — actualización de mediciones

Ejecutar con la aplicación cerrada:

```powershell
python aplicar_frecuencia_periodo.py --apply
python main.py
```

El aplicador puede instalar sobre la versión base `main` (commit
`e165496e45115f42f3a6253de2bff169562597b2`) o sobre el paquete anterior de
mediciones de amplitud. Reconoce archivos ya instalados, guarda respaldos
antes de reemplazar y se detiene ante cambios propios no reconocidos.
Sin `--apply`, solo comprueba. También admite `--project "C:/ruta/proyecto"`.
No usa la red, Git ni modifica GitHub.

## Uso

Abrí MEDICIONES y elegí CH1 o CH2. Las casillas Frecuencia y Período permiten
mostrar u ocultar las lecturas. El panel indica cuántos períodos se usaron.
Las mediciones de amplitud anteriores se conservan. En STOP se congelan
las mediciones; cambiar zoom, delay o interpolación gráfica no las altera.
La región medida sigue siendo la captura completa, no solo el área del zoom.

## Cálculo discreto

1. Se toma la señal del canal, con el procesamiento de adquisición ya aplicado.
2. Los percentiles 5 y 95 definen niveles representativos bajo y alto. Su punto
   medio es el nivel de cruce. Se usa una banda de histéresis de ±10% del rango.
3. Para aceptar un cruce ascendente, la señal debe pasar del umbral inferior
   al superior. Dentro de ese recorrido se localiza el último cruce del nivel
   central y se interpola linealmente entre las dos muestras que lo rodean.
4. Se calculan diferencias entre posiciones de cruces consecutivos en muestras.
   Se exige al menos 3 cruces (2 intervalos), 8 muestras por intervalo y que
   ningún intervalo se aparte más del 15% de la mediana.
5. Se verifica además que la forma de onda se repita: correlación normalizada
   de al menos 0,6 entre la señal y su versión desplazada un período estimado.
6. Con los intervalos aceptados se calcula su media: T = media(intervalos)/Fs;
   la frecuencia es f = 1/T. No se reemplazan silenciosamente períodos malos:
   una captura irregular muestra «—» con el motivo.

La interpolación temporal usada para estimar el cruce pertenece al cálculo;
no depende de la opción de interpolación gráfica.

## Modos

- Sampling: captura sin interpolar.
- Average: señal promediada que se presenta.
- High Resolution: señal reducida, usando Fs efectiva = Fs original / factor
  efectivo de reducción. El factor se toma del procesamiento de esa captura.
- Peak Detect: muestras originales de la captura, antes de agrupar extremos.
- Envelope, Roll y FastAct: siguen sin mediciones en esta versión.

Los tiempos y frecuencias no requieren calibración de amplitud: se expresan
en Hz/kHz y s/ms/µs también con audio digital. La exactitud temporal depende
además de la frecuencia de muestreo real del hardware.

## Límites y motivos de «—»

Si faltan ciclos, aumentá Time/div hasta capturar al menos tres cruces
ascendentes completos. Si hay menos de 8 muestras por período, usá menor
frecuencia de señal o menor reducción Hi-Res. Para Fs=97.656,25 muestras/s,
este criterio limita la estimación a aproximadamente 12,2 kHz en Sampling;
para audio de 48 kHz, aproximadamente 6 kHz. Cerca del límite la estimación
puede rechazarse por la distribución de muestras/cruces.

El estimador está pensado para seno, cuadrada y triangular periódicas.
No garantiza identificar la fundamental de señales con varias componentes,
modulación, varios cruces por ciclo o pulsos extremadamente estrechos.
El umbral por percentiles puede no representar pulsos con muy bajo duty.
El filtrado de calidad reduce falsas lecturas, pero no es una prueba absoluta
de periodicidad ni puede detectar/corregir aliasing.

## Prueba rápida

Simulador, Sampling, seno 1 kHz, amplitud pico 1 V, offset 0, ruido 0,
Time/div 1 ms/div y escala vertical 0,5 V/div. Esperá aproximadamente:

- Frecuencia: 1 kHz.
- Período: 1 ms.
- Vpp: 2 V; RMS: 0,707 V.

Probá CH2 con 500 Hz: aproximadamente 2 ms. Agregá un poco de ruido y luego
probá STOP. Si disminuís mucho Time/div, se indica que faltan ciclos.

## Verificación

30 pruebas de cálculo e integración Qt aprobadas: las 15 de amplitud y
15 de frecuencia/período. Se probaron ambas frecuencias de muestreo, seno,
cuadrada, triangular, offset, ruido moderado, ruido aleatorio, señal constante,
capturas cortas, cruces irregulares, Sample/Avg/Hi-Res/Peak, canales y estados.
También se comprobó el simulador en vivo (CH1 1 kHz, CH2 500 Hz), STOP y el
panel con tema oscuro. No se validó hardware físico ni un ejecutable Windows.
Entorno: Linux, Python 3.12, NumPy 2.3.5, PySide6 6.12.0, pyqtgraph 0.14.0.

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

Implementación: `processing/measurements.py` (cuentas),
`gui/oscilloscope/measurements.py` (datos/Fs/estado) y
`gui/panels/measurement_controls.py` (lecturas).
