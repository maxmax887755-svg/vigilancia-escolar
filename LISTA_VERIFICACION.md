# Lista de verificación antes de activar el sistema

## Permisos y políticas
- [ ] Autorización de la dirección
- [ ] Aviso/consentimiento a las familias (según la ley de tu país)
- [ ] Cámaras solo en áreas comunes (nunca baños ni vestidores)
- [ ] Por escrito: quién recibe alertas, quién las revisa, cuánto tiempo se guardan los clips y quién puede verlos

## Instalación
- [ ] Equipo dedicado con UPS, arranque automático (servicio o Docker) y disco con espacio
- [ ] Cámaras en VLAN aislada, usuario de solo lectura, substream configurado
- [ ] `pip install -r requirements.txt`
- [ ] `python prueba_sistema.py` → ✅
- [ ] Bot de Telegram creado, `chat_id` de cada persona en `config.yaml`; `python main.py --probar` llega a todos
- [ ] `python main.py --verificar` → todas las cámaras ✅
- [ ] Usuarios del panel creados (`crear_usuario.py`), contraseñas de 10+ caracteres, panel no expuesto a internet

## Modelo y capacidad
- [ ] `modelos/violencia.onnx` generado (`entrenar_modelo.py`) y `backend: onnx`
- [ ] `python benchmark.py` en el equipo real; la pestaña Cámaras del panel sin descartes ni timeouts

## Piloto y calibración (1–2 semanas, `modo_calibracion: true`)
- [ ] Clips revisados en el panel (real / falsa alarma) y precisión observada anotada
- [ ] Umbral y `ventanas_consecutivas` ajustados; reentrenado con clips de la escuela si hace falta
- [ ] Ampliación por zonas, sin sobrecarga

## Prueba y activación
- [ ] Simulación actuada con el personal en cada zona; la alerta llega a tiempo
- [ ] Personal de guardia definido y sabe qué hacer ante una alerta
- [ ] `modo_calibracion: false`
- [ ] Mensaje "Sistema activo" llegando; revisión semanal de falsas alarmas, cámaras sin señal y disco
- [ ] Copias de seguridad de `config.yaml`, `usuarios.json`, `datos/eventos.db`, `modelos/`
