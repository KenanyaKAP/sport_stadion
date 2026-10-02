"""Sport Stadion — dummy sports retail backend + storefront.

Run:  .venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8765
API docs: http://127.0.0.1:8765/docs
(--host 0.0.0.0 makes it reachable from other devices, e.g. the Conversify iPhone app.)
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from mcp.server.transport_security import TransportSecuritySettings
from sqlalchemy.orm import Session

from . import models, services
from .database import Base, SessionLocal, engine, get_db
from .mcp_server import mcp, refresh_instructions
from .routers import cart, catalog, orders
from .seed import seed_if_empty

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_if_empty(db)
        refresh_instructions(db)
    async with mcp.session_manager.run():
        yield


app = FastAPI(
    title="Sport Stadion API",
    version="1.0.0",
    description="Dummy sports retail backend: catalog, cart, checkout and orders. All prices in IDR.",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])



@app.exception_handler(services.ServiceError)
async def service_error_handler(_, exc: services.ServiceError):
    return JSONResponse(status_code=exc.status, content={"detail": exc.message})


app.include_router(catalog.router)
app.include_router(cart.router)
app.include_router(orders.router)


@app.get("/api/health", tags=["meta"])
def health():
    return {"status": "ok"}


@app.get("/api/info", tags=["meta"], summary="Retailer handshake used by Conversify to verify the connection")
def info(db: Session = Depends(get_db)):
    return {
        "name": "Sport Stadion",
        "tagline": "Perlengkapan olahraga — sepatu, apparel, bola, raket, dan aksesoris.",
        "api_version": app.version,
        "currency": "IDR",
        "mcp_endpoint": "/mcp",
        "product_count": db.query(models.Product).count(),
        "category_count": db.query(models.Category).count(),
    }


# ---------- MCP (Streamable HTTP at /mcp) ----------
# Stateless + plain JSON responses: the customer account travels in the X-Customer-Email header, so no
# MCP session is needed, and clients don't have to parse SSE. DNS-rebinding protection is off because the
# server is reached by LAN hostname/IP (e.g. Kens-MacBook-Pro.local) from the iPhone during development.
_mcp_app = mcp.streamable_http_app(
    streamable_http_path="/mcp",
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)
app.router.routes.extend(_mcp_app.routes)  # a single Route("/mcp"); added directly so /mcp has no redirect


# ---------- Storefront (static pages that consume the API above) ----------

app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")


def _page(name: str):
    return lambda: FileResponse(WEB_DIR / name)


app.get("/", include_in_schema=False)(_page("index.html"))
app.get("/product/{slug}", include_in_schema=False)(lambda slug: FileResponse(WEB_DIR / "product.html"))
app.get("/cart", include_in_schema=False)(_page("cart.html"))
app.get("/checkout", include_in_schema=False)(_page("checkout.html"))
app.get("/order/{order_number}", include_in_schema=False)(lambda order_number: FileResponse(WEB_DIR / "order.html"))
app.get("/orders", include_in_schema=False)(_page("orders.html"))
