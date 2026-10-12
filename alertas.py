import logging
import time

import requests

log = logging.getLogger("alertas")


class Telegram:
    def __init__(self, cfg):
        self.token = cfg.get("token")
        self.chats = [str(c) for c in cfg.get("chats", [])]
        if not self.token or not self.chats:
            log.warning("Telegram sin configurar: no se enviarán mensajes")

    def _post(self, metodo, chats=None, **kw):
        destinos = [str(c) for c in chats] if chats else self.chats
        if not self.token or not destinos:
            return False
        ok_total = True
        for chat in destinos:
            for intento in range(3):
                try:
                    kw_chat = dict(kw)
                    archivos = kw_chat.pop("files_fn", lambda: None)()
                    r = requests.post(
                        f"https://api.telegram.org/bot{self.token}/{metodo}",
                        data={**kw_chat, "chat_id": chat}, files=archivos, timeout=60,
                    )
                    if r.ok:
                        break
                    log.error("Telegram %s: %s", metodo, r.text[:200])
                except Exception as e:
                    log.error("Telegram error: %s", e)
                time.sleep(2 ** intento)
            else:
                ok_total = False
        return ok_total

    def aviso(self, texto, chats=None):
        return self._post("sendMessage", chats, text=texto)

    def alerta(self, foto_jpg, caption, ruta_clip=None, chats=None):
        ok = self._post("sendPhoto", chats, caption=caption,
                        files_fn=lambda: {"photo": ("alerta.jpg", foto_jpg)})
        if ruta_clip:
            self._post("sendVideo", chats, caption="Clip del evento",
                       files_fn=lambda: {"video": open(ruta_clip, "rb")})
        return ok
