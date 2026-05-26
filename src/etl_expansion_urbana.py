import geopandas as gpd
import pandas as pd
from sqlalchemy import create_engine, text
import sys
sys.path.append('../src')
from db_config import DB_URL
import os

engine = create_engine(DB_URL)

RAIZ = r"C:\Users\kenpa\OneDrive\Desktop\FORMACION\colombia-mercado-inmobiliario_v2\data\external"

capas = [
    {
"ruta":   os.path.join(RAIZ, "pot/clasificacion_de_suelo/clasificacion_de_suelo.shp"),
        "tabla":  "clasificacion_suelo",
        "cols":   ["mancodigo", "grupousoec", "ano", "geometry"],
        "rename": {"mancodigo": "cod_manzana", "grupousoec": "uso_economico", "ano": "anio"}
    },
    {
        "ruta":   os.path.join(RAIZ, "pot/redinfraestructuravialarterial/RedInfraestructuraVialArterial.shp"),
        "tabla":  "red_vial_arterial",
        "cols":   ["CODIGO_ID", "NOMBRE", "CLASIFICAC", "ESTADO", "FUNCIONALI", "PROYECTO", "geometry"],
        "rename": {
            "CODIGO_ID":  "codigo_id",
            "NOMBRE":     "nombre",
            "CLASIFICAC": "clasificacion",
            "ESTADO":     "estado",
            "FUNCIONALI": "funcionalidad",
            "PROYECTO":   "proyecto"
        }
    },
    {
        "ruta":   os.path.join(RAIZ, "pot/tratamientourbanistico/TratamientoUrbanistico.shp"),
        "tabla":  "tratamiento_urbanistico",
        "cols":   ["CODIGO_ID", "CODIGO_TRA", "NOMBRE_TRA", "TIPOLOGIA",
                   "ALTURA_MAX", "CÓDIGO_SU", "geometry"],
        "rename": {
            "CODIGO_ID":  "codigo_id",
            "CODIGO_TRA": "codigo_tratamiento",
            "NOMBRE_TRA": "nombre_tratamiento",
            "TIPOLOGIA":  "tipologia",
            "ALTURA_MAX": "altura_max",
            "CÓDIGO_SU":  "codigo_suelo"
        }
    }
]

for capa in capas:
    print(f"Cargando {capa['tabla']}...", end=' ')
    gdf = gpd.read_file(capa["ruta"])

    # Seleccionar columnas disponibles
    cols_disponibles = [c for c in capa["cols"] if c in gdf.columns or c == "geometry"]
    gdf = gdf[cols_disponibles].copy()

    # Renombrar
    rename_filtrado = {k: v for k, v in capa["rename"].items() if k in gdf.columns}
    gdf = gdf.rename(columns=rename_filtrado)

    # CRS
    if gdf.crs is None or gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(4326)

    gdf = gdf.rename_geometry("geom")

    gdf.to_postgis(
        name=capa["tabla"],
        con=engine,
        schema="catastro",
        if_exists="replace",
        index=False
    )
    print(f"✓ {len(gdf):,} registros")

# Índices espaciales
with engine.connect() as conn:
    for capa in capas:
        conn.execute(text(f"""
            CREATE INDEX IF NOT EXISTS idx_{capa['tabla']}_geom
            ON catastro.{capa['tabla']} USING GIST (geom);
        """))
    conn.commit()
    print("\n✓ Índices espaciales creados")

# Verificar tratamientos urbanísticos disponibles
print("\n── Tratamientos urbanísticos disponibles ────────────────")
with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT nombre_tratamiento, COUNT(*) as poligonos
        FROM catastro.tratamiento_urbanistico
        GROUP BY nombre_tratamiento
        ORDER BY poligonos DESC;
    """))
    for row in result:
        print(f"  {row.nombre_tratamiento:<40} {row.poligonos:>5} polígonos")

print("\n── Usos económicos disponibles ──────────────────────────")
with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT uso_economico, COUNT(*) as manzanas
        FROM catastro.clasificacion_suelo
        GROUP BY uso_economico
        ORDER BY manzanas DESC
        LIMIT 10;
    """))
    for row in result:
        print(f"  {str(row.uso_economico):<40} {row.manzanas:>6} manzanas")

print("\n✅ ETL expansión urbana completado")