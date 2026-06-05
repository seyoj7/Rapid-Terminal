import json
import logging
import httpx
import uvicorn
import websockets
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

class WebSocketLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if "WebSocket" in msg and "[accepted]" in msg:
            return False
        if msg in ("connection open", "connection closed", "connection closed normally"):
            return False
        return True

@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("websockets.client").setLevel(logging.WARNING)
    logging.getLogger("websockets.server").setLevel(logging.WARNING)
    
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "websockets", "websockets.client", "websockets.server"):
        logging.getLogger(logger_name).addFilter(WebSocketLogFilter())
        
    print("Candles and Chart streams are ready!")
    yield

app = FastAPI(title="Rapid Terminal API", version="1.0.0", lifespan=lifespan)

# Allow the browser (any origin while running locally) to call this server.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

BINANCE_BASE  = "https://api.binance.com/api/v3"
BINANCE_WS    = "wss://stream.binance.com:9443/ws"


# ---------------------------------------------------------------------------
# REST – Initial candle snapshot
# ---------------------------------------------------------------------------

@app.get("/api/candles")
async def get_candles(
    symbol: str = Query(..., description="Trading pair symbol, e.g. BTCUSDT"),
    interval: str = Query("15m", description="Kline interval, e.g. 1m 5m 15m 1h 4h 1d 1w"),
    limit: int = Query(250, ge=1, le=1000, description="Number of candles to return"),
):
    """
    Fetch OHLC candlestick data from Binance and return it in
    LightweightCharts-compatible format: { time, open, high, low, close }
    """
    
    url = f"{BINANCE_BASE}/klines"
    params = {"symbol": symbol.upper(), "interval": interval, "limit": limit}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=exc.response.status_code,
                detail=f"Binance API error: {exc.response.text}",
            )
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Could not reach Binance API: {exc}",
            )

    raw = response.json()

    # Transform Binance kline array into LightweightCharts candle objects.
    # Binance format: [openTime, open, high, low, close, volume, ...]
    candles = [
        {
            "time":  int(k[0]) // 1000,   # ms → seconds (Unix timestamp)
            "open":  float(k[1]),
            "high":  float(k[2]),
            "low":   float(k[3]),
            "close": float(k[4]),
        }
        for k in raw
    ]

    # Deduplicate and sort (safety guard – Binance already returns sorted data)
    seen = set()
    unique_candles = []
    for c in candles:
        if c["time"] not in seen:
            seen.add(c["time"])
            unique_candles.append(c)

    unique_candles.sort(key=lambda c: c["time"])
    return unique_candles


# ---------------------------------------------------------------------------
# WebSocket – Live chart candle updates
# ---------------------------------------------------------------------------

@app.websocket("/ws/chart/{symbol}/{interval}")
async def chart_websocket(websocket: WebSocket, symbol: str, interval: str):
    """
    Bridges the browser to the Binance kline stream for the active chart.
    Sends: { time, open, high, low, close, closed }
    `closed` is True when a candle finalises so JS can extend future whitespace.
    """
    
    await websocket.accept()
    stream = f"{symbol.lower()}@kline_{interval}"
    url = f"{BINANCE_WS}/{stream}"

    try:
        async with websockets.connect(url) as binance_ws:
            async for raw in binance_ws:
                msg = json.loads(raw)
                k = msg["k"]
                candle = {
                    "time":   int(k["t"]) // 1000,
                    "open":   float(k["o"]),
                    "high":   float(k["h"]),
                    "low":    float(k["l"]),
                    "close":  float(k["c"]),
                    "closed": bool(k["x"]),   # True when candle closes
                }
                try:
                    await websocket.send_json(candle)
                except (WebSocketDisconnect, Exception):
                    break
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        print(f"[chart ws] {symbol}/{interval} error: {exc}")


# ---------------------------------------------------------------------------
# WebSocket – Live price ticker (used to update coin cards)
# ---------------------------------------------------------------------------

@app.websocket("/ws/ticker/{symbol}")
async def ticker_websocket(websocket: WebSocket, symbol: str):
    """
    Bridges the browser to the Binance 1-minute kline stream for a coin ticker.
    Sends: { price, change }
    """
    await websocket.accept()
    stream = f"{symbol.lower()}@kline_1m"
    url = f"{BINANCE_WS}/{stream}"

    try:
        async with websockets.connect(url) as binance_ws:
            async for raw in binance_ws:
                msg = json.loads(raw)
                k = msg["k"]
                close = float(k["c"])
                open_ = float(k["o"])
                change = round((close - open_) / open_ * 100, 2)
                ticker = {
                    "price":  f"{close:.2f}",
                    "change": change,
                }
                try:
                    await websocket.send_json(ticker)
                except (WebSocketDisconnect, Exception):
                    break
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        print(f"[ticker ws] {symbol} error: {exc}")


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    """Simple health-check endpoint."""
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("server:app", host="localhost", port=5000, reload=True, access_log=False)

