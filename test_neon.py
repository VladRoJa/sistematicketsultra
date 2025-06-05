import os
from sqlalchemy import create_engine

uri = os.getenv("SQLALCHEMY_DATABASE_URI")
if not uri:
    raise SystemExit("❌  No está definida SQLALCHEMY_DATABASE_URI")

engine = create_engine(uri, pool_pre_ping=True)

with engine.connect() as conn:
    version = conn.exec_driver_sql("SELECT version();").scalar()
    print("✅  Conectado a:", version)
