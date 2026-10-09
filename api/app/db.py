import psycopg
from psycopg.rows import dict_row

from .config import Tenant


def connect(tenant: Tenant) -> psycopg.Connection:
    return psycopg.connect(tenant.database_url, row_factory=dict_row)


def migrate(conn: psycopg.Connection, migrations_dir) -> None:
    for path in sorted(migrations_dir.glob("*.sql")):
        conn.execute(path.read_text())
    conn.commit()
