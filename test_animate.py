import numpy as np
from animate import generar_cuadros


def test_norte_arriba_y_la_marca_cae_sobre_la_fuente():
    cubo = np.zeros((1, 20, 20))
    cubo[0, 3, 5] = 10  # fuente en la fila 3, cerca del sur (fila 0 = sur)
    cuadro = generar_cuadros(cubo, vmin=0, vmax=10, escala=4, marcas=[(5, 3)])[0]

    # Al dibujar con el norte arriba, la fuente queda abajo: fila 20 - 1 - 3 = 16
    assert cuadro.getpixel((5 * 4 + 2, 16 * 4 + 2)) == (255, 255, 255)
    assert cuadro.getpixel((5 * 4 + 2, 2)) == (0, 0, 0)

    # El círculo rojo está centrado en esa misma fuente
    arr = np.array(cuadro)
    rojo = (arr[:, :, 0] == 255) & (arr[:, :, 1] == 0) & (arr[:, :, 2] == 0)
    ys, xs = np.nonzero(rojo)
    assert len(ys) > 0
    assert abs(ys.mean() - 66) < 2 and abs(xs.mean() - 22) < 2


def test_invertir():
    cubo = np.zeros((1, 10, 10))
    cubo[0, 2, 2] = 10
    normal = generar_cuadros(cubo, vmin=0, vmax=10, escala=1)[0]
    invertida = generar_cuadros(cubo, vmin=0, vmax=10, escala=1, invertir=True)[0]
    assert normal.getpixel((2, 7)) == (255, 255, 255)
    assert invertida.getpixel((2, 7)) == (0, 0, 0)


def test_colores_y_pixeles_sin_dato():
    from animate import COLOR_SIN_DATO

    cubo = np.zeros((1, 10, 10))
    cubo[0, 2, 2] = 10
    cubo[0, 5, 5] = np.nan
    gris = generar_cuadros(cubo, vmin=0, vmax=10, escala=1)[0]
    color = generar_cuadros(cubo, vmin=0, vmax=10, escala=1, colores=True)[0]

    # En grises, R=G=B; en color la fuente brillante tiene tonos distintos
    assert len(set(gris.getpixel((2, 7)))) == 1
    assert len(set(color.getpixel((2, 7)))) > 1
    # El píxel sin dato (fila 5 -> 10 - 1 - 5 = 4) sale azul solo en color
    assert color.getpixel((5, 4)) == COLOR_SIN_DATO
    assert gris.getpixel((5, 4)) == (0, 0, 0)


def test_gif_se_construye_con_colores():
    from animate import construir_gif

    cubo = np.random.default_rng(0).normal(0, 1, (3, 16, 16))
    cuadros = generar_cuadros(cubo, escala=2, colores=True)
    assert construir_gif(cuadros, 100).startswith(b"GIF")
