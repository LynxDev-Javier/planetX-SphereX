import io
import numpy as np
from PIL import Image, ImageDraw
#convertir cubo de datos numeros a animados , como un gif, este no usa datos sinteticos no quitarxd
# Paleta de colores (negro, morado, magenta, naranja, amarillo claro), sin depender de matplotlib
_PUNTOS = np.array([0.0, 0.25, 0.5, 0.75, 1.0])
_COLORES = np.array(
    [[0, 0, 0], [60, 10, 110], [170, 40, 100], [245, 130, 30], [255, 250, 200]], dtype=float
)
COLOR_SIN_DATO = (30, 60, 140)  # azul: píxeles sin dato (enmascarados o fuera de la imagen)


def _a_color(n):
    """Convierte valores entre 0 y 1 en una imagen RGB con la paleta de arriba."""
    canales = [np.interp(n, _PUNTOS, _COLORES[:, c]) for c in range(3)]
    return np.stack(canales, axis=-1).astype(np.uint8)


def generar_cuadros(cubo, vmin=-2, vmax=10, escala=4, invertir=False, marcas=None, colores=False):
    """marcas: lista de (x, y) en píxeles del cubo; se dibujan como círculos.

    La imagen se dibuja con el norte arriba y el este a la izquierda: la fila 0 del cubo
    es el sur (la declinación crece con la fila), así que se voltea al dibujar.

    Con colores=True se usa una paleta de color y los píxeles sin dato (NaN) se pintan de
    azul, para no confundirlos con cielo vacío. Con colores=False la imagen es en grises.
    """
    out = []
    for f in cubo:
        alto = f.shape[0]
        sin_dato = ~np.isfinite(f)
        n = np.nan_to_num(np.clip((f - vmin) / (vmax - vmin), 0, 1))
        if invertir:
            n = 1 - n
        n = n[::-1]  # norte arriba
        if colores:
            rgb = _a_color(n)
            rgb[sin_dato[::-1]] = COLOR_SIN_DATO
            im = Image.fromarray(rgb)
        else:
            im = Image.fromarray((n * 255).astype(np.uint8)).convert("RGB")
        im = im.resize((im.width * escala, im.height * escala), Image.NEAREST)
        if marcas:
            d = ImageDraw.Draw(im)
            r = 3 * escala
            color_marca = (0, 255, 255) if colores else (255, 0, 0)
            for x, y in marcas:
                cx, cy = (x + 0.5) * escala, (alto - y - 0.5) * escala
                d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color_marca, width=2)
        out.append(im)
    return out

def construir_gif(cuadros, intervalo_ms=500):
    buf = io.BytesIO()
    cuadros[0].save(
        buf,
        format="GIF",
        save_all=True,
        append_images=cuadros[1:],
        duration=intervalo_ms,
        loop=0
    )
    return buf.getvalue()
