"""Búsqueda y descarga de recortes de imágenes SPHEREx desde IRSA.

El flujo (consulta TAP y URL de recorte) sigue el tutorial oficial de cutouts de
IRSA: https://caltech-ipac.github.io/irsa-tutorials/spherex-cutouts
(el código del tutorial tiene licencia BSD-3).
"""
import concurrent.futures
import hashlib
import http.client
import json
import os
import time
import warnings

import numpy as np
import requests
from astropy.io import fits
from astropy.time import Time
from astroquery.ipac.irsa import Irsa

BANDAS = ("D1", "D2", "D3", "D4", "D5", "D6")
ERRORES_DE_RED = (OSError, http.client.HTTPException)  # incluye timeouts y errores HTTP de requests


def _con_reintentos(funcion, intentos=4, espera=1.0):
    """Llama a funcion(); si hay un error de red espera y reintenta (1 s, 2 s, 4 s...)."""
    for n in range(intentos):
        try:
            return funcion()
        except ERRORES_DE_RED:
            if n == intentos - 1:
                raise
            time.sleep(espera * 2 ** n)


def _a_fecha(mjd):
    """Convierte una fecha en MJD a texto. Si el valor no parece MJD, lo deja como texto."""
    if 40000 < mjd < 100000:
        return Time(mjd, format="mjd").iso
    return str(mjd)


def _ruta_lista(carpeta_cache, ra, dec, tam_deg, banda, max_obs):
    """Archivo donde se guarda la lista de observaciones de una región."""
    nombre = f"obs_{ra:.5f}_{dec:.5f}_{tam_deg:.4f}_{banda}_{max_obs}.json"
    return os.path.join(carpeta_cache, nombre)


def buscar_observaciones(ra, dec, tam_deg=0.1, banda="D2", max_obs=40, carpeta_cache="cache"):
    """Lista las observaciones SPHEREx que cubren (ra, dec), ordenadas por fecha.

    ra, dec y tam_deg van en grados; banda es el detector, de "D1" a "D6".
    Si hay más de max_obs observaciones, se eligen repartidas en el tiempo.
    Devuelve una lista de diccionarios: {"fecha": texto, "mjd": número, "url": recorte}.

    La lista se guarda en `carpeta_cache`; si IRSA no responde y esa región ya se había
    consultado, se usa la lista guardada (con un aviso) en vez de fallar.
    """
    if banda not in BANDAS:
        raise ValueError(f"banda debe ser una de {BANDAS}")
    ra, dec, tam_deg = float(ra), float(dec), float(tam_deg)

    # Misma consulta que el tutorial de cutouts: la URL del recorte se arma en el SQL.
    consulta = f"""
    SELECT
        'https://irsa.ipac.caltech.edu/' || a.uri || '?center={ra},{dec}d&size={tam_deg}' AS uri,
        p.time_bounds_lower
    FROM spherex.artifact a
    JOIN spherex.plane p ON a.planeid = p.planeid
    WHERE 1 = CONTAINS(POINT('ICRS', {ra}, {dec}), p.poly)
        AND p.energy_bandpassname = 'SPHEREx-{banda}'
    ORDER BY p.time_bounds_lower
    """
    guardada = _ruta_lista(carpeta_cache, ra, dec, tam_deg, banda, max_obs)
    try:
        resultado = _con_reintentos(lambda: Irsa.query_tap(consulta))
    except Exception as error:
        if os.path.exists(guardada):
            warnings.warn(f"IRSA no respondió ({error!r}); se usa la lista guardada de esta región.")
            with open(guardada, encoding="utf-8") as f:
                return json.load(f)
        raise
    tabla = resultado.to_table() if hasattr(resultado, "to_table") else resultado
    if len(tabla) == 0:
        return []

    mjd = np.asarray(tabla["time_bounds_lower"], dtype=float)
    urls = [str(url) for url in tabla["uri"]]
    orden = np.argsort(mjd)
    if len(orden) > max_obs:
        elegidos = np.unique(np.linspace(0, len(orden) - 1, max_obs).round().astype(int))
        orden = orden[elegidos]
    lista = [{"fecha": _a_fecha(mjd[i]), "mjd": float(mjd[i]), "url": urls[i]} for i in orden]
    os.makedirs(carpeta_cache, exist_ok=True)
    with open(guardada, "w", encoding="utf-8") as f:
        json.dump(lista, f)
    return lista


def descargar(observaciones, carpeta="cache", hilos=6):
    """Descarga los recortes a `carpeta` (con caché y reintentos).

    Devuelve (rutas, fechas) solo de los recortes que se bajaron bien, en el mismo
    orden que `observaciones`. Si alguno falla, avisa con un warning y sigue.
    """
    os.makedirs(carpeta, exist_ok=True)
    errores = []

    def bajar_una(obs):
        clave = hashlib.md5(obs["url"].encode()).hexdigest()[:10]
        ruta = os.path.join(carpeta, f"{obs['fecha'][:10]}_{clave}.fits")
        if os.path.exists(ruta) and os.path.getsize(ruta) > 0:
            return ruta  # ya estaba en la caché

        def pedir():
            respuesta = requests.get(obs["url"], timeout=120)
            respuesta.raise_for_status()
            return respuesta.content

        contenido = _con_reintentos(pedir)
        parcial = ruta + ".part"
        with open(parcial, "wb") as f:
            f.write(contenido)
        try:
            with fits.open(parcial):  # comprueba que sea un FITS válido y no una página de error
                pass
        except Exception:
            os.remove(parcial)
            raise
        os.replace(parcial, ruta)
        return ruta

    def intentar(obs):
        try:
            return bajar_una(obs)
        except Exception as error:
            errores.append(repr(error))
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=hilos) as pool:
        rutas = list(pool.map(intentar, observaciones))

    buenas = [(ruta, obs["fecha"]) for ruta, obs in zip(rutas, observaciones) if ruta is not None]
    if errores:
        warnings.warn(
            f"No se pudieron descargar {len(errores)} de {len(observaciones)} recortes. "
            f"Primer error: {errores[0]}"
        )
    return [r for r, _ in buenas], [f for _, f in buenas]
