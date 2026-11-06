from fastapi import APIRouter,Query
from fastapi.responses import JSONResponse,Response

def filing_semantics_v2_router(store):
    router=APIRouter(prefix='/api/v1/filing-semantics-v2',tags=['filing financial semantics'])
    @router.get('')
    def latest():return JSONResponse(content=store.get(),headers={'Cache-Control':'no-store'})
    @router.get('/pdf')
    def pdf(doc_id:str=Query(pattern=r'^\d{6}-20\d{2}Q[1-4]$')):
        return Response(store.pdf(doc_id),media_type='application/pdf',headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})
    return router
