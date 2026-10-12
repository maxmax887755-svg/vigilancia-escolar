"""Funciones compartidas: configuración, logging, horario y estado de cámaras."""
import glob
import json
import logging
import os
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler

import yaml


def ruta_config():
    return os.environ.get("VIGILANCIA_CONFIG", "config.yaml")


def cargar_config_cruda():
    with open(ruta_config(), encoding="utf-8") as f:
        return yaml.safe_load(f)


def cargar_config():
    cfg = cargar_config_cruda()
    cfg["telegram"]["token"] = os.environ.get("TELEGRAM_TOKEN", cfg["telegram"].get("token"))
    return cfg


def configurar_logging(carpeta, nombre):
    d = os.path.join(carpeta, "logs")
    os.makedirs(d, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    fmt = logging.Formatter("%(asctime)s [%(processName)s/%(name)s] %(message)s")
    fh = RotatingFileHandler(os.path.join(d, nombre + ".log"), maxBytes=5_000_000,
                             backupCount=5, encoding="utf-8")
    sh = logging.StreamHandler()
    for h in (fh, sh):
        h.setFormatter(fmt)
        root.addHandler(h)


def en_horario(h):
    ahora = datetime.now()
    if ahora.isoweekday() not in h.get("dias", [1, 2, 3, 4, 5]):
        return False
    return h["inicio"] <= ahora.strftime("%H:%M") <= h["fin"]


# ------------------------------------------------------------ estado
def _seguro(nombre):
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in nombre)


def escribir_estado(carpeta, nombre, datos):
    d = os.path.join(carpeta, "estado")
    os.makedirs(d, exist_ok=True)
    datos = {**datos, "actualizado": time.time()}
    tmp = os.path.join(d, _seguro(nombre) + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(datos, f)
    os.replace(tmp, os.path.join(d, _seguro(nombre) + ".json"))


def leer_estados(carpeta):
    out = []
    for p in glob.glob(os.path.join(carpeta, "estado", "*.json")):
        try:
            with open(p, encoding="utf-8") as f:
                out.append(json.load(f))
        except Exception:
            pass
    return out


def limpiar_estados(carpeta):
    for p in glob.glob(os.path.join(carpeta, "estado", "*.json")):
        try:
            os.remove(p)
        except OSError:
            pass
