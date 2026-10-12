# Sistema de detección de violencia física – Escuela

Vigila varias cámaras IP, detecta posibles peleas/agresiones físicas y avisa por Telegram con foto
(caras marcadas) y clip. Incluye un panel web con usuarios, revisión de alertas y estado de cámaras.
**No** detecta bullying verbal, **no** identifica alumnos y siempre requiere revisión humana.

## Inicio rápido
```
pip install -r requirements.txt
python crear_usuario.py tunombre --rol admin     # usuarios del panel
# edita config.yaml: cámaras (URL de cada substream), token y chats de Telegram
python prueba_sistema.py                         # prueba sin cámaras (~45 s)
python main.py --probar                          # mensaje de prueba a Telegram
python main.py --verificar                       # prueba cada cámara y guarda una foto
python main.py                                   # arranca el sistema (en modo calibración)
streamlit run panel.py --server.address 127.0.0.1   # panel (otra terminal)
```
Telegram no permite escribir a un número de teléfono: crea un bot con @BotFather, cada persona le
escribe al bot y se usa su `chat_id` (por ejemplo con @userinfobot).

## Archivos
| Archivo | Para qué sirve |
|---|---|
| `main.py` | Arranque, vigilancia de procesos, avisos de sistema |
| `vigilante.py`, `camara.py` | Lectura y análisis de cámaras por grupos |
| `servidor_inferencia.py`, `detector.py` | Modelo compartido por todas las cámaras |
| `config.yaml`, `config_validar.py` | Configuración y validación al arrancar |
| `panel.py`, `usuarios.py`, `crear_usuario.py` | Panel con usuarios y roles |
| `entrenar_modelo.py` | Entrena y exporta el modelo ONNX |
| `benchmark.py`, `prueba_sistema.py` | Capacidad del equipo y prueba de instalación |
| `docs/DESPLIEGUE.md` | Guía para instalar en una escuela |
| `LISTA_VERIFICACION.md` | Pasos antes de activarlo |

## Importante
- El detector `movimiento` es **solo para pruebas** (confunde juegos con peleas). Para uso real
  entrena o consigue un modelo ONNX (`entrenar_modelo.py`) y pon `backend: onnx`.
- Empieza siempre en `modo_calibracion: true` (graba y registra, no envía) y revisa los clips en el panel.
- Autorización de la dirección, aviso a las familias, cámaras solo en áreas comunes.
- Despliegue completo, red, servicios, Docker y operación: `docs/DESPLIEGUE.md`.
