from fastapi import APIRouter
from fastapi.responses import JSONResponse,Response
from pydantic import BaseModel,ConfigDict,StrictInt,StrictStr,field_validator

class EventPreviewRequest(BaseModel):
 model_config=ConfigDict(extra='forbid')
 pre:StrictInt
 post:StrictInt
 source_record_sha256:StrictStr
 @field_validator('pre','post')
 @classmethod
 def window(cls,value):
  if not 1<=value<=10:raise ValueError('观察窗口须为1至10个交易日。')
  return value

def event_study_router(store):
 router=APIRouter(prefix='/api/v1/event-study',tags=['announcement event study'])
 @router.get('')
 def latest():return JSONResponse(content=store.get(),headers={'Cache-Control':'no-store'})
 @router.post('/preview')
 def preview(body:EventPreviewRequest):return JSONResponse(content=store.preview(body.pre,body.post,body.source_record_sha256),headers={'Cache-Control':'no-store'})
 @router.get('/document')
 def document(event_id:str):return Response(store.document(event_id),media_type='application/pdf',headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Content-Disposition':'inline; filename="announcement.pdf"'})
 return router
