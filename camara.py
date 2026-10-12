import threading
import time

import cv2


class Lector(threading.Thread):
    """Lee la cámara sin parar (vacía el buffer RTSP) y se reconecta sola."""

    def __init__(self, url):
        super().__init__(daemon=True)
        self.url = int(url) if str(url).isdigit() else url
        self.frame = None
        self.ts = 0.0
        self.lock = threading.Lock()

    def run(self):
        espera = 1
        while True:
            cap = cv2.VideoCapture(self.url)
            if not cap.isOpened():
                time.sleep(espera)
                espera = min(espera * 2, 30)
                continue
            espera = 1
            while True:
                ok, f = cap.read()
                if not ok:
                    break
                with self.lock:
                    self.frame, self.ts = f, time.time()
            cap.release()

    def ultimo(self):
        with self.lock:
            return self.frame, self.ts
