import geopandas as gpd
from sqlalchemy import create_engine, text

DB_URL = "postgresql+psycopg2://postgres:Skyler2026*@localhost:5433/bogota_inmobiliaria"
engine = create_engine(DB_URL)

capas = [
    {
        "ruta": r"C:\Users\kenpa\OneDrive\Desktop\FORMACION\colombia-mercado-inmobiliario_v2\data\localidades/localidades_bogota.shp",
        "tabla": "localidades",
        "columnas": ["locnombre", "loccodigo", "geometry"]
    },
    {
        "ruta": r"C:\Users\kenpa\OneDrive\Desktop\FORMACION\colombia-mercado-inmobiliario_v2\data\BARRIOS\SECTOR.shp",
        "tabla": "sectores",
        "columnas": ["SCACODIGO", "SCATIPO", "SCANOMBRE", "geometry"]
    },
    {
        "ruta": r"C:\Users\kenpa\OneDrive\Desktop\FORMACION\colombia-mercado-inmobiliario_v2\data\microterritorio-rural\Microterritorio Rural.shp",
        "tabla": "microterritorios_rurales",
        "columnas": ["id_microte", "numero_mic", "nombre_mic", "area_micro", "geometry"]
    }
]

for capa in capas:
    gdf = gpd.read_file(capa["ruta"])
    gdf = gdf[capa["columnas"]].copy()

    # Normalizar nombres de columnas a minúsculas
    gdf.columns = [c.lower() if c != "geometry" else "geometry" for c in gdf.columns]

    # Asegurar CRS 4326
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
    print(f"✓ {capa['tabla']} cargada — {len(gdf):,} registros")

# Crear índices espaciales
with engine.connect() as conn:
    for tabla in ["localidades", "sectores", "microterritorios_rurales"]:
        conn.execute(text(f"""
            CREATE INDEX IF NOT EXISTS idx_{tabla}_geom
            ON catastro.{tabla} USING GIST (geom);
        """))
    conn.commit()
    print("\n✓ Índices espaciales creados")