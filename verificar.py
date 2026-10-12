"""python main.py --verificar : prueba cada cámara y guarda una foto de muestra."""
import os
import threading
import time

import cv2


def verificar_camaras(cfg):
    carpeta = os.path.join(cfg["almacenamiento"]["carpeta"], "verificacion")
    os.makedirs(carpeta, exist_ok=True)
    cams = [c for c in cfg["camaras"] if c.get("activa", True)]
    res = {}

    def probar(c):
        url = int(c["url"]) if str(c["url"]).isdigit() else c["url"]
        t0 = time.time()
        cap = cv2.VideoCapture(url)
        if not cap.isOpened():
            res[c["nombre"]] = "❌ No se pudo abrir (revisa URL, usuario/clave, red)"
            return
        frame, n = None, 0
        for _ in range(20):
            ok, f = cap.read()
            if ok:
                frame, n = f, n + 1
        fps = cap.get(cv2.CAP_PROP_FPS)
        cap.release()
        if frame is None:
            res[c["nombre"]] = "❌ Abre pero no entrega imagen"
            return
        h, w = frame.shape[:2]
        cv2.imwrite(os.path.join(carpeta, f"{c['nombre']}.jpg".replace(" ", "_")), frame)
        aviso = "  ⚠️ resolución alta: usa el substream" if w > 1280 else ""
        res[c["nombre"]] = f"✅ {w}x{h} ~{fps:.0f} fps, {time.time() - t0:.1f}s{aviso}"

    hilos = [threading.Thread(target=probar, args=(c,), daemon=True) for c in cams]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=40)
    print(f"\nVerificación de {len(cams)} cámaras (fotos en {carpeta}):\n")
    for c in cams:
        print(f"  {c['nombre']:<20} {res.get(c['nombre'], '❌ Sin respuesta en 40 s')}")
    print()
