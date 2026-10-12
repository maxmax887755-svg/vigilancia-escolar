"""
Entrena un clasificador de violencia (R3D-18 preentrenado en Kinetics-400) y lo exporta a ONNX.

Estructura de datos esperada:
  datos_entrenamiento/
    train/violencia/*.mp4      train/no_violencia/*.mp4
    val/violencia/*.mp4        val/no_violencia/*.mp4

Uso:
  pip install torch torchvision opencv-python numpy
  python entrenar_modelo.py --datos datos_entrenamiento --epocas 10

Resultado: modelos/violencia.onnx  (+ umbral sugerido en pantalla)
"""
import argparse
import glob
import os
import random

import cv2
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset
from torchvision.models.video import R3D_18_Weights, r3d_18

MEDIA = np.array([0.43216, 0.394666, 0.37645], np.float32)
STD = np.array([0.22803, 0.22145, 0.216989], np.float32)
T, S = 16, 112          # 16 cuadros de 112x112 (igual que en config.yaml)
VENTANA_SEG = 2.0       # igual que deteccion.ventana_seg


class Videos(Dataset):
    def __init__(self, raiz, entrenar):
        self.items, self.entrenar = [], entrenar
        for etiqueta, carpeta in enumerate(["no_violencia", "violencia"]):
            for ext in ("*.mp4", "*.avi", "*.mkv"):
                for r in glob.glob(os.path.join(raiz, carpeta, ext)):
                    self.items.append((r, etiqueta))
        print(f"{raiz}: {len(self.items)} videos")

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        ruta, y = self.items[i]
        cap = cv2.VideoCapture(ruta)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        frames = []
        while True:
            ok, f = cap.read()
            if not ok:
                break
            frames.append(f)
        cap.release()
        if len(frames) < 2:
            return self[random.randrange(len(self))]

        # ventana de 2 s (como en la inferencia), inicio aleatorio al entrenar
        n_vent = min(len(frames), max(2, int(fps * VENTANA_SEG)))
        ini = random.randint(0, len(frames) - n_vent) if self.entrenar else (len(frames) - n_vent) // 2
        ids = np.linspace(ini, ini + n_vent - 1, T).astype(int)

        flip = self.entrenar and random.random() < 0.5
        frac = random.uniform(0.85, 1.0) if self.entrenar else 1.0
        brillo = random.uniform(0.8, 1.2) if self.entrenar else 1.0
        h, w = frames[0].shape[:2]
        ch, cw = int(h * frac), int(w * frac)
        y0 = random.randint(0, h - ch) if self.entrenar else 0
        x0 = random.randint(0, w - cw) if self.entrenar else 0

        out = []
        for k in ids:
            f = frames[k][y0:y0 + ch, x0:x0 + cw]
            f = cv2.resize(f, (S, S))
            if flip:
                f = f[:, ::-1]
            f = cv2.cvtColor(np.ascontiguousarray(f), cv2.COLOR_BGR2RGB).astype(np.float32) / 255
            out.append(np.clip(f * brillo, 0, 1))
        x = (np.stack(out) - MEDIA) / STD                    # T,H,W,C
        return torch.from_numpy(x.transpose(3, 0, 1, 2).copy()), y


def evaluar(modelo, dl, dev):
    modelo.eval()
    probs, ys = [], []
    with torch.no_grad():
        for x, y in dl:
            p = torch.softmax(modelo(x.to(dev)), 1)[:, 1].cpu().numpy()
            probs += list(p)
            ys += list(y.numpy())
    return np.array(probs), np.array(ys)


def informe(probs, ys):
    print("\numbral | precisión | recall | falsas alarmas")
    mejor = None
    for u in np.arange(0.3, 0.96, 0.05):
        pred = probs >= u
        tp = int((pred & (ys == 1)).sum())
        fp = int((pred & (ys == 0)).sum())
        fn = int((~pred & (ys == 1)).sum())
        prec = tp / (tp + fp) if tp + fp else 0
        rec = tp / (tp + fn) if tp + fn else 0
        print(f"{u:.2f}   | {prec:.2f}      | {rec:.2f}   | {fp}")
        if prec >= 0.90 and (mejor is None or rec > mejor[1]):
            mejor = (u, rec)
    if mejor:
        print(f"\nUmbral sugerido (precisión >= 90%): {mejor[0]:.2f}  (recall {mejor[1]:.2f})")
    else:
        print("\nNingún umbral alcanza 90% de precisión: faltan datos o entrenamiento.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--datos", default="datos_entrenamiento")
    ap.add_argument("--epocas", type=int, default=10)
    ap.add_argument("--lote", type=int, default=8)
    ap.add_argument("--salida", default="modelos/violencia.onnx")
    a = ap.parse_args()

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    print("Dispositivo:", dev)
    tr = DataLoader(Videos(os.path.join(a.datos, "train"), True), a.lote, shuffle=True, num_workers=4)
    va = DataLoader(Videos(os.path.join(a.datos, "val"), False), a.lote, num_workers=4)

    modelo = r3d_18(weights=R3D_18_Weights.KINETICS400_V1)
    modelo.fc = nn.Linear(modelo.fc.in_features, 2)
    modelo.to(dev)
    opt = torch.optim.AdamW(modelo.parameters(), lr=1e-4, weight_decay=1e-2)
    perdida = nn.CrossEntropyLoss()

    mejor_acc, mejor_estado = 0, None
    for ep in range(a.epocas):
        modelo.train()
        total = 0
        for x, y in tr:
            opt.zero_grad()
            l = perdida(modelo(x.to(dev)), y.to(dev))
            l.backward()
            opt.step()
            total += l.item()
        probs, ys = evaluar(modelo, va, dev)
        acc = ((probs >= 0.5) == ys).mean()
        print(f"Época {ep + 1}/{a.epocas}  pérdida {total / len(tr):.3f}  val acc {acc:.3f}")
        if acc > mejor_acc:
            mejor_acc = acc
            mejor_estado = {k: v.cpu().clone() for k, v in modelo.state_dict().items()}

    modelo.load_state_dict(mejor_estado)
    probs, ys = evaluar(modelo, va, dev)
    informe(probs, ys)

    os.makedirs(os.path.dirname(a.salida) or ".", exist_ok=True)
    modelo.cpu().eval()
    torch.onnx.export(
        modelo, torch.randn(1, 3, T, S, S), a.salida,
        input_names=["video"], output_names=["logits"],
        dynamic_axes={"video": {0: "lote"}, "logits": {0: "lote"}}, opset_version=17,
    )
    print(f"\nModelo exportado en {a.salida}")
    print("En config.yaml: backend: onnx, alto: 112, ancho: 112, frames: 16, layout: NCTHW,")
    print("clase_violencia: 1, media: [0.43216, 0.394666, 0.37645], std: [0.22803, 0.22145, 0.216989]")


if __name__ == "__main__":
    main()
