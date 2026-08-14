import json
import time as _time
import httpx
import websockets
from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
import database

router = APIRouter()

BINANCE_BASE  = "https://api.binance.com/api/v3"
BINANCE_WS    = "wss://stream.binance.com:9443/ws"
HYPE_API = "https://api.hyperliquid.xyz/info"
HYPE_WS = "wss://api.hyperliquid.xyz/ws"


# ---------------------------------------------------------------------------
# REST – Initial candle snapshot
# ---------------------------------------------------------------------------

@router.get("/api/candles")
async def get_candles(
    symbol: str = Query(..., description="Trading pair symbol, e.g. BTCUSDT"),
    interval: str = Query("15m", description="Kline interval, e.g. 1m 5m 15m 1h 4h 1d 1w"),
    limit: int = Query(250, ge=1, le=1000, description="Number of candles to return"),
    end_time: int = Query(None, description="Fetch candles ending before this Unix timestamp (ms). Used for paginating backwards."),
    exchange: str = Query("binance", description="Exchange: binance or hype")
):
    """
    Fetch OHLC candlestick data from the selected exchange and return it in
    LightweightCharts-compatible format: { time, open, high, low, close }.
    Pass `end_time` (Unix ms) to load older history pages.
    """
    
    if exchange == "hype":
        hype_symbol = symbol.replace("USDT", "")
        if end_time is not None:
            end_ms = end_time
        else:
            end_ms = int(_time.time() * 1000)
            
        interval_secs = 60
        if interval.endswith('m'): interval_secs = int(interval[:-1]) * 60
        elif interval.endswith('h'): interval_secs = int(interval[:-1]) * 3600
        elif interval.endswith('d'): interval_secs = int(interval[:-1]) * 86400
        elif interval.endswith('w'): interval_secs = int(interval[:-1]) * 7 * 86400
        
        start_ms = end_ms - (interval_secs * limit * 1000)
        
        payload = {
            "type": "candleSnapshot", 
            "req": {
                "coin": hype_symbol, 
                "interval": interval, 
                "startTime": start_ms, 
                "endTime": end_ms
            }
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.post(HYPE_API, json=payload, headers={"Content-Type": "application/json"})
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise HTTPException(status_code=503, detail=f"Hyperliquid API error: {exc}")
                
        raw = response.json()
        if not isinstance(raw, list):
            return []
            
        candles = [
            {
                "time":   int(k["t"]) // 1000,
                "open":   float(k["o"]),
                "high":   float(k["h"]),
                "low":    float(k["l"]),
                "close":  float(k["c"]),
                "volume": float(k["v"]),
            }
            for k in raw
        ]
        
    else:
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
        candles = [
            {
                "time":   int(k[0]) // 1000,
                "open":   float(k[1]),
                "high":   float(k[2]),
                "low":    float(k[3]),
                "close":  float(k[4]),
                "volume": float(k[5]),
            }
            for k in raw
        ]

    seen = set()
    unique_candles = []
    for c in candles:
        if c["time"] not in seen:
            seen.add(c["time"])
            unique_candles.append(c)

    unique_candles.sort(key=lambda c: c["time"])
    
    # Save to database
    await database.save_candles_batch(exchange, interval, symbol, unique_candles)
    
    # Read from database (returns newest first / descending)
    db_candles = await database.read_candles(exchange, interval, symbol, limit, end_time)
    
    # Reverse to return oldest first (ascending) to keep the API response the same
    # as expected by lightweight-charts
    db_candles.reverse()
    
    return db_candles


# ---------------------------------------------------------------------------
# WebSocket – Live chart candle updates
# ---------------------------------------------------------------------------

@router.websocket("/ws/chart/{exchange}/{symbol}/{interval}")
async def chart_websocket(websocket: WebSocket, exchange: str, symbol: str, interval: str):
    """
    Bridges the browser to the respective exchange streams for the active chart.
    Sends kline data and real-time trade data to make the chart update fluidly.
    """
    await websocket.accept()
    
    if exchange == "hype":
        hype_symbol = symbol.upper().replace("USDT", "")
        try:
            async with websockets.connect(HYPE_WS) as hl_ws:
                sub_candle = {"method": "subscribe", "subscription": {"type": "candle", "coin": hype_symbol, "interval": interval}}
                sub_trade = {"method": "subscribe", "subscription": {"type": "trades", "coin": hype_symbol}}
                await hl_ws.send(json.dumps(sub_candle))
                await hl_ws.send(json.dumps(sub_trade))
                
                async for raw in hl_ws:
                    msg = json.loads(raw)
                    channel = msg.get("channel")
                    data = msg.get("data")
                    
                    if channel == "candle" and data:
                        candle = {
                            "type":   "kline",
                            "time":   int(data["t"]) // 1000,
                            "open":   float(data["o"]),
                            "high":   float(data["h"]),
                            "low":    float(data["l"]),
                            "close":  float(data["c"]),
                            "volume": float(data["v"]),
                            "closed": False,
                        }
                        try:
                            await database.save_candle(exchange, interval, symbol, candle)
                            await websocket.send_json(candle)
                        except (WebSocketDisconnect, Exception):
                            break
                    elif channel == "trades" and data:
                        disconnected = False
                        for t in data:
                            trade = {
                                "type":  "trade",
                                "price": float(t["px"]),
                            }
                            try:
                                await websocket.send_json(trade)
                            except (WebSocketDisconnect, Exception):
                                disconnected = True
                                break
                        if disconnected:
                            break
        except (WebSocketDisconnect, websockets.exceptions.ConnectionClosed):
            pass
        except Exception as exc:
            print(f"[chart ws hype] {symbol}/{interval} error: {exc}")
            
    else:
        stream_kline = f"{symbol.lower()}@kline_{interval}"
        stream_trade = f"{symbol.lower()}@aggTrade"
        url = f"wss://stream.binance.com:9443/stream?streams={stream_kline}/{stream_trade}"

        try:
            async with websockets.connect(url) as binance_ws:
                async for raw in binance_ws:
                    msg = json.loads(raw)
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
                            await database.save_candle(exchange, interval, symbol, candle)
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
            print(f"[chart ws binance] {symbol}/{interval} error: {exc}")


# ---------------------------------------------------------------------------
# WebSocket – Live price ticker (used to update coin cards)
# ---------------------------------------------------------------------------

@router.websocket("/ws/ticker/{exchange}/{symbol}")
async def ticker_websocket(websocket: WebSocket, exchange: str, symbol: str):
    """
    Bridges the browser to the ticker stream for a coin ticker.
    Sends: { price, change }
    """
    await websocket.accept()
    
    if exchange == "hype":
        hype_symbol = symbol.upper().replace("USDT", "")
        try:
            async with websockets.connect(HYPE_WS) as hl_ws:
                sub = {"method": "subscribe", "subscription": {"type": "trades", "coin": hype_symbol}}
                await hl_ws.send(json.dumps(sub))
                
                async for raw in hl_ws:
                    msg = json.loads(raw)
                    if msg.get("channel") == "trades":
                        data = msg.get("data")
                        if data:
                            trade_px = data[-1]["px"]
                            ticker = {
                                "price":  f"{float(trade_px):,.2f}",
                            }
                            try:
                                await websocket.send_json(ticker)
                            except (WebSocketDisconnect, Exception):
                                break
        except (WebSocketDisconnect, websockets.exceptions.ConnectionClosed):
            pass
        except Exception as exc:
            print(f"[ticker ws hype] {symbol} error: {exc}")
            
    else:
        stream = f"{symbol.lower()}@miniTicker"
        url = f"{BINANCE_WS}/{stream}"

        try:
            async with websockets.connect(url) as binance_ws:
                async for raw in binance_ws:
                    msg = json.loads(raw)
                    close = float(msg["c"])
                    open_ = float(msg["o"])
                    change = round((close - open_) / open_ * 100, 2)
                    price_change = round(close - open_, 2)
                    ticker = {
                        "price":  f"{close:,.2f}",
                        "change": change,
                        "priceChange": price_change,
                    }
                    try:
                        await websocket.send_json(ticker)
                    except (WebSocketDisconnect, Exception):
                        break
        except WebSocketDisconnect:
            pass
        except Exception as exc:
            print(f"[ticker ws binance] {symbol} error: {exc}")


# ---------------------------------------------------------------------------
# REST – Initial ticker prices
# ---------------------------------------------------------------------------

@router.get("/api/prices")
async def get_prices(exchange: str = Query("binance")):
    """Fetch initial ticker prices for BTC, ETH, SOL."""
    
    if exchange == "hype":
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.post(HYPE_API, json={"type": "metaAndAssetCtxs"})
                response.raise_for_status()
            except httpx.HTTPError:
                return {}
                
        data = response.json()
        if not isinstance(data, list) or len(data) < 2:
            return {}
            
        universe = data[0].get("universe", [])
        ctxs = data[1]
        
        result = {}
        for idx, asset in enumerate(universe):
            sym = asset["name"]
            if sym in ["BTC", "ETH", "SOL"]:
                if idx < len(ctxs):
                    ctx = ctxs[idx]
                    close = float(ctx["markPx"])
                    open_ = float(ctx["prevDayPx"])
                    change = round((close - open_) / open_ * 100, 2) if open_ else 0.0
                    price_change = round(close - open_, 2) if open_ else 0.0
                    result[sym + "USDT"] = {
                        "price": f"{close:,.2f}",
                        "change": change,
                        "priceChange": price_change
                    }
        return result
        
    else:
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
            price_change = round(close - open_, 2) if open_ else 0.0
            result[sym] = {
                "price": f"{close:,.2f}",
                "change": change,
                "priceChange": price_change
            }
        return result
