"""Historial de muestras originales, separado del procesamiento y del gráfico."""
from collections import deque
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import csv
import json
import os
from pathlib import Path
import tempfile
import numpy as np


@dataclass(frozen=True)
class RawCapture:
    samples: np.ndarray
    sample_rate: float
    trigger_sample: float | None
    source: str
    mode: str
    captured_at: str
    config: str


def raw_capture(samples, sample_rate, trigger_sample, source, config):
    data=np.array(samples,dtype=np.float32,copy=True)
    if data.ndim!=2 or data.shape[1]!=2 or not len(data) or not np.isfinite(data).all():
        raise ValueError('Se requieren muestras originales finitas (N, 2)')
    rate=float(sample_rate)
    if not np.isfinite(rate) or rate<=0:
        raise ValueError('Frecuencia de muestreo inválida')
    if trigger_sample is not None and not np.isfinite(trigger_sample):
        raise ValueError('Referencia de trigger inválida')
    data.flags.writeable=False
    return RawCapture(data,rate,trigger_sample,str(source),config.mode,
                      datetime.now(timezone.utc).isoformat(),json.dumps(asdict(config),sort_keys=True))


class CaptureArchive:
    def __init__(self):
        self.visible=()
        self.reset()
    def reset(self):
        # La última captura visible sigue siendo exportable hasta reemplazarla.
        self.pending=deque()
    def clear(self):
        self.reset()
        self.visible=()
    def add(self,capture,target):
        if self.pending:
            old=self.pending[-1]
            if (old.config,old.sample_rate,old.source,old.samples.shape)!=(capture.config,capture.sample_rate,capture.source,capture.samples.shape):
                self.pending.clear()
        self.pending.append(capture)
        while len(self.pending)>target:self.pending.popleft()
    def publish(self):
        self.visible=tuple(self.pending)
    def snapshot(self):
        return self.visible  # Arrays propios de solo lectura; no se modifican al adquirir.


def write_csv(path,captures):
    """Escritura atómica; un error no deja un CSV parcial ni pisa el anterior."""
    captures=tuple(captures)
    if not captures:raise ValueError('No hay una captura disponible')
    path=Path(path)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',newline='',dir=path.parent,delete=False) as f:
            temporary=f.name
            metadata=[dict(capture_id=i,source=c.source,mode=c.mode,sample_rate_hz=c.sample_rate,
                           trigger_sample=c.trigger_sample,captured_at_utc=c.captured_at,
                           acquisition_config=json.loads(c.config),sample_count=len(c.samples))
                      for i,c in enumerate(captures)]
            f.write('# oscilloscope_raw_csv_v1\n')
            f.write('# units=normalized; time_reference=trigger_if_available_else_capture_start\n')
            f.write('# captures='+json.dumps(metadata,ensure_ascii=True,separators=(',',':'))+'\n')
            writer=csv.writer(f)
            writer.writerow(['captura_id','muestra','tiempo_s','ch1_raw','ch2_raw'])
            for capture_id,c in enumerate(captures):
                reference=0 if c.trigger_sample is None else c.trigger_sample
                writer.writerows((capture_id,i,format((i-reference)/c.sample_rate,'.17g'),
                                  format(float(a),'.9g'),format(float(b),'.9g'))
                                 for i,(a,b) in enumerate(c.samples))
        os.replace(temporary,path)
        temporary=None
    finally:
        if temporary is not None:os.unlink(temporary)
