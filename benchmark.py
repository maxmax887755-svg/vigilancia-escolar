"""
python benchmark.py
Mide cuántas ventanas por segundo procesa ESTE equipo con tu configuración y estima
cuántas cámaras puede vigilar. Es una estimación: confirma con la pestaña "Cámaras" del panel.
"""
import time

import numpy as np

from detector import crear_modelo, crear_preprocesador
from utilidades import cargar_config

cfg = cargar_config()
d, lote = cfg["deteccion"], cfg.get("rendimiento", {}).get("inferencia", {}).get("lote_max", 8)
w, h = d.get("resolucion", [640, 360])
n_vent = int(d["fps_analisis"] * d["ventana_seg"])
ventana = [np.random.randint(0, 255, (h, w, 3), np.uint8) for _ in range(n_vent)]

prep, modelo = crear_preprocesador(d), crear_modelo(d)
if d["backend"] != "onnx":
    print("⚠️ Backend de prueba: estas cifras NO representan a un modelo real. Pon backend: onnx y repite.\n")
print(f"Backend: {d['backend']} | ventana: {n_vent} cuadros de {w}x{h} | lote: {lote}\n")

t = time.time()
for _ in range(10):
    x = prep.entrada(ventana)
t_prep = (time.time() - t) / 10

lote_x = [x] * lote
modelo.inferir(lote_x)  # calentamiento
t = time.time()
rep = 10
for _ in range(rep):
    modelo.inferir(lote_x)
vps = lote * rep / (time.time() - t)

por_camara = 2.0 / d["ventana_seg"]   # ventanas/s que genera una cámara con movimiento
util = vps * 0.7                      # 30% de margen
print(f"Preprocesado por ventana (CPU de los procesos de cámara): {t_prep * 1000:.0f} ms")
print(f"Modelo: {vps:.1f} ventanas/s")
print(f"Cada cámara con movimiento genera {por_camara:.1f} ventanas/s\n")
print(f"→ Cámaras CON movimiento a la vez que soporta el modelo (con margen): ~{int(util / por_camara)}")
for pct in (0.3, 0.5):
    print(f"→ Total de cámaras si como máximo el {int(pct * 100)}% tiene movimiento a la vez: ~{int(util / por_camara / pct)}")
print("\nEl preprocesado y la lectura de video también usan CPU: vigila el uso al probar con las cámaras reales.")
