"""Proceso único que carga el modelo y atiende a todas las cámaras (con lotes)."""
import logging
import queue
import time

from detector import crear_modelo
from utilidades import configurar_logging

MAX_EDAD_SEG = 3.0   # una ventana más vieja que esto ya no sirve: se descarta


def servidor(cfg, cola_in, colas_out, listo):
    configurar_logging(cfg["almacenamiento"]["carpeta"], "inferencia")
    log = logging.getLogger("inferencia")
    modelo = crear_modelo(cfg["deteccion"])
    lote_max = cfg.get("rendimiento", {}).get("inferencia", {}).get("lote_max", 8)
    listo.set()
    log.info("Servidor de inferencia listo (lote máx. %d)", lote_max)
    vistos, t_log = 0, time.time()

    while True:
        try:
            lote = [cola_in.get(timeout=1)]
        except queue.Empty:
            continue
        while len(lote) < lote_max:
            try:
                lote.append(cola_in.get_nowait())
            except queue.Empty:
                break
        vivos = [i for i in lote if time.time() - i["t"] < MAX_EDAD_SEG]
        if not vivos:
            continue
        try:
            puntajes = modelo.inferir([i["x"] for i in vivos])
        except Exception:
            log.exception("Error de inferencia")
            puntajes = [None] * len(vivos)
        for i, s in zip(vivos, puntajes):
            try:
                colas_out[i["grupo"]].put_nowait({"cam": i["cam"], "score": s})
            except queue.Full:
                pass
        vistos += len(vivos)
        if time.time() - t_log > 60:
            log.info("%d ventanas procesadas en el último minuto", vistos)
            vistos, t_log = 0, time.time()
