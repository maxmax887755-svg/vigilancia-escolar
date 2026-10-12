"""
Panel de control (Streamlit) con usuarios y roles.

  python crear_usuario.py ana --rol admin        (primero crea al menos un usuario)
  streamlit run panel.py --server.address 127.0.0.1

Roles: admin (todo) | revisor (ver y etiquetar alertas, estado de cámaras).
"""
import os
import random
import shutil
import time
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

import usuarios
from config_editor import editar_config
from registro import abrir_db
from utilidades import cargar_config_cruda, leer_estados

st.set_page_config(page_title="Vigilancia escolar", page_icon="🛡️", layout="wide")

TIEMPO_SESION = 30 * 60               # cierre por inactividad
MAX_INTENTOS, BLOQUEO = 5, 300        # por usuario: 5 fallos -> 5 min
MAX_FALLOS_GLOBAL = 25                # en total en 5 min -> se bloquean todos los intentos

cfg = cargar_config_cruda()
CARPETA = cfg["almacenamiento"]["carpeta"]
DB = os.path.join(CARPETA, "eventos.db")
CLIPS = os.path.join(CARPETA, "clips")
os.makedirs(CLIPS, exist_ok=True)


# ---------------------------------------------------------------- seguridad
@st.cache_resource
def fallos():
    return {"por_usuario": {}, "global": []}


def anotar(texto):
    quien = st.session_state.get("usuario", "-")
    with open(os.path.join(CARPETA, "panel_accesos.log"), "a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} [{quien}] {texto}\n")


def login():
    ahora = time.time()
    if st.session_state.get("rol") and ahora - st.session_state.get("ult", 0) < TIEMPO_SESION:
        st.session_state["ult"] = ahora
        return
    st.session_state.pop("rol", None)
    st.title("🛡️ Vigilancia escolar")
    if not usuarios.cargar():
        st.error("No hay usuarios. Crea el primero en la terminal:\n\n"
                 "`python crear_usuario.py tunombre --rol admin`")
        st.stop()
    f = fallos()
    f["global"] = [t for t in f["global"] if ahora - t < 300]
    if len(f["global"]) >= MAX_FALLOS_GLOBAL:
        st.error("Demasiados intentos fallidos. Espera unos minutos.")
        st.stop()
    with st.form("login"):
        u = st.text_input("Usuario").strip().lower()
        c = st.text_input("Contraseña", type="password")
        enviar = st.form_submit_button("Entrar")
    if enviar:
        est = f["por_usuario"].setdefault(u, {"n": 0, "hasta": 0.0})
        if ahora < est["hasta"]:
            st.error(f"Usuario bloqueado. Espera {int(est['hasta'] - ahora)} s.")
            st.stop()
        rol = usuarios.verificar(u, c)
        if rol:
            est["n"] = 0
            st.session_state.update(usuario=u, rol=rol, ult=ahora)
            anotar("ACCESO CORRECTO")
            st.rerun()
        est["n"] += 1
        f["global"].append(ahora)
        st.session_state["usuario"] = u or "-"
        anotar("INTENTO FALLIDO")
        st.session_state.pop("usuario", None)
        if est["n"] >= MAX_INTENTOS:
            est["hasta"], est["n"] = ahora + BLOQUEO, 0
        st.error("Usuario o contraseña incorrectos")
    st.stop()


login()
ES_ADMIN = st.session_state["rol"] == "admin"


# ------------------------------------------------------------------- datos
def cargar_eventos():
    with abrir_db(DB) as c:
        df = pd.read_sql("SELECT * FROM eventos ORDER BY ts DESC", c)
    df["ts"] = pd.to_datetime(df["ts"])
    df["zona"] = df["zona"].fillna("")
    return df


def etiquetar(id_, valor):
    with abrir_db(DB) as c:
        c.execute("UPDATE eventos SET etiqueta=?, etiqueta_por=? WHERE id=?",
                  (valor, st.session_state["usuario"] if valor else None, id_))
    anotar(f"Evento {id_} etiquetado: {valor}")


def ruta_segura(ruta):
    """Solo permite abrir archivos dentro de la carpeta de clips."""
    if not ruta:
        return None
    real = os.path.realpath(ruta)
    if real.startswith(os.path.realpath(CLIPS) + os.sep) and os.path.exists(real):
        return real
    return None


# ----------------------------------------------------------------- interfaz
st.sidebar.title("🛡️ Vigilancia escolar")
st.sidebar.write(f"👤 **{st.session_state['usuario']}** ({st.session_state['rol']})")
if cfg["alertas"]["modo_calibracion"]:
    st.sidebar.warning("Modo calibración: NO se envían alertas")
else:
    st.sidebar.success("Modo activo")
if st.sidebar.button("Cerrar sesión"):
    anotar("Sesión cerrada")
    for k in ("rol", "usuario"):
        st.session_state.pop(k, None)
    st.rerun()

df = cargar_eventos()
st.sidebar.subheader("Filtros")
desde = st.sidebar.date_input("Desde", date.today() - timedelta(days=7))
hasta = st.sidebar.date_input("Hasta", date.today())
zonas = sorted(z for z in df["zona"].unique() if z)
sel_zona = st.sidebar.multiselect("Zonas", zonas, default=zonas)
camaras = sorted(df[df["zona"].isin(sel_zona) | (df["zona"] == "")]["camara"].unique())
sel_cam = st.sidebar.multiselect("Cámaras", camaras, default=camaras)
sel_et = st.sidebar.selectbox("Revisión", ["Todos", "Sin revisar", "Pelea real", "Falsa alarma"])

f = df[(df["ts"].dt.date >= desde) & (df["ts"].dt.date <= hasta) & df["camara"].isin(sel_cam)]
if sel_et == "Sin revisar":
    f = f[f["etiqueta"].isna()]
elif sel_et == "Pelea real":
    f = f[f["etiqueta"] == "real"]
elif sel_et == "Falsa alarma":
    f = f[f["etiqueta"] == "falsa"]

nombres = ["📋 Alertas", "📊 Estadísticas", "📷 Cámaras"]
if ES_ADMIN:
    nombres += ["🧠 Reentrenamiento", "⚙️ Ajustes"]
tabs = st.tabs(nombres)

# ---- Alertas
with tabs[0]:
    if f.empty:
        st.info("No hay eventos con esos filtros.")
    else:
        sin_rev = int(f["etiqueta"].isna().sum())
        st.caption(f"{len(f)} eventos, {sin_rev} sin revisar. Cada evento debe revisarlo una persona.")
        opciones = {
            int(r.id): f"{r.ts:%d/%m %H:%M:%S} · {r.camara} · {r.puntaje:.0%}"
            f" · {'✅ real' if r.etiqueta == 'real' else '❌ falsa' if r.etiqueta == 'falsa' else '⏳ sin revisar'}"
            for r in f.itertuples()
        }
        id_sel = st.selectbox("Evento", list(opciones), format_func=lambda i: opciones[i])
        ev = f[f["id"] == id_sel].iloc[0]
        c1, c2 = st.columns([2, 1])
        with c1:
            ruta = ruta_segura(ev["clip"])
            if ruta:
                with open(ruta, "rb") as fh:
                    datos = fh.read()
                st.video(datos)
                st.download_button("Descargar clip", datos, file_name=os.path.basename(ruta), mime="video/mp4")
                st.caption("Si no se reproduce en el navegador, descárgalo y ábrelo con VLC.")
            else:
                st.warning("El clip ya no existe (borrado por retención) o la ruta no es válida.")
        with c2:
            st.metric("Confianza del modelo", f"{ev['puntaje']:.0%}")
            st.write(f"**Cámara:** {ev['camara']}" + (f" ({ev['zona']})" if ev["zona"] else ""))
            st.write(f"**Alerta enviada:** {'Sí' if ev['enviado'] else 'No (calibración)'}")
            if ev["etiqueta"]:
                st.write(f"**Revisado por:** {ev['etiqueta_por'] or '-'}")
            if st.button("✅ Pelea real", use_container_width=True):
                etiquetar(int(id_sel), "real")
                st.rerun()
            if st.button("❌ Falsa alarma", use_container_width=True):
                etiquetar(int(id_sel), "falsa")
                st.rerun()
            if st.button("↩️ Quitar etiqueta", use_container_width=True):
                etiquetar(int(id_sel), None)
                st.rerun()
        st.dataframe(
            f[["ts", "zona", "camara", "puntaje", "enviado", "etiqueta", "etiqueta_por"]].rename(columns={
                "ts": "Fecha", "zona": "Zona", "camara": "Cámara", "puntaje": "Confianza",
                "enviado": "Enviada", "etiqueta": "Revisión", "etiqueta_por": "Revisó"}),
            use_container_width=True, hide_index=True)

# ---- Estadísticas
with tabs[1]:
    if f.empty:
        st.info("Sin datos para mostrar.")
    else:
        rev = f.dropna(subset=["etiqueta"])
        reales, falsas = int((rev["etiqueta"] == "real").sum()), int((rev["etiqueta"] == "falsa").sum())
        a, b, c, d = st.columns(4)
        a.metric("Eventos", len(f))
        b.metric("Revisados", len(rev))
        c.metric("Peleas reales", reales)
        d.metric("Falsas alarmas", falsas)
        if reales + falsas:
            st.metric("Precisión observada", f"{reales / (reales + falsas):.0%}",
                      help="Porcentaje de alertas revisadas que eran peleas reales")
        st.subheader("Por zona")
        st.bar_chart(f["zona"].replace("", "(sin zona)").value_counts())
        st.subheader("Cámaras con más eventos")
        st.bar_chart(f["camara"].value_counts().head(15))
        st.subheader("Por hora del día")
        st.bar_chart(f["ts"].dt.hour.value_counts().sort_index())
        st.subheader("Por día")
        st.bar_chart(f.groupby(f["ts"].dt.date).size())

# ---- Estado de cámaras
with tabs[2]:
    est = leer_estados(CARPETA)
    if not est:
        st.warning("No hay reportes de estado. ¿Está corriendo `main.py`?")
    else:
        ahora = time.time()
        ult = max(e["actualizado"] for e in est)
        if ahora - ult > 60:
            st.error(f"⚠️ El sistema no reporta hace {int((ahora - ult) / 60)} min. Puede estar caído.")
        else:
            st.success("🟢 Sistema activo")
        filas = []
        for e in est:
            sin_reporte = ahora - e["actualizado"] > 60
            filas.append({
                "Estado": "❔ sin reporte" if sin_reporte else ("🟢 en línea" if e["online"] else "🔴 sin señal"),
                "Cámara": e["nombre"], "Zona": e.get("zona", ""),
                "Último cuadro hace (s)": int(ahora - e["ultimo_frame"]) if e.get("ultimo_frame") else None,
                "Puntaje actual": e.get("score"), "Eventos": e.get("eventos", 0),
                "Omitidas (sin movimiento)": e.get("omitidas", 0),
                "Descartes (sobrecarga)": e.get("descartes", 0), "Timeouts": e.get("timeouts", 0),
            })
        tabla = pd.DataFrame(filas).sort_values(["Estado", "Cámara"])
        en_linea = sum(1 for x in filas if x["Estado"].startswith("🟢"))
        m1, m2, m3 = st.columns(3)
        m1.metric("Cámaras", len(filas))
        m2.metric("En línea", en_linea)
        m3.metric("Sin señal / sin reporte", len(filas) - en_linea)
        if (tabla["Descartes (sobrecarga)"] > 0).any() or (tabla["Timeouts"] > 0).any():
            st.warning("Hay descartes o timeouts: el equipo no da abasto. Reduce `fps_analisis`, usa el "
                       "substream, sube `prefiltro_movimiento` o añade GPU (ver docs/DESPLIEGUE.md).")
        st.dataframe(tabla, use_container_width=True, hide_index=True)
        st.caption("Se actualiza al recargar la página.")

if ES_ADMIN:
    # ---- Reentrenamiento
    with tabs[3]:
        et = df.dropna(subset=["etiqueta"])
        n_real, n_falsa = int((et["etiqueta"] == "real").sum()), int((et["etiqueta"] == "falsa").sum())
        st.write(f"Clips etiquetados: **{n_real} peleas reales** y **{n_falsa} falsas alarmas**.")
        st.write("Copia los clips etiquetados a `datos_entrenamiento/` (80% train, 20% val) para `entrenar_modelo.py`.")
        st.warning("Usa estos clips solo con autorización de la dirección y según la política de privacidad.")
        if st.button("Exportar clips etiquetados"):
            random.seed(42)
            copiados = 0
            for r in et.itertuples():
                ruta = ruta_segura(r.clip)
                if not ruta:
                    continue
                clase = "violencia" if r.etiqueta == "real" else "no_violencia"
                destino = os.path.join("datos_entrenamiento", "val" if random.random() < 0.2 else "train", clase)
                os.makedirs(destino, exist_ok=True)
                archivo = os.path.join(destino, os.path.basename(ruta))
                if not os.path.exists(archivo):
                    shutil.copy2(ruta, archivo)
                    copiados += 1
            anotar(f"Exportados {copiados} clips para entrenamiento")
            st.success(f"{copiados} clips copiados a datos_entrenamiento/")

    # ---- Ajustes
    with tabs[4]:
        st.write("Los cambios se guardan en `config.yaml` (se conservan los comentarios y se hace copia de "
                 "seguridad). **Reinicia `main.py` para aplicarlos.** Las cámaras se editan en el archivo.")
        d, al, alm = cfg["deteccion"], cfg["alertas"], cfg["almacenamiento"]
        with st.form("ajustes"):
            umbral = st.slider("Umbral de detección", 0.30, 0.99, float(d["umbral"]), 0.01,
                               help="Más alto = menos falsas alarmas, pero puede perder peleas")
            consec = st.number_input("Ventanas consecutivas", 1, 10, int(d["ventanas_consecutivas"]))
            calib = st.checkbox("Modo calibración (no enviar alertas)", al["modo_calibracion"])
            enfr = st.number_input("Segundos entre alertas de una cámara", 10, 3600, int(al["enfriamiento_seg"]))
            h1 = st.text_input("Hora de inicio (HH:MM)", al["horario"]["inicio"])
            h2 = st.text_input("Hora de fin (HH:MM)", al["horario"]["fin"])
            nombres_dias = {1: "Lun", 2: "Mar", 3: "Mié", 4: "Jue", 5: "Vie", 6: "Sáb", 7: "Dom"}
            dias = st.multiselect("Días activos", list(nombres_dias), default=al["horario"].get("dias", [1, 2, 3, 4, 5]),
                                  format_func=lambda i: nombres_dias[i])
            ret = st.number_input("Días de retención de clips", 1, 90, int(alm["retencion_dias"]))
            tope = st.number_input("Tope de espacio para clips (GB)", 1, 2000, int(alm.get("max_gb", 20)))
            guardar = st.form_submit_button("Guardar ajustes")
        if guardar:
            try:
                horario = '{ inicio: "%s", fin: "%s", dias: [%s] }' % (h1, h2, ", ".join(str(x) for x in sorted(dias)))
                editar_config({
                    ("deteccion", "umbral"): float(umbral),
                    ("deteccion", "ventanas_consecutivas"): int(consec),
                    ("alertas", "modo_calibracion"): str(bool(calib)).lower(),
                    ("alertas", "enfriamiento_seg"): int(enfr),
                    ("alertas", "horario"): horario,
                    ("almacenamiento", "retencion_dias"): int(ret),
                    ("almacenamiento", "max_gb"): int(tope),
                })
                anotar("Ajustes modificados")
                st.success("Guardado. Reinicia main.py para aplicar los cambios.")
            except Exception as e:
                st.error(f"No se guardó: {e}")
