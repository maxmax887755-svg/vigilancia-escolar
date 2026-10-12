"""
Detectores. La parte barata (preprocesado) corre en cada proceso de cámaras;
la parte pesada (modelo) corre una sola vez en el servidor de inferencia.
"""
import cv2
import numpy as np


def reducir_gris(frames, w=160, h=90):
    return np.stack([
        cv2.GaussianBlur(cv2.cvtColor(cv2.resize(f, (w, h)), cv2.COLOR_BGR2GRAY), (5, 5), 0)
        for f in frames
    ])


def movimiento(gris, k=8.0):
    """Fracción de píxeles con cambio fuerte, escalada a 0-1. Sirve de prefiltro."""
    if len(gris) < 2:
        return 0.0
    d = np.abs(np.diff(gris.astype(np.int16), axis=0)) > 25
    return float(min(1.0, d.mean() * k))


# ---- backend "movimiento" (SOLO PRUEBAS) ----
class PreprocesadorMovimiento:
    def __init__(self, cfg):
        pass

    def entrada(self, frames):
        return reducir_gris(frames)


class ModeloMovimiento:
    def __init__(self, cfg):
        self.k = cfg.get("sensibilidad_movimiento", 8.0)

    def inferir(self, lote):
        return [movimiento(x, self.k) for x in lote]


# ---- backend "onnx" (modelo real) ----
class PreprocesadorOnnx:
    def __init__(self, cfg):
        o = cfg.get("onnx", {})
        self.t, self.h, self.w = o.get("frames", 16), o.get("alto", 112), o.get("ancho", 112)

    def entrada(self, frames):
        ids = np.linspace(0, len(frames) - 1, self.t).astype(int)
        return np.stack([
            cv2.resize(cv2.cvtColor(frames[i], cv2.COLOR_BGR2RGB), (self.w, self.h)) for i in ids
        ])  # T,H,W,3 uint8 (liviano para enviar entre procesos)


class ModeloOnnx:
    def __init__(self, cfg):
        import onnxruntime as ort

        self.sesion = ort.InferenceSession(cfg["modelo_onnx"], providers=ort.get_available_providers())
        self.entrada = self.sesion.get_inputs()[0].name
        o = cfg.get("onnx", {})
        self.layout = o.get("layout", "NCTHW")
        self.idx = o.get("clase_violencia", 1)
        self.media = np.array(o.get("media", [0.43216, 0.394666, 0.37645]), np.float32)
        self.std = np.array(o.get("std", [0.22803, 0.22145, 0.216989]), np.float32)

    def _preparar(self, lote):
        x = (np.stack(lote).astype(np.float32) / 255.0 - self.media) / self.std  # B,T,H,W,C
        x = x.transpose(0, 4, 1, 2, 3) if self.layout == "NCTHW" else x.transpose(0, 1, 4, 2, 3)
        return np.ascontiguousarray(x, dtype=np.float32)

    def _puntajes(self, out):
        out = np.asarray(out)
        if out.ndim == 1:
            out = out[:, None]
        if out.shape[1] == 1:
            return (1 / (1 + np.exp(-out[:, 0]))).tolist()
        e = np.exp(out - out.max(1, keepdims=True))
        return (e / e.sum(1, keepdims=True))[:, self.idx].tolist()

    def inferir(self, lote):
        try:
            return self._puntajes(self.sesion.run(None, {self.entrada: self._preparar(lote)})[0])
        except Exception:
            if len(lote) == 1:
                raise
            return [self.inferir([x])[0] for x in lote]  # modelo de lote fijo = 1


def crear_preprocesador(cfg):
    return PreprocesadorOnnx(cfg) if cfg.get("backend") == "onnx" else PreprocesadorMovimiento(cfg)


def crear_modelo(cfg):
    return ModeloOnnx(cfg) if cfg.get("backend") == "onnx" else ModeloMovimiento(cfg)


def usa_servidor(cfg):
    modo = cfg.get("rendimiento", {}).get("inferencia", {}).get("en_servidor", "auto")
    if modo == "auto":
        return cfg["deteccion"].get("backend") == "onnx"
    return bool(modo)
