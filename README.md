# Mercado inmobiliario de Bogotá

Análisis geoespacial de valores de referencia por manzana en Bogotá (2020–2026). Incluye ETL hacia PostgreSQL/PostGIS, notebooks de exploración, series de tiempo, modelado y expansión urbana, figuras y módulos generales de sustento de avalúos.

## Contenido

- `src/`: carga y transformación de datos geoespaciales.
- `sql/`: esquema y consultas SQL.
- `notebooks/`: siete análisis reproducibles; las salidas guardadas son resultados históricos, no una ejecución verificada en esta copia.
- `reports/figures/`: figuras exportadas.
- `avaluo/`: módulos generales de consulta, sustento y evaluación.
- `models/`: metadatos del modelo, sin el binario entrenado.

## Requisitos y uso

Python 3.12, PostgreSQL con PostGIS y los datos descritos en [`data/README.md`](data/README.md). Instala dependencias con `pip install -r requirements.txt`. Configura `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER` y `PGPASSWORD` en el entorno antes de ejecutar ETL o notebooks. `.env.example` es solo una referencia; el código no carga automáticamente archivos `.env`. Ejecuta los notebooks desde `notebooks/` para resolver `../src`.

## Alcance de la publicación

Los datos geoespaciales, copias de bases de datos, expedientes prediales, propuestas comerciales y archivos del modelo entrenado se conservan solo localmente. Esta copia omite el historial Git anterior, conservado descomprimido en `_historial_git_local/` dentro de la carpeta de origen. La integración DVC descrita en documentos antiguos no está configurada en este repositorio.

**Autor:** Kevin Palacio · [GitHub](https://github.com/kenpama28-commits)
