import streamlit as st
from fake_data import cubo_sintetico
from detect import normalizar, imagen_diferencia, encontrar_candidatos
from animate import generar_cuadros, construir_gif

st.set_page_config(
    page_title="LynxScope | Detección en SPHEREx",
    page_icon="🔭",
    layout="wide"
)

st.title("🔭 LynxScope")
st.caption(
    "Objetos en movimiento con imágenes SPHEREx · Equipo Universales · NASA Space Apps 2026"
)

with st.sidebar:
    from coordenadas import SISTEMAS, a_icrs
    from regiones import etiqueta, guardar_region, listar_regiones

    def _elegir_region():
        r = st.session_state.get("region_guardada")
        if r:
            st.session_state.update(
                sistema=SISTEMAS[0], ra=r["ra"], dec=r["dec"], tam=min(max(r["tam"], 0.02), 0.5), banda=r["banda"]
            )

    with st.expander("📍 Región del cielo", expanded=True):
        sistema = st.selectbox("Tipo de coordenadas", SISTEMAS, key="sistema")
        if sistema == SISTEMAS[0]:
            ra = st.number_input("RA (grados)", value=210.80227, format="%.5f", key="ra")
            dec = st.number_input("Dec (grados)", value=54.34895, format="%.5f", key="dec")
        else:
            if sistema == SISTEMAS[4]:
                texto_a, texto_b = st.text_input("Nombre (ej. M101, Barnard's Star)", "M101"), ""
            else:
                etiquetas, ejemplos = {
                    SISTEMAS[1]: (("RA (hh:mm:ss)", "Dec (±dd:mm:ss)"), ("14:03:12.5", "+54:20:56")),
                    SISTEMAS[2]: (("l (grados)", "b (grados)"), ("102.0", "59.8")),
                    SISTEMAS[3]: (("Longitud eclíptica", "Latitud eclíptica"), ("170.0", "59.0")),
                }[sistema]
                texto_a = st.text_input(etiquetas[0], ejemplos[0], key=f"a_{sistema}")
                texto_b = st.text_input(etiquetas[1], ejemplos[1], key=f"b_{sistema}")
            try:
                ra, dec = a_icrs(sistema, texto_a, texto_b)
                st.caption(f"= RA {ra:.5f}°, Dec {dec:.5f}° (ICRS)")
            except ValueError as error:
                st.error(f"Coordenadas no válidas: {error}")
                st.stop()
        tam = st.slider("Tamaño de la región (grados)", 0.02, 0.5, 0.1, key="tam")
        banda = st.selectbox("Banda del detector", ["D1", "D2", "D3", "D4", "D5", "D6"], index=1, key="banda")

    with st.expander("📡 Datos", expanded=True):
        reales = st.checkbox("Usar datos reales de IRSA", value=False)
        local = st.checkbox("Usar solo la caché local (sin consultar a IRSA)", value=False)
        max_cuadros = st.slider("Máximo de cuadros (menos = más rápido)", 5, 100, 40)
        max_vacio = st.slider("Descartar cuadros con más de este % sin dato", 0, 100, 40, step=5)
        if local:
            guardadas = listar_regiones("cache")
            if guardadas:
                st.selectbox(
                    "Regiones ya descargadas", guardadas, index=None,
                    placeholder="Elige una región...", format_func=etiqueta,
                    key="region_guardada", on_change=_elegir_region,
                )
            else:
                st.caption("Aún no hay regiones guardadas en la caché.")
        st.markdown("**Guardar esta región con un nombre**")
        nombre = st.text_input("Nombre (ej. Estrella de Barnard)", max_chars=40)
        if st.button("Guardar nombre"):
            if guardar_region(nombre, ra, dec, tam, banda, "cache"):
                st.success("Guardada. Aparecerá en la lista del modo caché.")
            else:
                st.warning("Escribe un nombre válido (o se llegó al máximo de regiones).")

    with st.expander("🎞️ Animación e imagen", expanded=True):
        modo = st.radio("Modo", ["Normal", "Diferencia"], horizontal=True)
        colores = st.checkbox("Usar colores (los píxeles sin dato salen en azul)", value=False)
        invertir = st.checkbox("Invertir valores de píxeles", value=True)
        intervalo = st.slider("Intervalo del blink (ms)", 100, 1000, 500, step=50)
        escala = st.slider("Zoom", 1, 12, 4)
        col_min, col_max = st.columns(2)
        vmin = col_min.number_input("Brillo mínimo", value=-2.0, step=1.0)
        vmax = col_max.number_input("Brillo máximo", value=10.0, step=1.0)
        if vmax <= vmin:
            st.warning("El máximo debe ser mayor que el mínimo; se usa mínimo + 1.")
            vmax = vmin + 1.0

    with st.expander("⭐ Estrellas de Gaia", expanded=False):
        gaia = st.checkbox("Superponer estrellas de Gaia DR3 (solo datos reales)", value=False)
        mag_max = st.slider("Solo estrellas más brillantes que (mag G)", 8.0, 21.0, 16.0, step=0.5)
        radio_marca = st.slider("Tamaño de los círculos (píxeles)", 1, 6, 2)

reales = reales or local  # la caché local también son datos reales


@st.cache_data(show_spinner="Descargando y alineando imágenes...")
def cargar(ra, dec, tam, banda, reales, local, max_cuadros):
    if reales:
        from process import preparar_cuadros
        if local:
            from data import listar_cache
            rutas, fechas = listar_cache(ra, dec, tam, banda, "cache", max_obs=max_cuadros)
            if not rutas:
                raise ValueError(
                    "No hay recortes en la carpeta cache para esa región y banda. "
                    "Usa las mismas coordenadas y banda con las que se descargaron."
                )
        else:
            from data import buscar_observaciones, descargar
            obs = buscar_observaciones(ra, dec, tam, banda, max_cuadros)
            rutas, fechas = descargar(obs, "cache")
        return preparar_cuadros(rutas, ra, dec, tam, fechas)
    return cubo_sintetico()


@st.cache_data(show_spinner="Consultando Gaia DR3...")
def cargar_gaia(ra, dec, radio):
    from catalogs import estrellas_gaia
    return estrellas_gaia(ra, dec, radio)


@st.cache_data(show_spinner="Generando la animación...")
def hacer_gif(vista, vmin, vmax, escala, invertir, marcas, colores, intervalo, radio_marca):
    cuadros = generar_cuadros(vista, vmin, vmax, escala, invertir, marcas, colores, radio_marca)
    return construir_gif(cuadros, intervalo)


try:
    cubo, fechas = cargar(ra, dec, tam, banda, reales, local, max_cuadros)
except Exception as error:
    st.error(f"No se pudieron cargar los datos: {error}")
    st.stop()

import numpy as np

vacio = np.isnan(cubo).mean(axis=(1, 2)) * 100
buenos = np.flatnonzero(vacio <= max_vacio)
if len(buenos) == 0:
    st.error(
        f"Todos los cuadros tienen más de {max_vacio}% sin dato (el más completo tiene "
        f"{vacio.min():.0f}%). Sube el porcentaje permitido o prueba otras coordenadas."
    )
    st.stop()
descartados = len(cubo) - len(buenos)
cubo = cubo[buenos]
fechas = [fechas[i] for i in buenos]

cubo = normalizar(cubo)
dif = imagen_diferencia(cubo)

marcas = None
if gaia and reales:
    from catalogs import gaia_a_pixeles
    from process import wcs_comun
    try:
        # radio = mitad de la diagonal de la región, para cubrir también las esquinas
        estrellas = cargar_gaia(ra, dec, tam * 0.71)
        if "phot_g_mean_mag" in estrellas:
            estrellas = estrellas[estrellas["phot_g_mean_mag"] <= mag_max]  # NaN queda fuera
        marcas = gaia_a_pixeles(estrellas, wcs_comun(ra, dec, cubo.shape[1]))
        st.caption(f"Gaia: {len(marcas)} estrellas con G ≤ {mag_max:g} en la región")
    except Exception as error:
        st.warning(f"Gaia no respondió; se muestra la imagen sin las estrellas conocidas. ({error})")

vista = dif if modo == "Diferencia" else cubo
gif = hacer_gif(vista, vmin, vmax, escala, invertir, marcas, colores, intervalo, radio_marca)

st.caption(
    f"{len(fechas)} cuadros ({descartados} descartados por tener demasiado vacío) · "
    f"de {fechas[0][:10]} a {fechas[-1][:10]}"
)

tab_anim, tab_cuadro = st.tabs(["Animación", "Cuadro a cuadro"])

with tab_anim:
    st.image(gif)
    st.download_button("Descargar GIF", gif, "animacion.gif", "image/gif")

with tab_cuadro:
    i = st.slider("Cuadro", 0, len(fechas) - 1, 0)
    cuadro = generar_cuadros(vista[i:i + 1], vmin, vmax, escala, invertir, marcas, colores, radio_marca)[0]
    st.image(cuadro, caption=f"Fecha: {fechas[i]}")

cand = encontrar_candidatos(dif)
st.subheader("Candidatos")
st.dataframe(cand)
st.download_button("Exportar CSV", cand.to_csv(index=False), "candidatos.csv")
