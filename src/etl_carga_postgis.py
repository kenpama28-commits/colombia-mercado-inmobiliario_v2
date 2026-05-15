import geopandas as gpd
import pandas as pd
from sqlalchemy import create_engine, text
import os

# ── Configuración ──────────────────────────────────────────────
DB_URL = "postgresql+psycopg2://postgres:Skyler2026*@localhost:5433/bogota_inmobiliaria"
CARPETA_BASE = r"C:\Users\kenpa\OneDrive\Desktop\FORMACION\colombia-mercado-inmobiliario_v2\data"
TABLA = "valor_manzana"
SCHEMA = "catastro"

# Mapeo de columnas por año hacia esquema unificado
MAPEO = {
    2020: {"MANCODIGO": "cod_manzana", "V_REF": "valor_mediano", "ANO": "anio_raw"},
    2021: {"MANCODIGO": "cod_manzana", "V_REF": "valor_mediano", "ANO": "anio_raw"},
    2022: {"MANCODIGO": "cod_manzana", "V_REF": "valor_mediano", "ANO": "anio_raw"},
    2023: {"MANCODIGO": "cod_manzana", "V_REF": "valor_mediano", "ANO": "anio_raw"},
    2024: {"ManCodigo": "cod_manzana", "ValRef":   "valor_mediano", "Vigencia": "anio_raw"},
    2025: {"ManCodigo": "cod_manzana", "VALOR_REFE": "valor_mediano", "Vigencia": "anio_raw"},
    2026: {"MANCODIGO": "cod_manzana", "V_REF": "valor_mediano", "ANO": "anio_raw"},
}

# ── Funciones ──────────────────────────────────────────────────
def normalizar_geometria(gdf):
    """Convierte Polygon a MultiPolygon para consistencia en PostGIS."""
    from shapely.geometry import MultiPolygon, Polygon
    def to_multi(geom):
        if isinstance(geom, Polygon):
            return MultiPolygon([geom])
        return geom
    gdf["geometry"] = gdf["geometry"].apply(to_multi)
    return gdf

def cargar_shapefile(ruta, anio):
    """Lee, mapea columnas y normaliza un shapefile para un año dado."""
    gdf = gpd.read_file(ruta)
    
    # Renombrar columnas según mapeo del año
    gdf = gdf.rename(columns=MAPEO[anio])
    
    # Conservar solo columnas necesarias + geometry
    columnas = ["cod_manzana", "valor_mediano", "anio_raw", "geometry"]
    gdf = gdf[[c for c in columnas if c in gdf.columns]]
    
    # Extraer año como entero (puede venir como datetime o string)
    if "anio_raw" in gdf.columns:
        muestra = gdf["anio_raw"].iloc[0]
        if hasattr(muestra, "year"):
            gdf["anio"] = gdf["anio_raw"].apply(lambda x: x.year if pd.notna(x) else anio)
        else:
            gdf["anio"] = anio
        gdf = gdf.drop(columns=["anio_raw"])
    else:
        gdf["anio"] = anio

    # Normalizar geometría
    gdf = normalizar_geometria(gdf)
    gdf = gdf.set_crs(4326, allow_override=True)

    print(f"  ✓ {anio} — {len(gdf):,} registros cargados")
    return gdf

def main():
    engine = create_engine(DB_URL)

    # Crear esquema y tabla si no existen
    with engine.connect() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA};"))
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS {SCHEMA}.{TABLA} (
                id            SERIAL PRIMARY KEY,
                anio          SMALLINT NOT NULL,
                cod_manzana   VARCHAR(30),
                valor_mediano NUMERIC(14, 2),
                geom          GEOMETRY(MULTIPOLYGON, 4326)
            );
        """))
        conn.execute(text(f"""
            CREATE INDEX IF NOT EXISTS idx_{TABLA}_geom
                ON {SCHEMA}.{TABLA} USING GIST (geom);
        """))
        conn.execute(text(f"""
            CREATE INDEX IF NOT EXISTS idx_{TABLA}_anio
                ON {SCHEMA}.{TABLA} (anio);
        """))
        conn.commit()
        print("✓ Esquema y tabla listos\n")

    # Recorrer subcarpetas y cargar
    for subcarpeta in sorted(os.listdir(CARPETA_BASE)):
        ruta_sub = os.path.join(CARPETA_BASE, subcarpeta)
        if not os.path.isdir(ruta_sub):
            continue

        # Extraer año del nombre de carpeta
        try:
            anio = int(subcarpeta.split("_")[-1])
        except ValueError:
            print(f"  ⚠ Ignorando carpeta: {subcarpeta}")
            continue

        if anio not in MAPEO:
            print(f"  ⚠ Sin mapeo definido para {anio}, se omite")
            continue

        for archivo in os.listdir(ruta_sub):
            if not archivo.endswith(".shp"):
                continue

            ruta_shp = os.path.join(ruta_sub, archivo)
            print(f"Procesando: {subcarpeta}/{archivo}")

            try:
                gdf = cargar_shapefile(ruta_shp, anio)

                # Renombrar geometry → geom para PostGIS
                gdf = gdf.rename_geometry("geom")

                # Cargar a PostgreSQL (append para acumular todos los años)
                gdf.to_postgis(
                    name=TABLA,
                    con=engine,
                    schema=SCHEMA,
                    if_exists="append",
                    index=False
                )
            except Exception as e:
                print(f"  ✗ Error en {anio}: {e}")

    # Verificación final
    with engine.connect() as conn:
        resultado = conn.execute(text(f"""
            SELECT anio, COUNT(*) as registros
            FROM {SCHEMA}.{TABLA}
            GROUP BY anio
            ORDER BY anio;
        """))
        print("\n── Resumen de carga ──────────────────")
        for fila in resultado:
            print(f"  {fila.anio}: {fila.registros:,} registros")

if __name__ == "__main__":
    main()