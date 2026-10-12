"""
Prueba de humo SIN cámaras reales: crea videos sintéticos con movimiento fuerte, arranca
el sistema completo con ellos (en modo calibración, no envía nada) y comprueba que
detecta eventos, guarda clips y registra estados.

  python prueba_sistema.py            (~45 s)
  python prueba_sistema.py --servidor (prueba también el servidor de inferencia)
"""
import os
import sqlite3
import subprocess
import sys
import tempfile
import time

import cv2
import numpy as np
import yaml


def video_sintetico(ruta, segundos=12, fps=10):
    vw = cv2.VideoWriter(ruta, cv2.VideoWriter_fourcc(*"mp4v"), fps, (640, 360))
    rng = np.random.default_rng(1)
    for _ in range(segundos * fps):
        f = np.full((360, 640, 3), 90, np.uint8)
        for _ in range(6):  # bloques grandes moviéndose bruscamente
            x, y = rng.integers(0, 480), rng.integers(0, 240)
            cv2.rectangle(f, (int(x), int(y)), (int(x) + 160, int(y) + 120),
                          tuple(int(v) for v in rng.integers(0, 255, 3)), -1)
        vw.write(f)
    vw.release()


def terminar(proc):
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    else:
        proc.terminate()
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()


def main():
    con_servidor = "--servidor" in sys.argv
    with open("config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    tmp = tempfile.mkdtemp(prefix="prueba_vigilancia_")
    cams = []
    for i in (1, 2):
        v = os.path.join(tmp, f"cam{i}.mp4")
        video_sintetico(v)
        cams.append({"nombre": f"Prueba-{i}", "zona": "Simulada", "url": v})
    cfg["camaras"] = cams
    cfg["telegram"] = {"token": "", "chats": []}
    cfg["deteccion"].update(backend="movimiento", prefiltro_movimiento=0.01)
    cfg["rendimiento"]["inferencia"]["en_servidor"] = True if con_servidor else "auto"
    cfg["alertas"].update(modo_calibracion=True, enfriamiento_seg=5,
                          horario={"inicio": "00:00", "fin": "23:59", "dias": [1, 2, 3, 4, 5, 6, 7]})
    cfg["almacenamiento"].update(carpeta=os.path.join(tmp, "datos"))
    ruta_cfg = os.path.join(tmp, "config_prueba.yaml")
    with open(ruta_cfg, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True)

    print(f"Probando con 2 cámaras simuladas (servidor de inferencia: {con_servidor})…")
    proc = subprocess.Popen([sys.executable, "main.py"], env={**os.environ, "VIGILANCIA_CONFIG": ruta_cfg},
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(45)
    vivo = proc.poll() is None
    terminar(proc)

    db = os.path.join(tmp, "datos", "eventos.db")
    n = 0
    if os.path.exists(db):
        n = sqlite3.connect(db).execute("SELECT COUNT(*) FROM eventos").fetchone()[0]
    clips = os.path.join(tmp, "datos", "clips")
    n_clips = len(os.listdir(clips)) if os.path.isdir(clips) else 0
    estados = os.path.join(tmp, "datos", "estado")
    n_est = len(os.listdir(estados)) if os.path.isdir(estados) else 0

    ok = vivo and n >= 1 and n_clips >= 1 and n_est == 2
    print(f"  Sistema siguió vivo:   {'sí' if vivo else 'NO'}")
    print(f"  Eventos registrados:   {n}")
    print(f"  Clips guardados:       {n_clips}")
    print(f"  Estados de cámaras:    {n_est}/2")
    print("\nRESULTADO:", "✅ la instalación funciona" if ok else "❌ algo falló (revisa los logs en " + tmp + "/datos/logs)")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
