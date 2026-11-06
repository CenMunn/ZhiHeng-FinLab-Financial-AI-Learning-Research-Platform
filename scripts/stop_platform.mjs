import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';

const entries={committee:'start_committee.mjs',backend:'platform_app.api.app:create_app',frontend:'vite.js'};
export function isOwnedProcess(record,info,root){
  const normalize=value=>String(value??'').replaceAll('/','\\').toLowerCase();
  return Number.isInteger(record?.pid)&&record.pid>1&&info?.ProcessId===record.pid&&!!entries[record.role]
    &&normalize(info.CommandLine).includes(normalize(root)+'\\')
    &&normalize(info.CommandLine).includes(normalize(entries[record.role]))
    &&Number.isFinite(Date.parse(record.startedAt))&&Math.abs(Date.parse(record.startedAt)-Date.parse(info.CreatedAt))<10;
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
  const recordPath=process.argv.includes('--record')?path.resolve(process.argv[process.argv.indexOf('--record')+1]):path.join(root,'.local/platform/processes.json');
  if(!recordPath.startsWith(path.join(root,'.local/platform')+path.sep))throw Error('进程记录必须位于本平台本地目录。');
  if(!fs.existsSync(recordPath)){console.log('没有由整平台启动器登记的进程，不会结束其他服务。');}
  else{
    const records=JSON.parse(fs.readFileSync(recordPath,'utf8')).processes??[];
    for(const record of records){
      if(!Number.isInteger(record.pid)||record.pid<=1)continue;
      const query=`[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false);$p=Get-CimInstance Win32_Process -Filter "ProcessId=${record.pid}";if($p){[pscustomobject]@{ProcessId=$p.ProcessId;CommandLine=$p.CommandLine;CreatedAt=$p.CreationDate.ToUniversalTime().ToString('o')}|ConvertTo-Json -Compress}`;
      let info;
      try{info=JSON.parse(execFileSync('powershell.exe',['-NoProfile','-NonInteractive','-Command',query],{encoding:'utf8',windowsHide:true}).replace(/^\uFEFF/,''));}catch{continue;}
      if(!isOwnedProcess(record,info,root)){console.log(`跳过不匹配的 ${record.role} 进程。`);continue;}
      execFileSync('taskkill.exe',['/PID',String(record.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'});
      console.log(`已停止本平台 ${record.role} 进程树。`);
    }
  }
}
