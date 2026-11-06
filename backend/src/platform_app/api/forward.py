from fastapi import APIRouter
from fastapi.responses import JSONResponse


def forward_router(store):
    router = APIRouter(prefix='/api/v1/forward-market', tags=['forward observations'])

    @router.get('/status')
    def status():
        return JSONResponse(content=store.get(), headers={'Cache-Control': 'no-store'})

    return router
