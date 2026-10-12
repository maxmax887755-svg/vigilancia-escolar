"""Proceso que vigila un GRUPO de cámaras (varias por proceso)."""
import logging
import queue
import threading
import time
from collections import deque
from datetime import datetime

import cv2

from alertas import Telegram
from camara import Lector
from detector import crear_preprocesador, movimiento, reducir_gris
from registro import Registro
from utilidades import configurar_logging, en_horario, escribir_estado

SIN_SENAL_SEG = 60
log = logging.getLogger("vigilante")


class Camara:
    def __init__(self, c, cfg):
        d, al, alm = cfg["deteccion"], cfg["alertas"], cfg["almacenamiento"]
        self.nombre, self.zona, self.chats = c["nombre"], c.get("zona", ""), c.get("chats")
        self.umbral = c.get("umbral", d["umbral"])
        self.horario = c.get("horario", al["horario"])
        self.req = d["ventanas_consecutivas"]
        self.enfr = al["enfriamiento_seg"]
        self.fps = d["fps_analisis"]
        self.n_vent = int(self.fps * d["ventana_seg"])
        self.n_pre = int(self.fps * alm["clip_previo_seg"])
        self.post = alm["clip_posterior_seg"]
        self.eval_cada = d["ventana_seg"] / 2
        self.res = tuple(d.get("resolucion", [640, 360]))
        self.prefiltro = d.get("prefiltro_movimiento", 0.03)
        self.k = d.get("sensibilidad_movimiento", 8.0)
        self.buf = deque(maxlen=max(self.n_vent, self.n_pre))
        self.evento = None
        self.consec, self.score = 0, 0.0
        self.ult_alerta = self.ult_eval = self.t_envio = 0.0
        self.pendiente = False
        self.offline, self.online, self.ultimo_ts = False, False, 0.0
        self.inicio = time.time()
        self.stats = {"evaluaciones": 0, "omitidas": 0, "descartes": 0, "timeouts": 0, "eventos": 0}
        self.lector = Lector(c["url"])
        self.lector.start()

    # ---- ciclo por cuadro
    def paso(self, ahora, ctx):
        if not en_horario(self.horario):
            self.buf.clear()
            self.consec, self.evento = 0, None
            _, ts = self.lector.ultimo()          # fuera de horario no se analiza, pero
            self.ultimo_ts = ts                   # el estado sigue reflejando si la cámara responde
            self.online = ts > 0 and ahora - ts <= SIN_SENAL_SEG
            return
        frame, ts = self.lector.ultimo()
        self.ultimo_ts = ts
        if frame is None or ahora - ts > SIN_SENAL_SEG:
            self.online = False
            if not self.offline and ahora - self.inicio > SIN_SENAL_SEG:
                self.offline = True
                ctx.off.append(self.nombre)
            return
        self.online = True
        if self.offline:
            self.offline = False
            ctx.ok.append(self.nombre)

        frame = cv2.resize(frame, self.res)
        self.buf.append(frame)
        if self.evento:
            self.evento["frames"].append(frame)

        if len(self.buf) >= self.n_vent and ahora - self.ult_eval >= self.eval_cada:
            if self.pendiente and ahora - self.t_envio > 10:
                self.pendiente = False
                self.stats["timeouts"] += 1
            if not self.pendiente:
                self.ult_eval = ahora
                ventana = list(self.buf)[-self.n_vent:]
                mov = movimiento(reducir_gris(ventana), self.k)
                if ctx.cola_in is None:                    # detector local
                    self.resultado(mov, ahora, ctx)
                elif mov < self.prefiltro:                 # escena casi quieta: no gastar modelo
                    self.stats["omitidas"] += 1
                    self.resultado(0.0, ahora, ctx)
                else:
                    item = {"grupo": ctx.grupo, "cam": self.nombre, "t": time.time(),
                            "x": ctx.prep.entrada(ventana)}
                    try:
                        ctx.cola_in.put_nowait(item)
                        self.pendiente, self.t_envio = True, ahora
                    except queue.Full:
                        self.stats["descartes"] += 1

        if self.evento and ahora >= self.evento["fin"]:
            threading.Thread(target=ctx.cerrar, args=(self, self.evento), daemon=True).start()
            self.evento, self.consec, self.ult_alerta = None, 0, ahora

    def resultado(self, score, ahora, ctx):
        self.pendiente = False
        if score is None:
            return
        self.score = score
        self.stats["evaluaciones"] += 1
        self.consec = self.consec + 1 if score >= self.umbral else 0
        if self.evento:
            self.evento["score"] = max(self.evento["score"], score)
        elif self.consec >= self.req and ahora - self.ult_alerta >= self.enfr and self.buf:
            foto = self.buf[-1].copy()
            gris = cv2.cvtColor(foto, cv2.COLOR_BGR2GRAY)
            for (x, y, w, h) in ctx.caras.detectMultiScale(gris, 1.1, 5):
                cv2.rectangle(foto, (x, y), (x + w, y + h), (0, 0, 255), 2)
            _, jpg = cv2.imencode(".jpg", foto)
            self.stats["eventos"] += 1
            self.evento = {
                "frames": list(self.buf)[-self.n_pre:], "score": score, "foto": jpg.tobytes(),
                "hora": datetime.now().strftime("%H:%M:%S"), "fin": ahora + self.post,
            }


class Contexto:
    pass


def vigilar_grupo(grupo, cams_cfg, cfg, cola_in, cola_out):
    d, al, alm = cfg["deteccion"], cfg["alertas"], cfg["almacenamiento"]
    configurar_logging(alm["carpeta"], f"grupo{grupo}")
    ctx = Contexto()
    ctx.grupo, ctx.cola_in = grupo, cola_in
    ctx.prep = crear_preprocesador(d)
    ctx.caras = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    ctx.off, ctx.ok = [], []
    tg, reg = Telegram(cfg["telegram"]), Registro(alm)

    def cerrar(cam, ev):
        try:
            ruta = reg.guardar_clip(cam.nombre, ev["frames"], cam.fps)
            enviado = False
            if not al["modo_calibracion"]:
                lugar = f"{cam.zona} – {cam.nombre}" if cam.zona else cam.nombre
                cap = (f"⚠️ {lugar}: posible violencia (confianza {ev['score']:.0%}) a las "
                       f"{ev['hora']}. Requiere revisión humana antes de actuar.")
                enviado = tg.alerta(ev["foto"], cap, ruta, cam.chats)
            reg.registrar(cam.nombre, cam.zona, ev["score"], enviado, ruta)
            log.info("[%s] evento %.2f enviado=%s", cam.nombre, ev["score"], enviado)
        except Exception:
            log.exception("Error cerrando evento de %s", cam.nombre)

    ctx.cerrar = cerrar
    camaras = [Camara(c, cfg) for c in cams_cfg]
    por_nombre = {c.nombre: c for c in camaras}
    log.info("Grupo %d vigilando %d cámaras (%s)", grupo, len(camaras), d["backend"])

    paso = 1.0 / d["fps_analisis"]
    siguiente = time.time()
    ult_estado, ult_aviso = 0.0, time.time()
    while True:
        siguiente += paso
        time.sleep(max(0, siguiente - time.time()))
        if siguiente < time.time() - 1:
            siguiente = time.time()
        ahora = time.time()

        if cola_out is not None:
            while True:
                try:
                    r = cola_out.get_nowait()
                except queue.Empty:
                    break
                c = por_nombre.get(r["cam"])
                if c:
                    c.resultado(r["score"], ahora, ctx)

        for c in camaras:
            try:
                c.paso(ahora, ctx)
            except Exception:
                log.exception("Error en cámara %s", c.nombre)
                time.sleep(0.2)

        if ahora - ult_aviso >= 20:   # avisos agrupados: un mensaje, no uno por cámara
            ult_aviso = ahora
            if ctx.off:
                threading.Thread(target=tg.aviso, daemon=True, args=(
                    "📷 SIN SEÑAL: " + ", ".join(ctx.off) + ". Revisar conexión.",)).start()
                ctx.off = []
            if ctx.ok:
                threading.Thread(target=tg.aviso, daemon=True, args=(
                    "✅ Señal recuperada: " + ", ".join(ctx.ok),)).start()
                ctx.ok = []

        if ahora - ult_estado >= 10:
            ult_estado = ahora
            for c in camaras:
                escribir_estado(alm["carpeta"], c.nombre, {
                    "nombre": c.nombre, "zona": c.zona, "grupo": grupo, "online": c.online,
                    "ultimo_frame": c.ultimo_ts, "score": round(c.score, 3), **c.stats,
                })
