import os
from pathlib import Path
import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]

def connect():
    return psycopg.connect(
        os.environ.get('WAIN_DATABASE_URL', f'host={ROOT}/.local/run dbname=wain user=wain'),
        row_factory=dict_row,
    )

def initialize(conn):
    conn.execute((ROOT / 'schema.sql').read_text())
