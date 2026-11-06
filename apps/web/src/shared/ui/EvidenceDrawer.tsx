import { useEffect, useState } from 'react';
import { ExternalLink, FileText, X } from 'lucide-react';
import { api, type CaseSnapshot } from '../../features/risk/api';
import { TactileButton } from './TactileButton';
import { ModalFrame } from './ModalFrame';

export function EvidenceDrawer({snapshot,onClose}:{snapshot:CaseSnapshot;onClose:()=>void}) {
  const [availability,setAvailability]=useState<'checking'|'available'|'missing'|'changed'|'error'>('checking');
  useEffect(()=>{
    let alive=true;
    setAvailability('checking');
    api.sourceStatus(snapshot.evidence.source_id,snapshot.evidence.source_sha256).then(value=>{if(alive)setAvailability(value.status);})
      .catch(()=>{if(alive)setAvailability('error');});
    return()=>{alive=false;};
  },[snapshot.evidence.source_id,snapshot.evidence.source_sha256]);
  const evidence=snapshot.evidence;
  return <ModalFrame titleId="evidence-title" className="evidence-dialog" onClose={onClose}>
    <div className="drawer-content">
      <header><div className="icon-title"><FileText size={20}/><h2 id="evidence-title">财报原文依据</h2></div>
        <TactileButton className="icon-button compact" aria-label="关闭原文依据" onClick={onClose} autoFocus><X size={20}/></TactileButton></header>
      <p className="drawer-subtitle">{snapshot.company_name} · 2025 年度报告 · 合并报表</p>
      <div className="quote-page">金额所在页 <strong>P{evidence.value_page}</strong></div>
      <blockquote>{evidence.excerpt}</blockquote>
      <dl className="evidence-details">
        <div><dt>金额期间</dt><dd>{snapshot.period_start} 至 {snapshot.period_end}</dd></div>
        <div><dt>单位与范围</dt><dd>人民币元 · 合并口径</dd></div>
        <div><dt>单位/表头依据</dt><dd>{evidence.header_pages.map(page=>`P${page}`).join('、')}</dd></div>
        <div><dt>独立复核</dt><dd>尚待独立人工复核</dd></div>
        <div><dt>历史披露时点</dt><dd>尚未认证首次公开时间</dd></div>
      </dl>
      <div className="method-note"><strong>来源版本</strong><p>保留登记报告的原文引用和文件指纹。原文核对与用户假设分别记录。</p>
        <code>{evidence.source_sha256.slice(0,16)}…</code></div>
      <div className="drawer-actions">
        {availability==='available' && <a className="tactile primary" href={`/api/v1/sources/${encodeURIComponent(evidence.source_id)}?expected_sha256=${evidence.source_sha256}#page=${evidence.value_page}`} target="_blank" rel="noreferrer"><FileText size={17}/>打开本地原文 P{evidence.value_page}</a>}
        <a className="tactile secondary" href={`${evidence.source_url}#page=${evidence.value_page}`} target="_blank" rel="noreferrer">查看官方报告<ExternalLink size={15}/></a>
      </div>
      <p role="status" className="warning-text">{availability==='checking'?'正在核对当前原文件指纹。':availability==='available'?'当前本地文件与此情景的来源指纹一致。':availability==='changed'?'原文件已换版，无法作为此情景的原文；已保存结果和引用保持原样。':'原文件当前无法核对，已保存结果和引用保持原样。'} 官方链接可能指向更新后的文件。</p>
      <p className="drawer-footnote">{evidence.audit_warning}</p>
    </div>
  </ModalFrame>;
}
