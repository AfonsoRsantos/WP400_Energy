import sqlite3
import time
import logging

logger = logging.getLogger(__name__)

DB_PATH = '/data/energy.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS energy_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   REAL NOT NULL,
            tensao_L1   REAL, tensao_L2   REAL, tensao_L3   REAL,
            corrente_L1 REAL, corrente_L2 REAL, corrente_L3 REAL,
            potencia_ativa    REAL,
            potencia_reativa  REAL,
            potencia_aparente REAL,
            frequencia  REAL,
            fp_L1 REAL, fp_L2 REAL, fp_L3 REAL
        )
    ''')
    # Index for fast date range queries
    cur.execute('CREATE INDEX IF NOT EXISTS idx_ts ON energy_history(timestamp)')
    # Auto-cleanup: keep only last 30 days
    cutoff = time.time() - 30 * 86400
    cur.execute('DELETE FROM energy_history WHERE timestamp < ?', (cutoff,))
    conn.commit()
    conn.close()
    logger.info(f"Database initialized at {DB_PATH}")

def insert_reading(data):
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO energy_history
            (timestamp, tensao_L1, tensao_L2, tensao_L3,
             corrente_L1, corrente_L2, corrente_L3,
             potencia_ativa, potencia_reativa, potencia_aparente,
             frequencia, fp_L1, fp_L2, fp_L3)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ''', (
            time.time(),
            data.get('tensao_L1'),   data.get('tensao_L2'),   data.get('tensao_L3'),
            data.get('corrente_L1'), data.get('corrente_L2'), data.get('corrente_L3'),
            data.get('potencia_ativa'), data.get('potencia_reativa'), data.get('potencia_aparente'),
            data.get('frequencia'),
            data.get('fp_L1'), data.get('fp_L2'), data.get('fp_L3')
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"DB insert error: {e}")

def get_date_range():
    """Return oldest and newest timestamps in DB."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute('SELECT MIN(timestamp), MAX(timestamp) FROM energy_history')
        row = cur.fetchone()
        conn.close()
        return row
    except:
        return None, None
