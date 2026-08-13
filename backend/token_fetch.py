import json
import httpx
import websockets
from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect

router = APIRouter()

BINANCE_BASE  = "https://api.binance.com/api/v3"
BINANCE_WS    = "wss://stream.binance.com:9443/ws"


# ---------------------------------------------------------------------------
# REST – Initial candle snapshot
# ---------------------------------------------------------------------------

@router.get("/api/candles")
async def get_candles(
    symbol: str = Query(..., description="Trading pair symbol, e.g. BTCUSDT"),
    interval: str = Query("15m", description="Kline interval, e.g. 1m 5m 15m 1h 4h 1d 1w"),
    limit: int = Query(250, ge=1, le=1000, description="Number of candles to return"),
    end_time: int = Query(None, description="Fetch candles ending before this Unix timestamp (ms). Used for paginating backwards."),
):
    """
    Fetch OHLC candlestick data from Binance and return it in
    LightweightCharts-compatible format: { time, open, high, low, close }.
    Pass `end_time` (Unix ms) to load older history pages.
    """
    
    url = f"{BINANCE_BASE}/klines"
    params = {"symbol": symbol.upper(), "interval": interval, "limit": limit}
    if end_time is not None:
        params["endTime"] = end_time

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
            "time":   int(k[0]) // 1000,   # ms → seconds (Unix timestamp)
            "open":   float(k[1]),
            "high":   float(k[2]),
            "low":    float(k[3]),
            "close":  float(k[4]),
            "volume": float(k[5]),
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

@router.websocket("/ws/chart/{symbol}/{interval}")
async def chart_websocket(websocket: WebSocket, symbol: str, interval: str):
    """
    Bridges the browser to the Binance kline and aggTrade streams for the active chart.
    Sends kline data and real-time trade data to make the chart update fluidly.
    """
    await websocket.accept()
    stream_kline = f"{symbol.lower()}@kline_{interval}"
    stream_trade = f"{symbol.lower()}@aggTrade"
    url = f"wss://stream.binance.com:9443/stream?streams={stream_kline}/{stream_trade}"

    try:
        async with websockets.connect(url) as binance_ws:
            async for raw in binance_ws:
                msg = json.loads(raw)
                
                # Multiplexed payload wrapper
                if "stream" not in msg:
                    continue
                    
                stream_name = msg["stream"]
                data = msg["data"]
                
                if stream_name == stream_kline:
                    k = data["k"]
                    candle = {
                        "type":   "kline",
                        "time":   int(k["t"]) // 1000,
                        "open":   float(k["o"]),
                        "high":   float(k["h"]),
                        "low":    float(k["l"]),
                        "close":  float(k["c"]),
                        "volume": float(k["v"]),
                        "closed": bool(k["x"]),
                    }
                    try:
                        await websocket.send_json(candle)
                    except (WebSocketDisconnect, Exception):
                        break
                elif stream_name == stream_trade:
                    trade = {
                        "type":  "trade",
                        "price": float(data["p"]),
                    }
                    try:
                        await websocket.send_json(trade)
                    except (WebSocketDisconnect, Exception):
                        break
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        print(f"[chart ws] {symbol}/{interval} error: {exc}")


# ---------------------------------------------------------------------------
# WebSocket – Live price ticker (used to update coin cards)
# ---------------------------------------------------------------------------

@router.websocket("/ws/ticker/{symbol}")
async def ticker_websocket(websocket: WebSocket, symbol: str):
    """
    Bridges the browser to the Binance 24-hour miniTicker stream for a coin ticker.
    Sends: { price, change }
    `change` is the true 24-hour percentage change (close vs. 24h open price).
    """
    await websocket.accept()
    stream = f"{symbol.lower()}@miniTicker"
    url = f"{BINANCE_WS}/{stream}"

    try:
        async with websockets.connect(url) as binance_ws:
            async for raw in binance_ws:
                msg = json.loads(raw)
                # miniTicker fields: c = last price, o = 24h open price
                close = float(msg["c"])
                open_ = float(msg["o"])   # 24-hour rolling open — not session open
                change = round((close - open_) / open_ * 100, 2)
                ticker = {
                    "price":  f"{close:,.2f}",
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
# REST – Initial ticker prices
# ---------------------------------------------------------------------------

@router.get("/api/prices")
async def get_prices():
    """Fetch initial ticker prices for BTC, ETH, SOL."""
    url = f"{BINANCE_BASE}/ticker/24hr"
    symbols = '["BTCUSDT","ETHUSDT","SOLUSDT"]'
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(url, params={"symbols": symbols})
            response.raise_for_status()
        except httpx.HTTPError:
            return {}
            
    data = response.json()
    result = {}
    for item in data:
        sym = item["symbol"]
        close = float(item["lastPrice"])
        open_ = float(item["openPrice"])
        change = round((close - open_) / open_ * 100, 2) if open_ else 0.0
        result[sym] = {
            "price": f"{close:,.2f}",
            "change": change
        }
    return result
