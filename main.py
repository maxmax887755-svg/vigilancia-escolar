"""
Sistema de detección de violencia física en cámaras escolares.
  python main.py             arranca el sistema
  python main.py --verificar prueba la conexión de cada cámara
  python main.py --probar    envía un mensaje de prueba a Telegram
"""
import logging
import math
import multiprocessing as mp
import os
import signal
import sys
import time

from alertas import Telegram
from config_validar import validar
from detector import usa_servidor
from registro import Registro
from servidor_inferencia import servidor
from utilidades import (cargar_config, configurar_logging, leer_estados,
                        limpiar_estados)
from verificar import verificar_camaras
from vigilante import vigilar_grupo

SIN_RESPUESTA_SEG = 90


def main():
    cfg = cargar_config()
    carpeta = cfg["almacenamiento"]["carpeta"]
    os.makedirs(carpeta, exist_ok=True)
    configurar_logging(carpeta, "principal")
    log = logging.getLogger("principal")
    tg = Telegram(cfg["telegram"])

    if "--probar" in sys.argv:
        print("Enviado" if tg.aviso("✅ Prueba del sistema de vigilancia") else "Falló")
        return
    if "--verificar" in sys.argv:
        verificar_camaras(cfg)
        return

    errores, avisos = validar(cfg)
    for a in avisos:
        log.warning("AVISO: %s", a)
    if errores:
        for e in errores:
            log.error("ERROR DE CONFIGURACIÓN: %s", e)
        sys.exit(1)

    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    ctx = mp.get_context("spawn")
    cams = [c for c in cfg["camaras"] if c.get("activa", True)]
    por_proc = cfg.get("rendimiento", {}).get("camaras_por_proceso", 6)
    n_grupos = math.ceil(len(cams) / por_proc)
    grupos = [cams[i * por_proc:(i + 1) * por_proc] for i in range(n_grupos)]

    reg = Registro(cfg["almacenamiento"])
    reg.purgar()
    limpiar_estados(carpeta)

    con_servidor = usa_servidor(cfg)
    cola_in = colas_out = listo = srv = None
    if con_servidor:
        cola_max = cfg.get("rendimiento", {}).get("inferencia", {}).get("cola_max", 200)
        cola_in = ctx.Queue(cola_max)
        colas_out = [ctx.Queue(200) for _ in grupos]
        listo = ctx.Event()

        def lanzar_servidor():
            listo.clear()
            p = ctx.Process(target=servidor, args=(cfg, cola_in, colas_out, listo),
                            name="inferencia", daemon=True)
            p.start()
            return p

        srv = lanzar_servidor()
        if not listo.wait(180):
            log.error("El servidor de inferencia no arrancó (revisa el modelo ONNX).")
            srv.terminate()
            sys.exit(1)

    def lanzar_grupo(i):
        p = ctx.Process(target=vigilar_grupo, name=f"grupo{i}", daemon=True,
                        args=(i, grupos[i], cfg, cola_in, colas_out[i] if colas_out else None))
        p.start()
        return p

    procs = {i: [lanzar_grupo(i), time.time()] for i in range(n_grupos)}
    modo = "CALIBRACIÓN (no envía alertas)" if cfg["alertas"]["modo_calibracion"] else "ACTIVO"
    extra = "\n⚠️ Detector de PRUEBA (no es protección real)" if cfg["deteccion"]["backend"] == "movimiento" else ""
    tg.aviso(f"🟢 Sistema iniciado: {len(cams)} cámaras en {n_grupos} procesos. Modo: {modo}.{extra}")
    log.info("Sistema iniciado: %d cámaras, %d grupos, servidor=%s", len(cams), n_grupos, con_servidor)

    ult_purga = ult_latido = time.time()
    hb = cfg["alertas"]["heartbeat_horas"] * 3600
    try:
        while True:
            time.sleep(10)
            if srv is not None and not srv.is_alive():
                log.error("Servidor de inferencia caído: reiniciando")
                tg.aviso("🔄 Reiniciando el servidor de inferencia (falla interna).")
                srv = lanzar_servidor()
            estados = {e["nombre"]: e for e in leer_estados(carpeta)}
            for i, (p, t0) in list(procs.items()):
                nombres = [c["nombre"] for c in grupos[i]]
                ult = max([estados.get(n, {}).get("actualizado", 0) for n in nombres] + [0])
                colgado = time.time() - t0 > 120 and time.time() - ult > SIN_RESPUESTA_SEG
                if not p.is_alive() or colgado:
                    log.error("Grupo %d %s: reiniciando", i, "colgado" if colgado else "caído")
                    tg.aviso(f"🔄 Reiniciando vigilancia del grupo {i} "
                             f"({len(nombres)} cámaras) por falla interna.")
                    if p.is_alive():
                        p.terminate()
                    procs[i] = [lanzar_grupo(i), time.time()]
            if time.time() - ult_purga > 3600:
                reg.purgar()
                ult_purga = time.time()
            if time.time() - ult_latido > hb:
                sin = [n for n, e in estados.items() if not e.get("online")]
                txt = f"💚 Sistema activo: {len(cams) - len(sin)}/{len(cams)} cámaras en línea. Modo: {modo}."
                if sin:
                    txt += "\nSin señal: " + ", ".join(sin[:15]) + ("…" if len(sin) > 15 else "")
                tg.aviso(txt)
                ult_latido = time.time()
    except KeyboardInterrupt:
        log.info("Apagando…")
        for p, _ in procs.values():
            p.terminate()
        if srv is not None:
            srv.terminate()


if __name__ == "__main__":
    main()
