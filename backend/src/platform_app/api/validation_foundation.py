from fastapi import APIRouter
from fastapi.responses import JSONResponse

def validation_foundation_router(store):
    router=APIRouter(prefix='/api/v1/validation-foundation',tags=['read-only validation foundation'])
    @router.get('/report')
    def report():
        return JSONResponse(content=store.get(),headers={'Cache-Control':'no-store'})
    return router
