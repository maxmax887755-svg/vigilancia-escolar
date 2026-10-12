# Guía de despliegue en una escuela con muchas cámaras

## 1. Arquitectura (cómo escala)
- Cada **proceso de cámaras** vigila un grupo (`rendimiento.camaras_por_proceso`, por defecto 6):
  lee los streams, descarta escenas sin movimiento (`prefiltro_movimiento`) y manda solo las
  ventanas con movimiento al modelo.
- Un **servidor de inferencia único** carga el modelo una sola vez y atiende a todos los grupos
  por lotes (con GPU si hay).
- Si un grupo se cuelga o cae, `main.py` lo reinicia y avisa por Telegram. Los estados de las
  cámaras se ven en la pestaña **Cámaras** del panel.

## 2. Dimensionar el equipo
1. Pon `backend: onnx` con tu modelo y ejecuta `python benchmark.py` en el equipo real.
2. Estimación orientativa (confírmala en la pestaña Cámaras): decodificar video también gasta CPU;
   usa siempre el **substream** (≤ 640x360) y 5–8 fps de análisis.
3. Señales de que falta capacidad: *Descartes* o *Timeouts* > 0 en el panel. Soluciones: bajar
   `fps_analisis`, subir `prefiltro_movimiento`, más `camaras_por_proceso` en más núcleos, o una GPU
   (instala `onnxruntime-gpu` en lugar de `onnxruntime`).
4. Equipo dedicado, con SAI/UPS, disco con espacio para `max_gb` de clips y, si es posible, cifrado de disco.

## 3. Red y cámaras
- Cámaras y servidor en una **VLAN aislada**, sin acceso a internet para las cámaras. Solo el servidor
  sale a internet (Telegram).
- Crea en cada cámara un usuario **de solo lectura** para el sistema. IP fija o reservada por DHCP.
- Usa el substream RTSP. Comprueba todas con `python main.py --verificar` (guarda una foto de cada una).
- Cámaras solo en áreas comunes. Nunca baños ni vestidores.

## 4. Instalación
```
python -m venv venv && source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp config.yaml config.local.yaml    # edita cámaras, token y chats (opcional: VIGILANCIA_CONFIG=ruta)
python crear_usuario.py direccion --rol admin
python crear_usuario.py guardia1 --rol revisor
python prueba_sistema.py             # prueba de humo con cámaras simuladas
python main.py --probar              # llega un mensaje de Telegram
python main.py --verificar           # todas las cámaras responden
```

### Como servicio (arranque automático)
**Linux (systemd)** — `/etc/systemd/system/vigilancia.service`:
```
[Unit]
Description=Vigilancia escolar
After=network-online.target
[Service]
User=vigilancia
WorkingDirectory=/opt/vigilancia_escolar
EnvironmentFile=/etc/vigilancia.env       # TELEGRAM_TOKEN=...
ExecStart=/opt/vigilancia_escolar/venv/bin/python main.py
Restart=always
RestartSec=10
[Install]
WantedBy=multi-user.target
```
Otro servicio igual para el panel con
`ExecStart=/opt/vigilancia_escolar/venv/bin/streamlit run panel.py --server.address 127.0.0.1`.
Luego: `sudo systemctl enable --now vigilancia`.

**Windows**: con NSSM, `nssm install VigilanciaEscolar C:\ruta\venv\Scripts\python.exe main.py`
(directorio de inicio = la carpeta del proyecto) y lo mismo para el panel.

**Docker**: `docker compose up -d --build` (ver `docker-compose.yml`).

## 5. Despliegue por fases (recomendado)
1. **Semana 0:** instalación, `prueba_sistema.py`, `--verificar`, simulacro de Telegram.
2. **Piloto (1–2 semanas):** 2–4 cámaras, `modo_calibracion: true`. El personal etiqueta cada
   clip en el panel (real / falsa alarma). Ajusta `umbral` y `ventanas_consecutivas`.
3. **Ampliación:** añade cámaras por zonas, 1/3 cada vez, vigilando la pestaña Cámaras.
4. **Activación:** `modo_calibracion: false` solo cuando la precisión observada sea aceptable
   para la dirección y haya personal asignado a revisar cada alerta.
5. **Reentrenamiento** con los clips etiquetados de la escuela (pestaña Reentrenamiento).

## 6. Operación
- **Cada día:** llega el mensaje "Sistema activo" (cada `heartbeat_horas`). Si no llega, el sistema cayó.
- **Cada semana:** revisar falsas alarmas, cámaras sin señal y espacio en disco.
- **Copias de seguridad:** `config.yaml`, `usuarios.json`, `datos/eventos.db` y `modelos/`.
- **Logs:** `datos/logs/` (rotan solos). Accesos al panel: `datos/panel_accesos.log`.
- **Cambios:** edita ajustes desde el panel (admin) y reinicia `main.py`. Cada cambio deja una copia `.bak`.

## 7. Seguridad y privacidad
- Contraseñas de panel de 10+ caracteres, un usuario por persona, rol *revisor* para guardias.
- El panel **no se expone a internet**. Para verlo desde otras PCs: proxy con HTTPS o VPN.
- Token de Telegram en la variable `TELEGRAM_TOKEN`, no en el archivo.
- Retención corta (`retencion_dias`), tope de disco (`max_gb`) y acceso limitado a `datos/`.
- Define por escrito: quién recibe alertas, quién revisa, cuánto se guardan los clips y quién
  puede verlos. Informa a las familias según la ley local.

## 8. Alcance y límites
Detecta **violencia física** y avisa; no detecta bullying verbal ni acoso, no identifica
alumnos y no sustituye la supervisión del personal. Tendrá falsas alarmas y puede no detectar
peleas. Su fiabilidad depende del modelo y de las cámaras de tu escuela: **mídela en el piloto
antes de depender de ella.**
