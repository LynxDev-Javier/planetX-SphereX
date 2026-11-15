
import argparse
import os
import time
import warnings

import numpy as np
import pandas as pd

from animate import construir_gif, generar_cuadros
from data import buscar_observaciones, descargar, listar_cache
from detect import encontrar_candidatos, imagen_diferencia, normalizar
from process import preparar_cuadros

# Coordenadas aproximadas (J2000, en grados). Verifícalas en SIMBAD antes de citarlas.
# Las estrellas con movimiento propio grande (Barnard, WISE 0855) ya se habrán movido
# desde J2000: por eso la región por defecto es amplia (0.24 grados).
OBJETIVOS = {
    "barnard": ("Estrella de Barnard", 269.452, 4.693),
    "epsindi_b": ("Epsilon Indi B (enanas marrones)", 331.044, -56.783),
    "wise0855": ("WISE 0855-0714", 133.79513, -7.24515),
    "rwaur": ("RW Aurigae (variable)", 76.957, 30.401),
    "rdra": ("R Draconis (variable)", 248.18, 66.755),
}


def _datos(ra, dec, tam, banda):
    """Rutas y fechas de los recortes: desde IRSA y, si falla, desde la carpeta cache."""
    try:
        obs = buscar_observaciones(ra, dec, tam, banda)
        return descargar(obs, "cache")
    except Exception as error:
        rutas, fechas = listar_cache(ra, dec, tam, banda, "cache")
        if not rutas:
            raise error
        print("  IRSA no respondió; se usan los recortes de la carpeta cache.", flush=True)
        return rutas, fechas


def probar(clave, nombre, ra, dec, tam, banda, salida):
    """Procesa un objetivo, guarda sus archivos y devuelve una línea de resumen."""
    rutas, fechas = _datos(ra, dec, tam, banda)
    if not rutas:
        raise ValueError("no hay imágenes para esa región y banda")
    cubo, etiquetas = preparar_cuadros(rutas, ra, dec, tam, fechas)

    os.makedirs(salida, exist_ok=True)
    norm = normalizar(cubo)
    dif = imagen_diferencia(norm)
    for sufijo, vista in (("normal", norm), ("diferencia", dif)):
        gif = construir_gif(generar_cuadros(vista, -2, 10, 4, True), 500)
        with open(os.path.join(salida, f"{clave}_{sufijo}.gif"), "wb") as f:
            f.write(gif)

    cand = encontrar_candidatos(dif)
    cand.to_csv(os.path.join(salida, f"{clave}_candidatos.csv"), index=False)

    alto, ancho = cubo.shape[1:]
    centro = cubo[:, alto // 2 - 1:alto // 2 + 2, ancho // 2 - 1:ancho // 2 + 2]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # cuadros enteros sin dato dan un aviso de numpy
        brillo = np.nanmedian(centro.reshape(len(cubo), -1), axis=1)
    pd.DataFrame(
        {"cuadro": range(len(cubo)), "etiqueta": etiquetas, "brillo_centro": brillo}
    ).to_csv(os.path.join(salida, f"{clave}_brillo.csv"), index=False)

    sin_dato = np.isnan(cubo).mean(axis=(1, 2)) * 100
    return (
        f"{nombre}: {len(cubo)} cuadros ({etiquetas[0][:10]} a {etiquetas[-1][:10]}), "
        f"{len(cand)} candidatos, sin dato en promedio {sin_dato.mean():.0f}%"
    )


def main(argv=None):
    ap = argparse.ArgumentParser(description="Prueba LynxScope con los objetivos del reto.")
    ap.add_argument("objetivos", nargs="*", help=f"claves a probar; por defecto todas: {list(OBJETIVOS)}")
    ap.add_argument("--banda", default="D1", help="detector de SPHEREx, D1 a D6 (por defecto D1)")
    ap.add_argument("--tam", type=float, default=0.24, help="tamaño de la región en grados")
    ap.add_argument("--salida", default="resultados", help="carpeta donde se guardan los resultados")
    ap.add_argument("--una", action="store_true", help="un solo intento, sin reintentar")
    ap.add_argument("--espera", type=float, default=5, help="minutos entre reintentos")
    ap.add_argument("--horas", type=float, default=12, help="tiempo máximo reintentando")
    args = ap.parse_args(argv)

    claves = args.objetivos or list(OBJETIVOS)
    desconocidos = [c for c in claves if c not in OBJETIVOS]
    if desconocidos:
        ap.error(f"objetivos desconocidos: {desconocidos}. Opciones: {list(OBJETIVOS)}")

    pendientes, resumen = list(claves), {}
    limite = time.time() + args.horas * 3600
    while pendientes:
        for clave in list(pendientes):
            nombre, ra, dec = OBJETIVOS[clave]
            print(f"Probando {nombre} (RA {ra}, Dec {dec})...", flush=True)
            try:
                resumen[clave] = probar(clave, nombre, ra, dec, args.tam, args.banda, args.salida)
                pendientes.remove(clave)
                print("  OK:", resumen[clave], flush=True)
            except Exception as error:
                print(f"  FALLÓ: {error!r}", flush=True)
        if not pendientes or args.una or time.time() > limite:
            break
        print(f"Faltan {len(pendientes)}; se reintenta en {args.espera:g} min.", flush=True)
        time.sleep(args.espera * 60)

    os.makedirs(args.salida, exist_ok=True)
    with open(os.path.join(args.salida, "resumen.txt"), "w", encoding="utf-8") as f:
        for clave in claves:
            f.write(resumen.get(clave, f"{OBJETIVOS[clave][0]}: SIN DATOS (IRSA no respondió)") + "\n")
    print("Listo." if not pendientes else f"Sin datos: {pendientes}", flush=True)
    return 0 if not pendientes else 1


if __name__ == "__main__":
    raise SystemExit(main())
