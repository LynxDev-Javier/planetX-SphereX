import os

import astropy.units as u
import numpy as np
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS
from reproject import reproject_interp

# Bits de FLAGS que invalidan un píxel: transitorio (0), saturación (1), error de rampa (2),
# no funcional (6), dicroico (7), sin datos (9), caliente (10), frío (11) y no lineal (15).
# Los bits informativos, como SOURCE (21), NO se enmascaran: marcarían justo las fuentes
# que queremos ver. Lista tomada de la máscara por defecto del paquete SPXQuery; hay que
# confirmarla en la Tabla 16 del SPHEREx Explanatory Supplement.
BITS_MALOS = (0, 1, 2, 6, 7, 9, 10, 11, 15)
MASCARA_MALOS = sum(1 << bit for bit in BITS_MALOS)


def wcs_comun(ra, dec, tam_pix, escala_arcsec=6.15):
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [ra, dec]
    w.wcs.crpix = [tam_pix / 2, tam_pix / 2]
    w.wcs.cdelt = [-escala_arcsec / 3600, escala_arcsec / 3600]
    return w


def _fecha_del_encabezado(hdul, ruta):
    """Plan B si no llegó la fecha de la tabla de IRSA: busca en los encabezados."""
    for hdu in (hdul[0], hdul["IMAGE"]):
        for clave in ("DATE-OBS", "MJD-OBS"):
            if clave in hdu.header:
                return str(hdu.header[clave])
    return os.path.basename(ruta)


def _longitud_de_onda(hdul, encabezado, centro):
    """Longitud de onda central (micras) en el centro del recorte, como en el tutorial de IRSA.

    Cada imagen de SPHEREx tiene una longitud de onda distinta según el píxel, así que la
    misma estrella puede verse más o menos brillante entre cuadros. Si no se puede
    calcular, devuelve None.
    """
    try:
        x, y = WCS(encabezado, naxis=2).world_to_pixel(centro)
        wcs_onda = WCS(encabezado, fobj=hdul, key="W")
        wcs_onda.sip = None
        longitud, _ = wcs_onda.pixel_to_world(x, y)
        return float(longitud.to(u.micrometer).value)
    except Exception:
        return None


def preparar_cuadros(rutas, ra, dec, tam_deg, fechas=None, escala_arcsec=6.15):
    """Lee los recortes, enmascara píxeles malos y los alinea a un mismo WCS.

    Devuelve (cubo, etiquetas): el cubo tiene forma (n_cuadros, alto, ancho) y cada
    etiqueta es la fecha del cuadro (más su longitud de onda, si se pudo calcular).
    """
    if not rutas:
        raise ValueError("No hay imágenes para esa región y banda.")
    tam_pix = int(round(tam_deg * 3600 / escala_arcsec))
    destino = wcs_comun(ra, dec, tam_pix, escala_arcsec)
    centro = SkyCoord(ra, dec, unit="deg")
    cubo, etiquetas = [], []

    for i, ruta in enumerate(rutas):
        with fits.open(ruta) as hdul:
            encabezado = hdul["IMAGE"].header
            img = hdul["IMAGE"].data.astype(float)

            # Enmascarar solo los píxeles realmente malos (no todo lo que tenga una bandera)
            if "FLAGS" in hdul:
                malos = (hdul["FLAGS"].data.astype(np.int64) & MASCARA_MALOS) != 0
                img[malos] = np.nan

            alineada, _ = reproject_interp(
                (img, WCS(encabezado, naxis=2)), destino, shape_out=(tam_pix, tam_pix)
            )
            cubo.append(alineada)

            etiqueta = fechas[i] if fechas else _fecha_del_encabezado(hdul, ruta)
            longitud = _longitud_de_onda(hdul, encabezado, centro)
            if longitud is not None:
                etiqueta += f" · {longitud:.2f} µm"
            etiquetas.append(etiqueta)

    return np.array(cubo), etiquetas
