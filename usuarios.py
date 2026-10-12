"""Usuarios del panel: contraseñas con PBKDF2 (nunca en texto plano) y roles."""
import hashlib
import hmac
import json
import os
import re
import secrets

ARCHIVO = os.environ.get("VIGILANCIA_USUARIOS", "usuarios.json")
ITERACIONES = 200_000
ROLES = ("admin", "revisor")   # admin: todo | revisor: ver y etiquetar alertas
SAL_FALSA = b"0" * 16


def _hash(clave, sal):
    return hashlib.pbkdf2_hmac("sha256", clave.encode(), sal, ITERACIONES).hex()


def cargar():
    if not os.path.exists(ARCHIVO):
        return {}
    with open(ARCHIVO, encoding="utf-8") as f:
        return json.load(f)


def _guardar(d):
    tmp = ARCHIVO + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, ARCHIVO)


def crear(usuario, clave, rol):
    usuario = usuario.strip().lower()
    if not re.fullmatch(r"[a-z0-9._-]{3,32}", usuario):
        raise ValueError("Usuario: 3-32 caracteres (letras, números, . _ -)")
    if rol not in ROLES:
        raise ValueError(f"Rol inválido: {ROLES}")
    if len(clave) < 10:
        raise ValueError("La contraseña debe tener al menos 10 caracteres")
    d = cargar()
    sal = secrets.token_bytes(16)
    d[usuario] = {"sal": sal.hex(), "hash": _hash(clave, sal), "rol": rol}
    _guardar(d)


def eliminar(usuario):
    d = cargar()
    if usuario.strip().lower() not in d:
        raise ValueError("Ese usuario no existe")
    del d[usuario.strip().lower()]
    _guardar(d)


def verificar(usuario, clave):
    """Devuelve el rol si las credenciales son correctas; si no, None (tiempo similar)."""
    u = cargar().get(usuario.strip().lower())
    sal = bytes.fromhex(u["sal"]) if u else SAL_FALSA
    h = _hash(clave, sal)
    if u and hmac.compare_digest(h, u["hash"]):
        return u["rol"]
    return None
