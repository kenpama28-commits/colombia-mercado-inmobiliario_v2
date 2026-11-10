-- Esquema principal del proyecto
CREATE SCHEMA IF NOT EXISTS catastro;

-- Tabla para los shapefiles de valor comercial por manzana
CREATE TABLE catastro.valor_manzana (
    id               SERIAL PRIMARY KEY,
    anio             SMALLINT NOT NULL,
    cod_manzana      VARCHAR(20),
    localidad        VARCHAR(60),
    upz              VARCHAR(60),
    valor_mediano    NUMERIC(14, 2),
    geom             GEOMETRY(MULTIPOLYGON, 4326)
);

-- Índice espacial
CREATE INDEX idx_valor_manzana_geom
    ON catastro.valor_manzana USING GIST (geom);

-- Índice por año para consultas de series de tiempo
CREATE INDEX idx_valor_manzana_anio
    ON catastro.valor_manzana (anio);