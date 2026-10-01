"""Sport Stadion — dummy sports retail backend + storefront.

Run:  .venv/bin/uvicorn app.main:app --reload
API docs: http://127.0.0.1:8000/docs
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import models  # noqa: F401  (registers tables)
from .database import Base, SessionLocal, engine
from .routers import cart, catalog, orders
from .seed import seed_if_empty

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_if_empty(db)
    yield


app = FastAPI(
    title="Sport Stadion API",
    version="1.0.0",
    description="Dummy sports retail backend: catalog, cart, checkout and orders. All prices in IDR.",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.include_router(catalog.router)
app.include_router(cart.router)
app.include_router(orders.router)


@app.get("/api/health", tags=["meta"])
def health():
    return {"status": "ok"}


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
