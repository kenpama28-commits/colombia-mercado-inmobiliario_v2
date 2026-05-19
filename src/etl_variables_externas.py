import geopandas as gpd
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
import sys
sys.path.append('../src')
from db_config import DB_URL
import os

engine = create_engine(DB_URL)

RAIZ = r"C:\Users\kenpa\OneDrive\Desktop\FORMACION\colombia-mercado-inmobiliario_v2\data\external"

# ── 1. Cargar capas de transporte ─────────────────────────────
print("── Cargando capas de transporte ─────────────────────────")

capas_transporte = [
    {
        "ruta":   os.path.join(RAIZ, "transporte\Estaciones_troncales_transmilenio/Estacion_troncal.shp"),
        "tabla":  "estaciones_tm",
        "cols":   ["nom_est", "tipo_esta", "geometry"],
        "tipo":   "TransMilenio"
    },
    {
        "ruta":   os.path.join(RAIZ, "transporte\estaciones_metro_L1/ESTACIONES.shp"),
        "tabla":  "estaciones_metro_l1",
        "cols":   ["NOMBRE", "TIPO", "geometry"],
        "tipo":   "Metro L1"
    },
    {
        "ruta":   os.path.join(RAIZ, "transporte\estaciones_metro_L2/estaciones_metro_L2.shp"),
        "tabla":  "estaciones_metro_l2",
        "cols":   ["NOMBRE", "TIPO", "geometry"],
        "tipo":   "Metro L2"
    },
    {
        "ruta":   os.path.join(RAIZ, "transporte\paraderos_SITP/PSITP.shp"),
        "tabla":  "paraderos_sitp",
        "cols":   ["nombre_par", "locali_par", "geometry"],
        "tipo":   "SITP"
    }
]

for capa in capas_transporte:
    gdf = gpd.read_file(capa["ruta"])
    gdf = gdf[[c for c in capa["cols"]]].copy()
    gdf.columns = [c.lower() if c != "geometry" else "geometry"
                   for c in gdf.columns]
    gdf["tipo_transporte"] = capa["tipo"]
    if gdf.crs is None or gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(4326)
    gdf = gdf.rename_geometry("geom")
    gdf.to_postgis(capa["tabla"], engine, schema="catastro",
                   if_exists="replace", index=False)
    print(f"  ✓ {capa['tabla']} — {len(gdf):,} registros")

# ── 2. Cargar capas de seguridad ──────────────────────────────
print("\n── Cargando capas de seguridad ──────────────────────────")

# IRLoc — índice de riesgo por localidad
irloc = gpd.read_file(os.path.join(RAIZ, "seguridad\ir_shp/IRLoc.shp"))

# Columnas de delitos por año disponibles
cols_delitos = {
    'homicidios':         [c for c in irloc.columns if c.startswith('CMH') and 'CONT' in c and not 'HC' in c],
    'hurto_personas':     [c for c in irloc.columns if c.startswith('CMPIA') and 'CONT' in c],
    'riñas':              [c for c in irloc.columns if c.startswith('CMR') and 'CONT' in c],
    'narcoticos':         [c for c in irloc.columns if c.startswith('CMN') and 'CONT' in c],
    'orden_publico':      [c for c in irloc.columns if c.startswith('CMAOP') and 'CONT' in c],
}

# Construir índice compuesto de seguridad (promedio normalizado)
for delito, cols in cols_delitos.items():
    if cols:
        irloc[f'total_{delito}'] = irloc[cols].sum(axis=1)

cols_total = [f'total_{d}' for d in cols_delitos.keys() if f'total_{d}' in irloc.columns]
irloc['indice_inseguridad'] = irloc[cols_total].sum(axis=1)

# Normalizar 0-100 (100 = más inseguro)
min_val = irloc['indice_inseguridad'].min()
max_val = irloc['indice_inseguridad'].max()
irloc['indice_inseguridad_norm'] = (
    (irloc['indice_inseguridad'] - min_val) / (max_val - min_val) * 100
).round(2)

irloc_export = irloc[['CMIULOCAL', 'CMNOMLOCAL', 'indice_inseguridad',
                        'indice_inseguridad_norm', 'geometry']].copy()
irloc_export.columns = ['cod_localidad', 'nom_localidad', 'indice_inseguridad',
                         'indice_inseguridad_norm', 'geometry']
if irloc_export.crs is None or irloc_export.crs.to_epsg() != 4326:
    irloc_export = irloc_export.to_crs(4326)
irloc_export = irloc_export.rename_geometry("geom")
irloc_export.to_postgis("indice_seguridad_localidad", engine,
                         schema="catastro", if_exists="replace", index=False)
print(f"  ✓ indice_seguridad_localidad — {len(irloc_export):,} localidades")

# IRSCAT — índice por barrio/sector
irscat = gpd.read_file(os.path.join(RAIZ, "seguridad\ir_shp/IRSCAT.shp"))
for delito, cols in cols_delitos.items():
    cols_scat = [c for c in irscat.columns if any(c.startswith(p) for p in
                 ['CMH', 'CMPIA', 'CMR', 'CMN', 'CMAOP']) and 'CONT' in c]
irscat['indice_inseguridad'] = irscat[[c for c in irscat.columns
                                        if 'CONT' in c]].sum(axis=1)
irscat['indice_inseguridad_norm'] = (
    (irscat['indice_inseguridad'] - irscat['indice_inseguridad'].min()) /
    (irscat['indice_inseguridad'].max() - irscat['indice_inseguridad'].min()) * 100
).round(2)

irscat_export = irscat[['CMIUSCAT', 'CMNOMSCAT',
                          'indice_inseguridad', 'indice_inseguridad_norm',
                          'geometry']].copy()
irscat_export.columns = ['cod_sector', 'nom_sector', 'indice_inseguridad',
                          'indice_inseguridad_norm', 'geometry']
if irscat_export.crs is None or irscat_export.crs.to_epsg() != 4326:
    irscat_export = irscat_export.to_crs(4326)
irscat_export = irscat_export.rename_geometry("geom")
irscat_export.to_postgis("indice_seguridad_sector", engine,
                          schema="catastro", if_exists="replace", index=False)
print(f"  ✓ indice_seguridad_sector — {len(irscat_export):,} sectores")

# ── 3. Cargar estratificación por manzana ─────────────────────
print("\n── Cargando estratificación por manzana ─────────────────")

estrato = gpd.read_file(os.path.join(RAIZ, "Estratificacion_por_manzana/ManzanaEstratificacion.shp"))

estrato_export = estrato[['CODIGO_MAN', 'ESTRATO', 'geometry']].copy()
estrato_export.columns = ['cod_manzana', 'estrato', 'geometry']
estrato_export['estrato'] = pd.to_numeric(
    estrato_export['estrato'], errors='coerce'
)
if estrato_export.crs is None or estrato_export.crs.to_epsg() != 4326:
    estrato_export = estrato_export.to_crs(4326)
estrato_export = estrato_export.rename_geometry("geom")
estrato_export.to_postgis("estratificacion_manzana", engine,
                           schema="catastro", if_exists="replace", index=False)
print(f"  ✓ estratificacion_manzana — {len(estrato_export):,} manzanas")

# ── 4. Crear índices espaciales ───────────────────────────────
print("\n── Creando índices espaciales ───────────────────────────")
tablas_idx = [
    "estaciones_tm", "estaciones_metro_l1", "estaciones_metro_l2",
    "paraderos_sitp", "indice_seguridad_localidad",
    "indice_seguridad_sector", "estratificacion_manzana"
]
with engine.connect() as conn:
    for tabla in tablas_idx:
        conn.execute(text(f"""
            CREATE INDEX IF NOT EXISTS idx_{tabla}_geom
            ON catastro.{tabla} USING GIST (geom);
        """))
    conn.commit()
    print(f"  ✓ Índices creados para {len(tablas_idx)} tablas")

print("\n✅ ETL variables externas completado")