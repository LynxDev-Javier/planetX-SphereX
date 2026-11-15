"""Pruebas del flujo de datos reales sin internet.

Se simula IRSA: un servidor local sirve recortes FITS inventados (con extensiones IMAGE,
FLAGS y VARIANCE) y la consulta TAP se reemplaza por una tabla con esas direcciones.
"""
import functools
import http.server
import threading
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from astropy.table import Table

import data
from detect import encontrar_candidatos, imagen_diferencia, normalizar
from process import MASCARA_MALOS, preparar_cuadros, wcs_comun

RA, DEC = 210.80227, 54.34895
TAM_PIX = 58
TAM_DEG = TAM_PIX * 6.15 / 3600
N = 6
ESTRELLAS = [(14, 40), (44, 16), (52, 50)]  # (y, x), fijas en todos los cuadros


def _posicion_movil(i):
    return 8 + 6 * i, 10 + 5 * i  # (y, x) del objeto que se mueve


def _crear_recorte(i, ruta):
    rng = np.random.default_rng(i)
    img = rng.normal(0, 1, (TAM_PIX, TAM_PIX))
    flags = np.zeros((TAM_PIX, TAM_PIX), dtype=np.int32)
    for y, x in ESTRELLAS:
        img[y - 1:y + 2, x - 1:x + 2] += 40
        flags[y - 1:y + 2, x - 1:x + 2] |= 1 << 21  # SOURCE: informativo, no se enmascara
    y, x = _posicion_movil(i)
    img[y - 1:y + 2, x - 1:x + 2] += 25
    flags[5, 5] |= 1 << 10  # HOT: píxel malo, sí se enmascara

    encabezado = wcs_comun(RA, DEC, TAM_PIX).to_header()
    fits.HDUList([
        fits.PrimaryHDU(),
        fits.ImageHDU(img, header=encabezado, name="IMAGE"),
        fits.ImageHDU(flags, header=encabezado, name="FLAGS"),
        fits.ImageHDU(np.ones_like(img), header=encabezado, name="VARIANCE"),
    ]).writeto(ruta)


@pytest.fixture(scope="module")
def servidor(tmp_path_factory):
    carpeta = tmp_path_factory.mktemp("irsa_falso")
    for i in range(N):
        _crear_recorte(i, carpeta / f"recorte_{i}.fits")

    class Silencioso(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    manejador = functools.partial(Silencioso, directory=str(carpeta))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), manejador)
    hilo = threading.Thread(target=httpd.serve_forever, daemon=True)
    hilo.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


@pytest.fixture
def irsa_simulado(servidor, monkeypatch):
    consultas = []

    def query_tap(consulta):
        consultas.append(consulta)
        orden = [3, 0, 5, 1, 4, 2]  # desordenado a propósito: data.py debe ordenar por fecha
        return Table({
            "uri": [f"{servidor}/recorte_{i}.fits" for i in orden],
            "time_bounds_lower": [60900.0 + 7 * i for i in orden],
        })

    monkeypatch.setattr(data.Irsa, "query_tap", query_tap)
    return consultas


def test_busqueda_ordena_por_fecha_y_usa_la_consulta_oficial(irsa_simulado):
    obs = data.buscar_observaciones(RA, DEC, TAM_DEG, "D2")
    assert [o["mjd"] for o in obs] == sorted(o["mjd"] for o in obs)
    assert obs[0]["fecha"].startswith("2025-08")
    consulta = irsa_simulado[0]
    assert "SPHEREx-D2" in consulta
    assert f"center={RA},{DEC}d" in consulta
    assert "spherex.artifact" in consulta and "spherex.plane" in consulta


def test_banda_invalida():
    with pytest.raises(ValueError):
        data.buscar_observaciones(RA, DEC, TAM_DEG, "D9")


def test_reintentos():
    intentos = []

    def inestable():
        intentos.append(1)
        if len(intentos) < 3:
            raise OSError("502")
        return "ok"

    assert data._con_reintentos(inestable, espera=0) == "ok"
    assert len(intentos) == 3


def test_descarga_cache_y_flujo_completo(irsa_simulado, tmp_path, monkeypatch):
    obs = data.buscar_observaciones(RA, DEC, TAM_DEG, "D2")
    carpeta = tmp_path / "cache"
    rutas, fechas = data.descargar(obs, str(carpeta))
    assert len(rutas) == N and all(Path(r).exists() for r in rutas)

    # Segunda vez: todo sale de la caché, sin tocar la red
    def sin_red(*args, **kwargs):
        raise AssertionError("no debía pedir nada a la red")

    monkeypatch.setattr(data.requests, "get", sin_red)
    rutas2, _ = data.descargar(obs, str(carpeta))
    assert rutas2 == rutas

    cubo, etiquetas = preparar_cuadros(rutas, RA, DEC, TAM_DEG, fechas)
    assert cubo.shape == (N, TAM_PIX, TAM_PIX)
    assert etiquetas == fechas  # sin WCS-WAVE no hay longitud de onda, solo la fecha

    # El píxel con bandera HOT queda en NaN; las estrellas (bandera SOURCE) no
    assert np.isnan(cubo[:, 5, 5]).all()
    for y, x in ESTRELLAS:
        assert np.isfinite(cubo[:, y, x]).all()

    # Y el objeto móvil aparece en cada cuadro, en el orden de las fechas
    cand = encontrar_candidatos(imagen_diferencia(normalizar(cubo)))
    for i in range(N):
        y, x = _posicion_movil(i)
        del_cuadro = cand[cand["cuadro"] == i]
        distancias = np.hypot(del_cuadro["x"] - x, del_cuadro["y"] - y)
        assert len(del_cuadro) > 0 and distancias.min() < 2


def test_descarga_con_fallos_avisa_y_sigue(servidor, tmp_path):
    obs = [
        {"fecha": "2025-08-13 00:00:00", "mjd": 60900.0, "url": f"{servidor}/recorte_0.fits"},
        {"fecha": "2025-08-20 00:00:00", "mjd": 60907.0, "url": f"{servidor}/no_existe.fits"},
    ]
    with pytest.warns(UserWarning, match="No se pudieron descargar 1 de 2"):
        rutas, fechas = data.descargar(obs, str(tmp_path / "c"), hilos=1)
    assert len(rutas) == 1 and fechas == ["2025-08-13 00:00:00"]


def test_sin_imagenes():
    with pytest.raises(ValueError):
        preparar_cuadros([], RA, DEC, TAM_DEG)


def test_mascara_no_incluye_source():
    assert MASCARA_MALOS & (1 << 21) == 0
    assert MASCARA_MALOS & (1 << 10) != 0


def test_app_con_datos_reales_simulados(irsa_simulado, tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    app = Path(__file__).parent / "app.py"
    monkeypatch.chdir(tmp_path)  # la app guarda la caché en ./cache
    at = AppTest.from_file(str(app), default_timeout=60).run()
    at.slider[0].set_value(TAM_DEG)
    at.checkbox[1].set_value(True)  # "Usar datos reales de IRSA"
    at.run()
    assert not at.exception
    assert not at.error
    assert len(irsa_simulado) >= 1
