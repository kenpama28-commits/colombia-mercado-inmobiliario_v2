"""Database connection from environment variables. No credentials in source."""
import os
from sqlalchemy.engine import URL

DB_URL = URL.create(
    "postgresql+psycopg2",
    username=os.getenv("PGUSER", "postgres"),
    password=os.getenv("PGPASSWORD"),
    host=os.getenv("PGHOST", "localhost"),
    port=int(os.getenv("PGPORT", "5433")),
    database=os.getenv("PGDATABASE", "bogota_inmobiliaria"),
)
