"""
Gestiona los usuarios del panel.
  python crear_usuario.py ana --rol admin        (pide la contraseña)
  python crear_usuario.py luis --rol revisor
  python crear_usuario.py --listar
  python crear_usuario.py luis --eliminar
Roles: admin (todo) | revisor (ver y etiquetar alertas, sin ajustes ni exportar).
"""
import argparse
import getpass
import sys

import usuarios

ap = argparse.ArgumentParser()
ap.add_argument("usuario", nargs="?")
ap.add_argument("--rol", choices=usuarios.ROLES, default="revisor")
ap.add_argument("--listar", action="store_true")
ap.add_argument("--eliminar", action="store_true")
a = ap.parse_args()

try:
    if a.listar:
        for u, v in usuarios.cargar().items():
            print(f"  {u:<20} {v['rol']}")
    elif not a.usuario:
        ap.print_help()
    elif a.eliminar:
        usuarios.eliminar(a.usuario)
        print("Usuario eliminado.")
    else:
        c1 = getpass.getpass("Contraseña (mínimo 10 caracteres): ")
        if c1 != getpass.getpass("Repite la contraseña: "):
            sys.exit("Las contraseñas no coinciden.")
        usuarios.crear(a.usuario, c1, a.rol)
        print(f"Usuario '{a.usuario}' guardado con rol {a.rol}.")
except ValueError as e:
    sys.exit(f"Error: {e}")
