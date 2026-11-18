"""Regiones ya descargadas: lista las de la carpeta cache y guarda nombres puestos por la gente."""
import glob
import json
import os
import re

ARCHIVO = "regiones.json"
MAX_REGIONES = 200
MAX_NOMBRE = 40
_PATRON = re.compile(r"obs_(-?\d+\.\d+)_(-?\d+\.\d+)_(\d+\.\d+)_(D[1-6])_\d+\.json$")


def _clave(ra, dec, tam, banda):
    return (round(float(ra), 4), round(float(dec), 4), round(float(tam), 3), banda)


def _leer_registro(carpeta):
    try:
        with open(os.path.join(carpeta, ARCHIVO), encoding="utf-8") as f:
            datos = json.load(f)
        return [r for r in datos if isinstance(r, dict)]
    except (OSError, ValueError):
        return []


def limpiar_nombre(nombre):
    """Quita espacios de más y recorta; devuelve '' si no queda nada."""
    return " ".join(str(nombre).split())[:MAX_NOMBRE]


def listar_regiones(carpeta="cache"):
    """Regiones guardadas con nombre + las que se deducen de las consultas ya hechas a IRSA."""
    regiones, vistas = [], set()
    for r in _leer_registro(carpeta):
        try:
            clave = _clave(r["ra"], r["dec"], r["tam"], r["banda"])
            regiones.append({"nombre": limpiar_nombre(r.get("nombre", "")), "ra": float(r["ra"]),
                             "dec": float(r["dec"]), "tam": float(r["tam"]), "banda": r["banda"]})
        except (KeyError, TypeError, ValueError):
            continue
        vistas.add(clave)
    for ruta in sorted(glob.glob(os.path.join(carpeta, "obs_*.json"))):
        m = _PATRON.search(os.path.basename(ruta))
        if not m:
            continue
        ra, dec, tam, banda = float(m[1]), float(m[2]), float(m[3]), m[4]
        if _clave(ra, dec, tam, banda) not in vistas:
            vistas.add(_clave(ra, dec, tam, banda))
            regiones.append({"nombre": "", "ra": ra, "dec": dec, "tam": tam, "banda": banda})
    return regiones


def etiqueta(r):
    coords = f"RA {r['ra']:.3f}, Dec {r['dec']:.3f}, {r['tam']:g}°, {r['banda']}"
    return f"{r['nombre']} ({coords})" if r["nombre"] else coords


def guardar_region(nombre, ra, dec, tam, banda, carpeta="cache"):
    """Guarda (o renombra) una región. Devuelve True si se guardó."""
    nombre = limpiar_nombre(nombre)
    if not nombre:
        return False
    registro = _leer_registro(carpeta)
    clave = _clave(ra, dec, tam, banda)
    registro = [r for r in registro
                if not ("ra" in r and _clave(r.get("ra", 0), r.get("dec", 0), r.get("tam", 0), r.get("banda", "")) == clave)]
    if len(registro) >= MAX_REGIONES:
        return False
    registro.append({"nombre": nombre, "ra": float(ra), "dec": float(dec), "tam": float(tam), "banda": banda})
    os.makedirs(carpeta, exist_ok=True)
    tmp = os.path.join(carpeta, ARCHIVO + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(registro, f, ensure_ascii=False, indent=1)
    os.replace(tmp, os.path.join(carpeta, ARCHIVO))
    return True
