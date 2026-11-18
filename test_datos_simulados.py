"""Pruebas del flujo de datos reales sin internet.

Se simula IRSA: un servidor local sirve recortes FITS inventados (con extensiones IMAGE,
FLAGS y VARIANCE) y la consulta TAP se reemplaza por una tabla con esas direcciones.
"""
import functools
import os
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
def irsa_simulado(servidor, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # la lista de observaciones se guarda en ./cache
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


def test_app_con_colores_y_descarga_de_gif():
    from streamlit.testing.v1 import AppTest

    app = Path(__file__).parent / "app.py"
    at = AppTest.from_file(str(app), default_timeout=60).run()
    colores = next(c for c in at.checkbox if "colores" in c.label)
    colores.set_value(True)
    at.run()
    assert not at.exception
    assert not at.error


def test_lista_guardada_se_usa_si_irsa_falla(irsa_simulado, monkeypatch):
    primera = data.buscar_observaciones(RA, DEC, TAM_DEG, "D2")
    assert Path("cache").exists()

    def caido(consulta):
        raise OSError("502 Proxy Error")

    monkeypatch.setattr(data.Irsa, "query_tap", caido)
    monkeypatch.setattr(data.time, "sleep", lambda s: None)
    with pytest.warns(UserWarning, match="lista guardada"):
        segunda = data.buscar_observaciones(RA, DEC, TAM_DEG, "D2")
    assert segunda == primera

    # Una región que nunca se consultó sí falla
    with pytest.raises(OSError):
        data.buscar_observaciones(RA + 1, DEC, TAM_DEG, "D2")


def test_listar_cache_encuentra_los_recortes_de_la_region(irsa_simulado):
    obs = data.buscar_observaciones(RA, DEC, TAM_DEG, "D2")
    data.descargar(obs, "cache")

    rutas, fechas = data.listar_cache(RA, DEC, TAM_DEG, "D2", "cache")
    assert len(rutas) == N
    assert fechas == sorted(fechas) and fechas[0].startswith("2025-08")

    # Una región lejana no encuentra nada
    assert data.listar_cache(RA + 1, DEC, TAM_DEG, "D2", "cache") == ([], [])
    with pytest.raises(ValueError):
        data.listar_cache(RA, DEC, TAM_DEG, "D9", "cache")


def test_listar_cache_filtra_por_banda(irsa_simulado):
    obs = data.buscar_observaciones(RA, DEC, TAM_DEG, "D2")
    rutas, _ = data.descargar(obs, "cache")
    for ruta in rutas:  # marca los recortes como detector 1 (D1)
        with fits.open(ruta, mode="update") as hdul:
            hdul["IMAGE"].header["DETECTOR"] = 1
    assert len(data.listar_cache(RA, DEC, TAM_DEG, "D1", "cache")[0]) == N
    assert data.listar_cache(RA, DEC, TAM_DEG, "D2", "cache")[0] == []


def test_app_con_cache_local_no_consulta_a_irsa(irsa_simulado):
    from streamlit.testing.v1 import AppTest

    obs = data.buscar_observaciones(RA, DEC, TAM_DEG, "D2")
    data.descargar(obs, "cache")
    consultas_antes = len(irsa_simulado)

    app = Path(__file__).parent / "app.py"
    at = AppTest.from_file(str(app), default_timeout=60).run()
    at.slider[0].set_value(TAM_DEG)
    next(c for c in at.checkbox if "caché local" in c.label).set_value(True)
    at.run()
    assert not at.exception
    assert not at.error
    assert len(irsa_simulado) == consultas_antes  # no se tocó IRSA


def test_probar_objetivos_guarda_resultados_y_usa_la_cache(irsa_simulado, tmp_path, monkeypatch):
    import probar_objetivos

    salida = tmp_path / "res"
    linea = probar_objetivos.probar("sim", "Simulado", RA, DEC, TAM_DEG, "D2", str(salida))
    assert f"{N} cuadros" in linea
    for nombre in ("sim_normal.gif", "sim_diferencia.gif", "sim_candidatos.csv", "sim_brillo.csv"):
        assert (salida / nombre).stat().st_size > 0

    # Con IRSA caído se sigue pudiendo usar lo ya guardado
    def caido(consulta, **kwargs):
        raise OSError("502 Proxy Error")

    monkeypatch.setattr(data.Irsa, "query_tap", caido)
    monkeypatch.setattr(data.time, "sleep", lambda s: None)
    with pytest.warns(UserWarning):
        linea2 = probar_objetivos.probar("sim", "Simulado", RA, DEC, TAM_DEG, "D2", str(salida))
    assert f"{N} cuadros" in linea2


def test_probar_objetivos_sin_datos_devuelve_1(tmp_path, monkeypatch):
    import probar_objetivos

    monkeypatch.chdir(tmp_path)

    def caido(consulta, **kwargs):
        raise OSError("502 Proxy Error")

    monkeypatch.setattr(data.Irsa, "query_tap", caido)
    monkeypatch.setattr(data.time, "sleep", lambda s: None)
    salida = tmp_path / "res"
    codigo = probar_objetivos.main(["wise0855", "--una", "--salida", str(salida)])
    assert codigo == 1
    assert "SIN DATOS" in (salida / "resumen.txt").read_text(encoding="utf-8")


def test_listar_cache_limita_los_cuadros(irsa_simulado):
    obs = data.buscar_observaciones(RA, DEC, TAM_DEG, "D2")
    data.descargar(obs, "cache")
    rutas, fechas = data.listar_cache(RA, DEC, TAM_DEG, "D2", "cache", max_obs=3)
    assert len(rutas) == 3
    assert fechas == sorted(fechas)
    assert len(data.listar_cache(RA, DEC, TAM_DEG, "D2", "cache", max_obs=50)[0]) == N


def _app_con_cache_local_y_gaia(irsa_simulado):
    import streamlit as st
    from streamlit.testing.v1 import AppTest

    st.cache_data.clear()
    obs = data.buscar_observaciones(RA, DEC, TAM_DEG, "D2")
    data.descargar(obs, "cache")
    app = Path(__file__).parent / "app.py"
    at = AppTest.from_file(str(app), default_timeout=60).run()
    at.slider[0].set_value(TAM_DEG)
    next(c for c in at.checkbox if "caché local" in c.label).set_value(True)
    next(c for c in at.checkbox if "Gaia" in c.label).set_value(True)
    return at


def test_app_con_gaia_que_falla_muestra_aviso(irsa_simulado, monkeypatch):
    import catalogs

    def sin_gaia(*args, **kwargs):
        raise OSError("Gaia caído")

    monkeypatch.setattr(catalogs, "estrellas_gaia", sin_gaia)
    at = _app_con_cache_local_y_gaia(irsa_simulado)
    at.run()
    assert not at.exception
    assert not at.error
    assert any("Gaia" in w.value for w in at.warning)


def test_app_con_gaia_consulta_una_sola_vez(irsa_simulado, monkeypatch):
    import catalogs
    import pandas as pd

    llamadas = []

    def falso_gaia(ra, dec, radio):
        llamadas.append(1)
        return pd.DataFrame({"ra": [RA + 0.001], "dec": [DEC + 0.001]})

    monkeypatch.setattr(catalogs, "estrellas_gaia", falso_gaia)
    at = _app_con_cache_local_y_gaia(irsa_simulado)
    at.run()
    assert not at.exception and not at.error and not at.warning
    at.slider[1].set_value(300)  # cambiar un control no debe volver a consultar a Gaia
    at.run()
    assert not at.exception and not at.error
    assert len(llamadas) == 1


def test_gaia_sin_limite_de_filas(monkeypatch):
    import catalogs
    visto = {}

    class Job:
        def get_results(self):
            import pandas as pd
            class Tabla:
                def to_pandas(self):
                    return pd.DataFrame({"ra": [1.0], "dec": [2.0]})
            return Tabla()

    def falso(centro, radius):
        visto["limite"] = catalogs.Gaia.ROW_LIMIT
        return Job()

    antes = catalogs.Gaia.ROW_LIMIT
    monkeypatch.setattr(catalogs.Gaia, "cone_search_async", falso)
    catalogs.estrellas_gaia(10.0, 20.0, 0.1)
    assert visto["limite"] == -1
    assert catalogs.Gaia.ROW_LIMIT == antes


def test_regiones_guardar_y_listar(tmp_path):
    import regiones
    carpeta = str(tmp_path / "cache")
    os.makedirs(carpeta)
    open(os.path.join(carpeta, "obs_269.45208_4.69333_0.2400_D1_40.json"), "w").write("[]")
    assert regiones.guardar_region("  Barnard   </b>  ", 269.45208, 4.69333, 0.24, "D1", carpeta)
    assert not regiones.guardar_region("   ", 1, 2, 0.1, "D2", carpeta)
    lista = regiones.listar_regiones(carpeta)
    assert len(lista) == 1  # la consulta y el nombre son la misma región
    assert lista[0]["nombre"] == "Barnard </b>"
    open(os.path.join(carpeta, "obs_10.00000_-5.00000_0.1000_D2_40.json"), "w").write("[]")
    assert len(regiones.listar_regiones(carpeta)) == 2


def test_app_elegir_region_guardada(tmp_path, monkeypatch):
    import regiones
    from streamlit.testing.v1 import AppTest

    monkeypatch.chdir(tmp_path)
    regiones.guardar_region("Barnard", 269.45208, 4.69333, 0.24, "D1", "cache")
    app = Path(__file__).parent / "app.py"
    at = AppTest.from_file(str(app), default_timeout=60).run()
    next(c for c in at.checkbox if "caché local" in c.label).set_value(True)
    at.run()
    assert at.selectbox(key="region_guardada") is not None
    at.selectbox(key="region_guardada").select_index(0)
    at.run()
    assert at.session_state["ra"] == 269.45208
    assert at.session_state["banda"] == "D1"


def test_brillo_maximo_alto():
    from streamlit.testing.v1 import AppTest

    app = Path(__file__).parent / "app.py"
    at = AppTest.from_file(str(app), default_timeout=60).run()
    next(n for n in at.number_input if n.label == "Brillo máximo").set_value(1000.0)
    at.run()
    assert not at.exception


def test_app_filtro_de_cuadros_vacios():
    from streamlit.testing.v1 import AppTest

    app = Path(__file__).parent / "app.py"
    at = AppTest.from_file(str(app), default_timeout=60).run()
    next(s for s in at.slider if "sin dato" in s.label).set_value(0)
    at.run()
    assert not at.exception
