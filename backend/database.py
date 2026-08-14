import aiosqlite
import datetime
import os
import asyncio

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DB_DIR, exist_ok=True)

DB_FILES = {
    "binance": os.path.join(DB_DIR, "binance.db"),
    "hype": os.path.join(DB_DIR, "hyperliquid.db")
}

_INITIALIZED_TABLES = set()
_db_locks = {
    "binance": asyncio.Lock(),
    "hype": asyncio.Lock(),
}

def get_table_name(symbol: str, interval: str) -> str:
    return f"{symbol.lower()}_{interval.lower()}"

async def init_db(exchange: str, symbol: str, interval: str):
    db_file = DB_FILES.get(exchange)
    if not db_file:
        raise ValueError(f"Unknown exchange: {exchange}")
        
    table_name = get_table_name(symbol, interval)
    cache_key = f"{exchange}_{table_name}"
    
    if cache_key in _INITIALIZED_TABLES:
        return

    async with _db_locks[exchange]:
        if cache_key in _INITIALIZED_TABLES:
            return
            
        async with aiosqlite.connect(db_file) as db:
            await db.execute(f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    symbol TEXT,
                    timestamp INTEGER,
                    date TEXT,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume REAL,
                    PRIMARY KEY (symbol, timestamp DESC)
                ) WITHOUT ROWID
            """)
            await db.commit()
            
        _INITIALIZED_TABLES.add(cache_key)

async def save_candle(exchange: str, interval: str, symbol: str, candle: dict):
    symbol = symbol.upper()
    db_file = DB_FILES.get(exchange)
    if not db_file:
        return
        
    await init_db(exchange, symbol, interval)
    table_name = get_table_name(symbol, interval)
    
    ts_seconds = candle["time"]
    ts_millis = ts_seconds * 1000
    date_str = datetime.datetime.fromtimestamp(ts_seconds, tz=datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    
    async with _db_locks[exchange]:
        async with aiosqlite.connect(db_file) as db:
            await db.execute(f"""
                INSERT INTO {table_name} (symbol, timestamp, date, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, timestamp) DO UPDATE SET
                    date=excluded.date,
                    open=excluded.open,
                    high=excluded.high,
                    low=excluded.low,
                    close=excluded.close,
                    volume=excluded.volume
            """, (
                symbol,
                ts_millis,
                date_str,
                candle["open"],
                candle["high"],
                candle["low"],
                candle["close"],
                candle["volume"]
            ))
            await db.commit()

async def save_candles_batch(exchange: str, interval: str, symbol: str, candles: list):
    symbol = symbol.upper()
    db_file = DB_FILES.get(exchange)
    if not db_file:
        return
        
    await init_db(exchange, symbol, interval)
    table_name = get_table_name(symbol, interval)
    
    rows = []
    for c in candles:
        ts_seconds = c["time"]
        ts_millis = ts_seconds * 1000
        date_str = datetime.datetime.fromtimestamp(ts_seconds, tz=datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        rows.append((symbol, ts_millis, date_str, c["open"], c["high"], c["low"], c["close"], c["volume"]))
        
    async with _db_locks[exchange]:
        async with aiosqlite.connect(db_file) as db:
            await db.executemany(f"""
                INSERT INTO {table_name} (symbol, timestamp, date, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, timestamp) DO UPDATE SET
                    date=excluded.date,
                    open=excluded.open,
                    high=excluded.high,
                    low=excluded.low,
                    close=excluded.close,
                    volume=excluded.volume
            """, rows)
            await db.commit()

async def read_candles(exchange: str, interval: str, symbol: str, limit: int = 250, end_time: int = None):
    symbol = symbol.upper()
    db_file = DB_FILES.get(exchange)
    if not db_file:
        return []
        
    await init_db(exchange, symbol, interval)
    table_name = get_table_name(symbol, interval)
    
    query = f"SELECT timestamp, open, high, low, close, volume FROM {table_name} WHERE symbol = ?"
    params = [symbol]
    
    if end_time is not None:
        query += " AND timestamp < ?"
        params.append(end_time)
        
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)
    
    async with _db_locks[exchange]:
        async with aiosqlite.connect(db_file) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            
    candles = [
        {
            "time": row["timestamp"] // 1000,
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "close": row["close"],
            "volume": row["volume"],
        }
        for row in rows
    ]
    return candles
