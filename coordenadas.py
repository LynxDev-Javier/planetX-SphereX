"""Convierte coordenadas escritas en distintos sistemas a RA y Dec en grados (ICRS)."""
import astropy.units as u
from astropy.coordinates import SkyCoord

SISTEMAS = [
    "ICRS en grados (RA, Dec)",
    "ICRS en horas (hh:mm:ss ±dd:mm:ss)",
    "Galácticas (l, b en grados)",
    "Eclípticas (lon, lat en grados)",
    "Nombre del objeto (SIMBAD)",
]


def _numero(texto, nombre):
    try:
        return float(str(texto).replace(",", ".").strip())
    except ValueError:
        raise ValueError(f"{nombre} debe ser un número, por ejemplo 210.8") from None


def a_icrs(sistema, a, b=""):
    """Devuelve (ra, dec) en grados. `a` y `b` son los textos escritos; para un nombre solo `a`.

    Lanza ValueError con un mensaje claro si no se puede interpretar.
    """
    try:
        if sistema == SISTEMAS[1]:
            c = SkyCoord(str(a).strip(), str(b).strip(), unit=(u.hourangle, u.deg), frame="icrs")
        elif sistema == SISTEMAS[2]:
            c = SkyCoord(_numero(a, "l") * u.deg, _numero(b, "b") * u.deg, frame="galactic").icrs
        elif sistema == SISTEMAS[3]:
            c = SkyCoord(_numero(a, "lon") * u.deg, _numero(b, "lat") * u.deg,
                         frame="barycentricmeanecliptic").icrs
        elif sistema == SISTEMAS[4]:
            nombre = str(a).strip()
            if not nombre:
                raise ValueError("escribe el nombre de un objeto")
            c = SkyCoord.from_name(nombre).icrs
        else:
            c = SkyCoord(_numero(a, "RA") * u.deg, _numero(b, "Dec") * u.deg, frame="icrs")
    except ValueError:
        raise
    except Exception as error:  # nombre no encontrado, sin red, formato raro
        raise ValueError(f"no se pudo interpretar la coordenada: {error}") from None
    ra, dec = float(c.ra.deg), float(c.dec.deg)
    if not -90 <= dec <= 90:
        raise ValueError("la declinación debe estar entre -90 y 90")
    return ra, dec
