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
    ra = st.number_input("RA (grados)", value=210.80227, format="%.5f")
    dec = st.number_input("Dec (grados)", value=54.34895, format="%.5f")
    tam = st.slider("Tamaño de la región (grados)", 0.02, 0.5, 0.1)
    banda = st.selectbox("Banda del detector", ["D1", "D2", "D3", "D4", "D5", "D6"], index=1)
    intervalo = st.slider("Intervalo del blink (ms)", 100, 1000, 500, step=50)
    escala = st.slider("Zoom", 1, 12, 4)
    vmin, vmax = st.slider("Rango de brillo (min - max)", -10.0, 50.0, (-2.0, 10.0))
    invertir = st.checkbox("Invertir valores de píxeles", value=True)
    modo = st.radio("Modo", ["Normal", "Diferencia"])
    reales = st.checkbox("Usar datos reales de IRSA", value=False)
    gaia = st.checkbox("Superponer estrellas de Gaia DR3 (solo datos reales)", value=False)
    colores = st.checkbox("Usar colores (los píxeles sin dato salen en azul)", value=False)
    local = st.checkbox("Usar solo la caché local (sin consultar a IRSA)", value=False)
    max_cuadros = st.slider("Máximo de cuadros (menos = más rápido)", 5, 100, 40)

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
def hacer_gif(vista, vmin, vmax, escala, invertir, marcas, colores, intervalo):
    cuadros = generar_cuadros(vista, vmin, vmax, escala, invertir, marcas, colores)
    return construir_gif(cuadros, intervalo)


try:
    cubo, fechas = cargar(ra, dec, tam, banda, reales, local, max_cuadros)
except Exception as error:
    st.error(f"No se pudieron cargar los datos: {error}")
    st.stop()

cubo = normalizar(cubo)
dif = imagen_diferencia(cubo)

marcas = None
if gaia and reales:
    from catalogs import gaia_a_pixeles
    from process import wcs_comun
    try:
        # radio = mitad de la diagonal de la región, para cubrir también las esquinas
        estrellas = cargar_gaia(ra, dec, tam * 0.71)
        marcas = gaia_a_pixeles(estrellas, wcs_comun(ra, dec, cubo.shape[1]))
    except Exception as error:
        st.warning(f"Gaia no respondió; se muestra la imagen sin las estrellas conocidas. ({error})")

vista = dif if modo == "Diferencia" else cubo
gif = hacer_gif(vista, vmin, vmax, escala, invertir, marcas, colores, intervalo)

tab_anim, tab_cuadro = st.tabs(["Animación", "Cuadro a cuadro"])

with tab_anim:
    st.image(gif)
    st.download_button("Descargar GIF", gif, "animacion.gif", "image/gif")

with tab_cuadro:
    i = st.slider("Cuadro", 0, len(fechas) - 1, 0)
    cuadro = generar_cuadros(vista[i:i + 1], vmin, vmax, escala, invertir, marcas, colores)[0]
    st.image(cuadro, caption=f"Fecha: {fechas[i]}")

cand = encontrar_candidatos(dif)
st.subheader("Candidatos")
st.dataframe(cand)
st.download_button("Exportar CSV", cand.to_csv(index=False), "candidatos.csv")
