from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.datasets import explorer
from app.datasets.explorer import EXPLORER_TABLES, ExplorerError, ExplorerTable

router = APIRouter(prefix="/api/data", tags=["data-explorer"])

FILTER_PREFIX = "filter."


def _table(key: str) -> ExplorerTable:
    table = EXPLORER_TABLES.get(key)
    if table is None:
        raise HTTPException(status_code=404, detail=f"Unknown dataset: {key}")
    return table


def _statements(table: ExplorerTable, request: Request, q: str, sort: str | None, order: str | None):
    filters = {k[len(FILTER_PREFIX):]: v for k, v in request.query_params.items() if k.startswith(FILTER_PREFIX)}
    try:
        return explorer.build_query(table, q=q, sort=sort, order=order, filters=filters)
    except ExplorerError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None


@router.get("/catalog")
async def catalog(db: AsyncSession = Depends(get_db)) -> list[dict]:
    refreshed = await explorer.last_refreshed(db)
    entries = []
    for key, table in EXPLORER_TABLES.items():
        count = (await db.execute(select(func.count()).select_from(table.model))).scalar_one()
        entries.append(
            {
                "key": key,
                "title": table.title,
                "category": table.category,
                "description": table.description,
                "row_count": count,
                "last_refreshed": refreshed.get(table.source) if table.source else None,
                "columns": [{"name": c.name, "label": c.label, "type": c.type, "unit": c.unit} for c in table.columns],
            }
        )
    return entries


@router.get("/{key}/rows")
async def rows(
    key: str,
    request: Request,
    limit: int = Query(50, ge=1, le=explorer.MAX_LIMIT),
    offset: int = Query(0, ge=0),
    q: str = Query("", max_length=200),
    sort: str | None = None,
    order: Literal["asc", "desc"] | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    table = _table(key)
    rows_stmt, count_stmt = _statements(table, request, q, sort, order)
    return await explorer.fetch_rows(db, table, rows_stmt, count_stmt, limit, offset)


@router.get("/{key}/export.csv")
async def export_csv(
    key: str,
    request: Request,
    q: str = Query("", max_length=200),
    sort: str | None = None,
    order: Literal["asc", "desc"] | None = None,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    table = _table(key)
    rows_stmt, _ = _statements(table, request, q, sort, order)
    return StreamingResponse(
        explorer.stream_csv(db, table, rows_stmt),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{key}.csv"'},
    )
