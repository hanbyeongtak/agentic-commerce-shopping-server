from fastapi import HTTPException

from app.db import get_conn


def insert(table: str, data: dict) -> int:
    columns = ", ".join(data)
    placeholders = ", ".join(["%s"] * len(data))
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", list(data.values()))
        return cur.lastrowid


def fetch_one(table: str, pk: str, value) -> dict:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT * FROM {table} WHERE {pk} = %s", (value,))
        row = cur.fetchone()
    if row is None:
        raise HTTPException(404, f"{table} not found")
    return row


def fetch_all(table: str, order_by: str, limit: int, offset: int, filters: dict | None = None) -> list[dict]:
    filters = {k: v for k, v in (filters or {}).items() if v is not None}
    where = " AND ".join(f"{k} = %s" for k in filters)
    sql = f"SELECT * FROM {table}" + (f" WHERE {where}" if where else "")
    sql += f" ORDER BY {order_by} DESC LIMIT %s OFFSET %s"
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, [*filters.values(), limit, offset])
        return cur.fetchall()


def update(table: str, pk: str, value, data: dict, touch: str | None = None) -> None:
    """touch: 함께 NOW()로 갱신할 컬럼명 (ON UPDATE 가 없는 updated_at 용)"""
    if not data:
        raise HTTPException(400, "No fields to update")
    assignments = ", ".join(f"{k} = %s" for k in data)
    if touch:
        assignments += f", {touch} = NOW()"
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(f"UPDATE {table} SET {assignments} WHERE {pk} = %s", [*data.values(), value])
    # rowcount는 값이 같으면 0이라 존재 여부는 별도로 확인한다
    fetch_one(table, pk, value)


def delete(table: str, pk: str, value) -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(f"DELETE FROM {table} WHERE {pk} = %s", (value,))
        if cur.rowcount == 0:
            raise HTTPException(404, f"{table} not found")
