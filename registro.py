import logging
import os
import sqlite3
import time
from datetime import datetime

import cv2

log = logging.getLogger("registro")
COLUMNAS_EXTRA = {"etiqueta": "TEXT", "etiqueta_por": "TEXT", "zona": "TEXT"}


def abrir_db(ruta):
    c = sqlite3.connect(ruta, timeout=10)
    c.execute(
        "CREATE TABLE IF NOT EXISTS eventos(id INTEGER PRIMARY KEY, ts TEXT,"
        " camara TEXT, puntaje REAL, enviado INTEGER, clip TEXT)"
    )
    existentes = [r[1] for r in c.execute("PRAGMA table_info(eventos)")]
    for col, tipo in COLUMNAS_EXTRA.items():
        if col not in existentes:
            c.execute(f"ALTER TABLE eventos ADD COLUMN {col} {tipo}")
    return c


class Registro:
    def __init__(self, cfg):
        self.carpeta = cfg.get("carpeta", "datos")
        self.clips = os.path.join(self.carpeta, "clips")
        os.makedirs(self.clips, exist_ok=True)
        try:
            os.chmod(self.carpeta, 0o700)
        except OSError:
            pass
        self.db = os.path.join(self.carpeta, "eventos.db")
        self.retencion = cfg.get("retencion_dias", 7)
        self.max_gb = cfg.get("max_gb", 20)
        with abrir_db(self.db):
            pass

    def guardar_clip(self, camara, frames, fps):
        nombre = f"{camara}_{datetime.now():%Y%m%d_%H%M%S}.mp4".replace(" ", "_")
        ruta = os.path.join(self.clips, nombre)
        h, w = frames[0].shape[:2]
        for codec in ("avc1", "mp4v"):  # avc1 (H.264) se reproduce directo en navegador/Telegram
            vw = cv2.VideoWriter(ruta, cv2.VideoWriter_fourcc(*codec), fps, (w, h))
            if vw.isOpened():
                break
        for f in frames:
            vw.write(f)
        vw.release()
        return ruta

    def registrar(self, camara, zona, puntaje, enviado, clip):
        with abrir_db(self.db) as c:
            c.execute(
                "INSERT INTO eventos(ts,camara,zona,puntaje,enviado,clip) VALUES(?,?,?,?,?,?)",
                (datetime.now().isoformat(timespec="seconds"), camara, zona, puntaje, int(enviado), clip),
            )

    def purgar(self):
        limite = time.time() - self.retencion * 86400
        archivos = []
        for f in os.listdir(self.clips):
            p = os.path.join(self.clips, f)
            if os.path.getmtime(p) < limite:
                os.remove(p)
            else:
                archivos.append((os.path.getmtime(p), os.path.getsize(p), p))
        # tope de espacio: borra los más viejos si se supera max_gb
        archivos.sort()
        total, tope = sum(a[1] for a in archivos), self.max_gb * 1024 ** 3
        while archivos and total > tope:
            _, tam, p = archivos.pop(0)
            os.remove(p)
            total -= tam
            log.warning("Espacio excedido: borrado %s", os.path.basename(p))
        corte = datetime.fromtimestamp(limite).isoformat(timespec="seconds")
        with abrir_db(self.db) as c:
            c.execute("DELETE FROM eventos WHERE ts < ?", (corte,))
        log.info("Purga completada (%.2f GB en clips)", total / 1024 ** 3)
