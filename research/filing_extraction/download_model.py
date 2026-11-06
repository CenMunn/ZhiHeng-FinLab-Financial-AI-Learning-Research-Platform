"""Pinned public Qwen assets; streaming downloads and upstream content verification."""
import argparse,hashlib,json,os,time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlparse
from research.market.common import PROJECT,write_json

MODEL_ID='Qwen/Qwen2.5-1.5B-Instruct'
REVISION='989aa7980e4cf806f80c7fef2b1adb7bc71aa306'
WEIGHT_SHA='dd924a11b4c220f385b51ffa522daea7c9f3d850e31b162bb5661df483c6d3ee'
WEIGHT_SIZE=3087467144
NAMES=('LICENSE','README.md','config.json','generation_config.json','merges.txt','model.safetensors','tokenizer.json','tokenizer_config.json','vocab.json')
ROOT=PROJECT/'research/artifacts/filing-extraction/model'/REVISION

def file_sha(path):
 with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def verify_file(path,spec):
 path=Path(path)
 if not path.is_file() or path.stat().st_size!=spec['size'] or file_sha(path)!=spec['sha256']:raise ValueError('Model asset missing/changed: '+path.name)
 if spec.get('lfs_sha256'):
  if spec['sha256']!=spec['lfs_sha256']:raise ValueError('Upstream LFS mismatch')
 else:
  digest=hashlib.sha1(b'blob '+str(spec['size']).encode()+b'\0')
  with path.open('rb') as stream:
   for chunk in iter(lambda:stream.read(4*1024*1024),b''):digest.update(chunk)
  if digest.hexdigest()!=spec['blob_id']:raise ValueError('Upstream Git blob mismatch')

def verify_model(manifest_path):
 path=Path(manifest_path).resolve();m=json.loads(path.read_text('utf8'))
 if m['schema']!='filing-extraction-model-v1' or m['model_id']!=MODEL_ID or m['revision']!=REVISION or set(m['files'])!=set(NAMES):raise ValueError('Unexpected model identity or files')
 if m['files']['model.safetensors']['sha256']!=WEIGHT_SHA or m['files']['model.safetensors']['size']!=WEIGHT_SIZE:raise ValueError('Unexpected weight identity')
 for name,spec in m['files'].items():
  if spec['url']!=f'https://huggingface.co/{MODEL_ID}/resolve/{REVISION}/{name}':raise ValueError('Model source not pinned')
  verify_file(path.parent/name,spec)
 metadata=path.parent/'upstream.json'
 if file_sha(metadata)!=m['upstream_sha256']:raise ValueError('Upstream manifest changed')
 upstream=json.loads(metadata.read_text('utf8'))
 if upstream['sha']!=REVISION:raise ValueError('Upstream revision changed')
 indexed={x['rfilename']:x for x in upstream['siblings']}
 for name,spec in m['files'].items():
  item=indexed[name]
  if spec['size']!=item['size'] or spec['blob_id']!=item['blobId'] or spec.get('lfs_sha256')!=(item.get('lfs') or {}).get('sha256'):raise ValueError('Upstream metadata binding differs')
 return m

def validate_range(status,header,start,end,total,received):
 if status!=206 or header!=f'bytes {start}-{end}/{total}' or received!=end-start+1:raise ValueError('Range response status/interval/length mismatch')

def retained_range_path(folder,start,end):
 """Never overwrite incomplete segments; exact-sized candidates still need final LFS verification."""
 folder=Path(folder).resolve();base=folder/f'{start}-{end}.bin'
 candidates=[base]+sorted(folder.glob(f'{start}-{end}.retry-*.bin'))
 for path in candidates:
  if path.resolve().parent!=folder:raise ValueError('Retained range path escaped')
  if path.is_file() and path.stat().st_size==end-start+1:return path,True
 if not base.exists():return base,False
 attempt=1
 while (folder/f'{start}-{end}.retry-{attempt}.bin').exists():attempt+=1
 return folder/f'{start}-{end}.retry-{attempt}.bin',False

def retained_prefix(folder,start,end):
 folder=Path(folder).resolve();candidates=[folder/f'{start}-{end}.bin']+list(folder.glob(f'{start}-{end}.retry-*.bin'))
 valid=[p for p in candidates if p.resolve().parent==folder and p.is_file() and 0<p.stat().st_size<end-start+1]
 return max(valid,key=lambda p:p.stat().st_size) if valid else None

def resume_ranges(url,partial,size,final):
 """Keep original prefix and separately verified HTTP ranges; final LFS hash is mandatory."""
 prefix_size=partial.stat().st_size
 if not 0<prefix_size<size:raise ValueError('Invalid retained prefix size')
 prefix_sha=file_sha(partial);range_root=ROOT/'retained-range-download';range_root.mkdir(exist_ok=True)
 ranges=[(start,min(start+64*1024*1024-1,size-1)) for start in range(prefix_size,size,64*1024*1024)]
 def fetch(interval):
  start,end=interval
  for attempt in range(3):
   target,reused=retained_range_path(range_root,start,end)
   if reused:
    print(json.dumps({'range_reused':[start,end],'bytes':end-start+1}),flush=True)
    return {'start':start,'end':end,'file':target.name,'sha256':file_sha(target),'mode':'retained_exact_length_candidate_final_LFS_required'}
   count=0;subranges=[];inherited=retained_prefix(range_root,start,end)
   try:
    with target.open('xb') as stream:
     if inherited:
      with inherited.open('rb') as previous:
       for chunk in iter(lambda:previous.read(4*1024*1024),b''):stream.write(chunk);count+=len(chunk)
     while start+count<=end:
      left=start+count;right=min(left+8*1024*1024-1,end);received=0
      with urlopen(Request(url,headers={'Range':f'bytes={left}-{right}','User-Agent':'FinancialLearningLab-D29/0.1'}),timeout=60) as response:
       if urlparse(response.url).scheme!='https':raise ValueError('Non-HTTPS range redirect')
       header=response.headers.get('Content-Range');status=response.status
       validate_range(status,header,left,right,size,right-left+1)
       for chunk in iter(lambda:response.read(1024*1024),b''):
        received+=len(chunk);count+=len(chunk)
        if received>right-left+1:raise ValueError('Range exceeds requested bytes')
        stream.write(chunk)
      validate_range(status,header,left,right,size,received);subranges.append({'start':left,'end':right,'bytes':received});stream.flush();os.fsync(stream.fileno())
     stream.flush();os.fsync(stream.fileno())
    if count!=end-start+1:raise ValueError('Recovered range size mismatch')
    print(json.dumps({'range_complete':[start,end],'bytes':count}),flush=True)
    return {'start':start,'end':end,'file':target.name,'sha256':file_sha(target),'mode':'verified_206_subranges_final_LFS_required','inherited_fragment':inherited.name if inherited else None,'subranges':subranges}
   except (OSError,ValueError) as error:
    print(json.dumps({'range_failed':[start,end],'attempt':attempt+1,'retained_bytes':count,'error':str(error)}),flush=True)
    if attempt==2:raise
 with ThreadPoolExecutor(max_workers=2) as executor:receipts=list(executor.map(fetch,ranges))
 if partial.stat().st_size!=prefix_size or file_sha(partial)!=prefix_sha:raise ValueError('Original prefix changed')
 assembled=ROOT/'model.safetensors.assembled';attempt=1
 while assembled.exists():assembled=ROOT/f'model.safetensors.assembled.retry-{attempt}';attempt+=1
 with assembled.open('xb') as output:
  for source in [partial]+[range_root/row['file'] for row in receipts]:
   with source.open('rb') as stream:
    for chunk in iter(lambda:stream.read(4*1024*1024),b''):output.write(chunk)
  output.flush();os.fsync(output.fileno())
 if assembled.stat().st_size!=WEIGHT_SIZE or file_sha(assembled)!=WEIGHT_SHA:raise ValueError('Assembled model fails fixed upstream LFS SHA')
 write_json(range_root/'receipt.json',{'mode':'official HTTPS Range, max two connections, 8MiB requests','prefix_file':str(partial),'prefix_bytes':prefix_size,'prefix_sha256':prefix_sha,'prefix_downloader_sha256':'020b3d7e41a52a809e5ec67cbe49682d17c56c77d1251d012f9259734a70bb90','ranges':receipts,'assembled_sha256':WEIGHT_SHA,'completed_at':datetime.now(timezone.utc).isoformat()})
 os.rename(assembled,final)

def download(*,resume=False):
 ROOT.mkdir(parents=True,exist_ok=True);manifest=ROOT/'manifest.json'
 if manifest.exists():verify_model(manifest);return manifest
 metadata_url=f'https://huggingface.co/api/models/{MODEL_ID}/revision/{REVISION}?blobs=true'
 with urlopen(Request(metadata_url,headers={'User-Agent':'FinancialLearningLab-D29/0.1'}),timeout=45) as response: raw=response.read(2_000_001)
 if len(raw)>2_000_000:raise ValueError('Upstream metadata exceeds bound')
 upstream=json.loads(raw)
 if upstream['sha']!=REVISION:raise ValueError('Upstream revision mismatch')
 path=ROOT/'upstream.json'
 if path.exists():
  old=json.loads(path.read_text('utf8'))
  if old['sha']!=REVISION:raise ValueError('Existing upstream metadata mismatch')
  upstream=old
 else:
  with path.open('xb') as stream:stream.write(raw)
 indexed={x['rfilename']:x for x in upstream['siblings']};files={}
 for name in NAMES:
  item=indexed[name];lfs=(item.get('lfs') or {}).get('sha256');size=item['size'];url=f'https://huggingface.co/{MODEL_ID}/resolve/{REVISION}/{name}'
  if name=='model.safetensors' and (lfs!=WEIGHT_SHA or size!=WEIGHT_SIZE):raise ValueError('Weight metadata mismatch')
  final=ROOT/name
  if not final.exists():
   partial=ROOT/(name+'.partial')
   if partial.exists():
    if not resume or name!='model.safetensors':raise ValueError('Retained partial download: '+str(partial))
    resume_ranges(url,partial,size,final)
    spec={'url':url,'size':size,'sha256':file_sha(final),'blob_id':item['blobId'],'lfs_sha256':lfs};verify_file(final,spec);files[name]=spec;continue
   received=0;last=0;started=time.monotonic()
   with urlopen(Request(url,headers={'User-Agent':'FinancialLearningLab-D29/0.1'}),timeout=60) as response,partial.open('xb') as stream:
    if urlparse(response.url).scheme!='https':raise ValueError('Non-HTTPS model redirect')
    for chunk in iter(lambda:response.read(4*1024*1024),b''):
     received+=len(chunk)
     if received>size:raise ValueError('Model asset exceeds upstream size')
     stream.write(chunk)
     if received-last>=256*1024*1024:print(json.dumps({'file':name,'received':received,'total':size,'seconds':round(time.monotonic()-started,1)}),flush=True);last=received
    stream.flush();os.fsync(stream.fileno())
   spec={'url':url,'size':size,'sha256':file_sha(partial),'blob_id':item['blobId'],'lfs_sha256':lfs}
   verify_file(partial,spec);os.rename(partial,final)
  spec={'url':url,'size':size,'sha256':file_sha(final),'blob_id':item['blobId'],'lfs_sha256':lfs};verify_file(final,spec);files[name]=spec
  print(json.dumps({'file':name,'verified':True,'bytes':size}),flush=True)
 result={'schema':'filing-extraction-model-v1','model_id':MODEL_ID,'revision':REVISION,'retrieved_at':datetime.now(timezone.utc).isoformat(),'files':files,'upstream_url':metadata_url,'upstream_sha256':file_sha(path),'downloader_sha256':file_sha(Path(__file__))}
 write_json(manifest,result);verify_model(manifest);return manifest

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--resume-ranges',action='store_true');args=parser.parse_args();print(str(download(resume=args.resume_ranges)),flush=True)
