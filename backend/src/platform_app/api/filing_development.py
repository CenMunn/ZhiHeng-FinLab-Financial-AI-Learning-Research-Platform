from typing import Literal
from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response


def filing_development_router(store):
    router = APIRouter(prefix='/api/v1/filing-development', tags=['filing development validation'])

    @router.get('')
    def latest():
        return JSONResponse(content=store.get(), headers={'Cache-Control': 'no-store'})

    @router.get('/review')
    def review(file: Literal['checklist', 'guide']):
        media, filename = ('text/csv', 'filing-human-review-checklist.csv') if file == 'checklist' else ('text/markdown', 'filing-human-review-guide.md')
        return Response(store.review(file), media_type=media, headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Content-Disposition': f'attachment; filename="{filename}"'})

    return router
