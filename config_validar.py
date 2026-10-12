import os
from datetime import datetime


def _hora_ok(s):
    try:
        datetime.strptime(str(s), "%H:%M")
        return True
    except ValueError:
        return False


def validar(cfg):
    """Devuelve (errores, avisos). Con errores el sistema no arranca."""
    e, a = [], []
    d, al = cfg.get("deteccion", {}), cfg.get("alertas", {})
    calib = al.get("modo_calibracion", True)

    cams = [c for c in cfg.get("camaras", []) if c.get("activa", True)]
    if not cams:
        e.append("No hay cámaras activas en 'camaras'.")
    nombres = set()
    for c in cams:
        n, url = c.get("nombre"), str(c.get("url", "")).strip()
        if not n:
            e.append("Hay una cámara sin 'nombre'.")
        elif n in nombres:
            e.append(f"Nombre de cámara repetido: {n}")
        nombres.add(n)
        if not url or "usuario:clave" in url:
            e.append(f"Cámara '{n}': falta la URL real (tiene el valor de ejemplo).")
        if "umbral" in c and not 0 < c["umbral"] <= 1:
            e.append(f"Cámara '{n}': umbral fuera de rango (0-1].")

    tg = cfg.get("telegram", {})
    if not tg.get("token") or "TU_TOKEN" in str(tg.get("token")) or not tg.get("chats"):
        (a if calib else e).append("Telegram sin configurar (token y chats).")

    if d.get("backend") not in ("movimiento", "onnx"):
        e.append("deteccion.backend debe ser 'movimiento' u 'onnx'.")
    if d.get("backend") == "onnx" and not os.path.exists(d.get("modelo_onnx", "")):
        e.append(f"No existe el modelo ONNX: {d.get('modelo_onnx')}")
    if d.get("backend") == "movimiento" and not calib and not d.get("permitir_detector_de_prueba"):
        e.append("El detector 'movimiento' es solo de pruebas y genera muchas falsas alarmas. "
                 "Usa un modelo ONNX, activa modo_calibracion, o pon "
                 "deteccion.permitir_detector_de_prueba: true (solo para probar).")
    if not 0 < d.get("umbral", 0) <= 1:
        e.append("deteccion.umbral debe estar entre 0 y 1.")
    if not 1 <= d.get("fps_analisis", 0) <= 30:
        e.append("deteccion.fps_analisis debe estar entre 1 y 30.")
    if d.get("ventana_seg", 0) < 1:
        e.append("deteccion.ventana_seg debe ser >= 1.")

    for h in [al.get("horario", {})] + [c.get("horario", {}) for c in cams if "horario" in c]:
        if not (_hora_ok(h.get("inicio")) and _hora_ok(h.get("fin"))):
            e.append("Horario inválido: usa formato HH:MM en 'inicio' y 'fin'.")
    if calib:
        a.append("MODO CALIBRACIÓN: se registran eventos pero NO se envían alertas.")
    if d.get("backend") == "movimiento":
        a.append("Detector de PRUEBA (movimiento): no usar como protección real.")
    return e, a
