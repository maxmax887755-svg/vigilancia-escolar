"""Edita valores concretos de config.yaml conservando comentarios y formato."""
import re
import shutil
from datetime import datetime

import yaml

from config_validar import validar
from utilidades import ruta_config


def _aplicar(texto, cambios):
    lineas, seccion, hechos = texto.split("\n"), None, set()
    for i, l in enumerate(lineas):
        m = re.match(r"^([A-Za-z_]+):", l)
        if m:
            seccion = m.group(1)
        for (sec, clave), val in cambios.items():
            if seccion == sec and re.match(rf"^\s+{clave}:", l) and (sec, clave) not in hechos:
                nueva = re.sub(
                    rf"^(\s+{clave}:)\s*(\{{[^}}]*\}}|[^#\s][^#]*?)(\s+#.*)?$",
                    lambda mm: f"{mm.group(1)} {val}{mm.group(3) or ''}", l)
                if nueva != l or str(val) in l:
                    lineas[i] = nueva
                    hechos.add((sec, clave))
    faltan = set(cambios) - hechos
    if faltan:
        raise ValueError(f"No se encontró en config.yaml: {sorted(faltan)}")
    return "\n".join(lineas)


def editar_config(cambios):
    """cambios = {('deteccion','umbral'): 0.7, ...}. Valida y revierte si queda inválido."""
    ruta = ruta_config()
    copia = f"{ruta}.{datetime.now():%Y%m%d_%H%M%S}.bak"
    shutil.copy2(ruta, copia)
    with open(ruta, encoding="utf-8") as f:
        original = f.read()
    try:
        nuevo = _aplicar(original, cambios)
        antes, _ = validar(yaml.safe_load(original))
        despues, _ = validar(yaml.safe_load(nuevo))
        nuevos = [e for e in despues if e not in antes]   # solo bloquea lo que ESTE cambio rompe
        if nuevos:
            raise ValueError("; ".join(nuevos))
    except Exception:
        shutil.copy2(copia, ruta)
        raise
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(nuevo)
    return copia
