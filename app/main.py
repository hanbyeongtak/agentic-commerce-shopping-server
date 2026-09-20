import httpx
import pymysql
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app import crud
from app.db import get_conn
from app.routers import auth, merchants, orders, payments, stores, users
from app.schemas import Product, ProductCreate, ProductUpdate

app = FastAPI(title="Agentic Commerce Shopping Server")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth.router)
app.include_router(merchants.router)
app.include_router(users.router)
app.include_router(stores.router)
app.include_router(orders.router)
app.include_router(payments.router)


@app.exception_handler(pymysql.err.IntegrityError)
async def integrity_error_handler(request: Request, exc: pymysql.err.IntegrityError):
    code = exc.args[0]
    if code == 1062:
        return JSONResponse({"detail": "Already exists"}, status_code=409)
    if code == 1451:
        return JSONResponse({"detail": "Referenced by other records"}, status_code=409)
    if code == 1452:
        return JSONResponse({"detail": "Referenced record does not exist"}, status_code=400)
    return JSONResponse({"detail": "Integrity constraint violated"}, status_code=400)


@app.get("/products", response_model=list[Product])
def list_products(
    store_id: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    return crud.fetch_all("products", "id", limit, offset, {"store_id": store_id})


@app.get("/products/{product_id}", response_model=Product)
def get_product(product_id: int):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM products WHERE id = %s", (product_id,))
        row = cur.fetchone()
    if row is None:
        raise HTTPException(404, "Product not found")
    return row


@app.post("/products", response_model=Product, status_code=201)
def create_product(body: ProductCreate):
    data = body.model_dump()
    columns = ", ".join(data)
    placeholders = ", ".join(["%s"] * len(data))
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(f"INSERT INTO products ({columns}) VALUES ({placeholders})", list(data.values()))
        cur.execute("SELECT * FROM products WHERE id = %s", (cur.lastrowid,))
        return cur.fetchone()


@app.patch("/products/{product_id}", response_model=Product)
def update_product(product_id: int, body: ProductUpdate):
    crud.update("products", "id", product_id, body.model_dump(exclude_unset=True))
    return crud.fetch_one("products", "id", product_id)


@app.delete("/products/{product_id}", status_code=204)
def delete_product(product_id: int):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM products WHERE id = %s", (product_id,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Product not found")
    return Response(status_code=204)


@app.get("/search")
async def search_products(
    q: str = Query(..., min_length=1),
    country: str = "CA",
    limit: int = Query(10, ge=1, le=100),
):
    """Agnic 상품 검색 API를 프록시하고 응답을 그대로 반환한다."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                settings.agnic_api_url,
                params={"q": q, "country": country, "limit": limit},
                headers={"X-Agnic-Token": settings.agnic_token},
            )
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Agnic API request failed: {e}")

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type=resp.headers.get("content-type", "application/json"),
    )
