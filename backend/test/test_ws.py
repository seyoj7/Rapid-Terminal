import asyncio
import websockets
import time

async def test():
    try:
        async with websockets.connect('ws://localhost:5000/ws/chart/btcusdt/1m') as ws:
            print("Connected to ws://localhost:5000/ws/chart/btcusdt/1m")
            for _ in range(5):
                msg = await ws.recv()
                print(f"{time.time()}: Received {msg}")
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(test())
