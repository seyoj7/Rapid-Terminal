import logging
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from token_fetch import router as token_router

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
        
    yield

app = FastAPI(title="Rapid Terminal API", version="1.0.0", lifespan=lifespan)

# Allow the browser (any origin while running locally) to call this server.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(token_router)

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    """Simple health-check endpoint."""
    return {"status": "ok"}


import os

# Serve frontend static files
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")

if __name__ == "__main__":
    print("Open http://localhost:5000 in your browser")
    uvicorn.run("server:app", host="localhost", port=5000, reload=True, access_log=False)