export interface Announcement {event_id:string;symbol:string;title:string;publication_date:string;publication_at:string|null;time_precision:string;url:string;report_period?:string;document_type?:string;version_status?:string;qualification?:unknown;[key:string]:unknown}
export interface Evidence {metric:string;label:string;value:string|null;unit:string;period:string;scope:string;page:number;excerpt:string;method:string;verification:string}
export interface EventRow {session:string;offset:number;stock_return:number;benchmark_return:number;expected_return:number;abnormal_return:number;cumulative_abnormal_return:number}
export interface EventAnalysis {event_id:string;symbol:string;event_session:string;mapping:{publication_date:string;publication_at:string|null;time_precision:string;rule:string};config:{pre:number;post:number;estimation_start_offset:number;estimation_end_offset:number};estimation:{start:string;end:string;n:number;alpha:number;beta:number;r_squared:number|null;residual_sigma:number};rows:EventRow[];summary:{car:number;event_ar:number};limitations:string[]}
export interface EventRecord {schema:'event-study-publication-v1';run_id:string;created_at:string;catalog:Announcement[];case:{event_id:string;pdf_path:string;pdf_sha256:string;evidence:Evidence[]};analysis:EventAnalysis;artifacts:Record<string,string>;limitations:string[];extraction_evaluation:Record<string,unknown>;[key:string]:unknown}
export interface EventEnvelope {record:EventRecord|null;record_sha256:string|null;artifact_status:'verified'|'missing'|'empty';missing_artifacts:string[]}
export interface EventPreview {source_record_sha256:string;engine_sha256:string;analysis:EventAnalysis}
const hash=(v:unknown)=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const finite=(v:unknown)=>typeof v==='number'&&Number.isFinite(v);
const strings=(v:unknown):v is string[]=>Array.isArray(v)&&v.every(s=>typeof s==='string');
function validAnalysis(a:EventAnalysis){return a&&typeof a.event_id==='string'&&typeof a.event_session==='string'&&a.config&&Number.isInteger(a.config.pre)&&Number.isInteger(a.config.post)&&a.config.pre>=1&&a.config.pre<=10&&a.config.post>=1&&a.config.post<=10&&a.estimation&&Number.isInteger(a.estimation.n)&&a.estimation.n>=2&&[a.estimation.alpha,a.estimation.beta,a.estimation.residual_sigma].every(finite)&&(a.estimation.r_squared===null||finite(a.estimation.r_squared))&&Array.isArray(a.rows)&&a.rows.length===a.config.pre+a.config.post+1&&a.rows.every((r,i)=>typeof r.session==='string'&&r.offset===i-a.config.pre&&[r.stock_return,r.benchmark_return,r.expected_return,r.abnormal_return,r.cumulative_abnormal_return].every(finite))&&a.summary&&finite(a.summary.car)&&finite(a.summary.event_ar)&&strings(a.limitations);}
export function validateEventStudy(body:EventEnvelope):EventEnvelope {
 if(!body||!['verified','missing','empty'].includes(body.artifact_status)||!strings(body.missing_artifacts))throw Error('公告实验响应不完整。');
 if(body.artifact_status==='empty'){if(body.record!==null||body.record_sha256!==null)throw Error('公告实验空状态不一致。');return body;}
 const r=body.record;
 if(!r||r.schema!=='event-study-publication-v1'||!hash(body.record_sha256)||!Array.isArray(r.catalog)||!r.catalog.length||new Set(r.catalog.map(e=>e.event_id)).size!==r.catalog.length||!r.catalog.every(e=>e&&typeof e.event_id==='string'&&typeof e.title==='string'&&['600519','600036','600585'].includes(e.symbol)&&typeof e.publication_date==='string')||!r.case||!r.catalog.some(e=>e.event_id===r.case.event_id)||!Array.isArray(r.case.evidence)||!r.case.evidence.every(e=>e&&typeof e.metric==='string'&&typeof e.label==='string'&&(e.value===null||(typeof e.value==='string'&&/^-?\d+(\.\d+)?$/.test(e.value)&&Number.isFinite(Number(e.value))))&&typeof e.unit==='string'&&Number.isInteger(e.page)&&e.page>=1&&typeof e.excerpt==='string')||!validAnalysis(r.analysis)||r.analysis.event_id!==r.case.event_id||!strings(r.limitations))throw Error('公告实验数据或案例归属不一致。');
 return body;
}
export function validateEventPreview(body:EventPreview,sha:string){if(!body||body.source_record_sha256!==sha||!hash(body.engine_sha256)||!validAnalysis(body.analysis))throw Error('区间预览版本或结果不一致，请刷新后重试。');return body;}
async function request(url:string,options:RequestInit,signal?:AbortSignal){let response;try{response=await fetch(url,{...options,signal,cache:'no-store'});}catch(e){if((e as Error).name==='AbortError')throw e;throw Error('公告实验服务暂不可用，请重试。');}let body;try{body=await response.json();}catch{throw Error('公告实验响应无法读取。');}if(signal?.aborted)throw new DOMException('aborted','AbortError');if(!response.ok)throw Error(body?.message||'公告实验读取失败。');return body;}
export async function readEventStudy(signal?:AbortSignal){return validateEventStudy(await request('/api/v1/event-study',{},signal));}
export async function previewEventStudy(pre:number,post:number,sha:string,signal?:AbortSignal){return validateEventPreview(await request('/api/v1/event-study/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pre,post,source_record_sha256:sha})},signal),sha);}
export function safeSourceUrl(value:string){try{const u=new URL(value);return u.protocol==='https:'&&!['localhost','127.0.0.1','[::1]'].includes(u.hostname)?u.href:null;}catch{return null;}}
export function eventReport(body:EventEnvelope,preview:EventPreview|null,hypothesis:string){
 const r=body.record;if(!r)return '# 公告与市场反应实验\n\n尚未发布公告实验记录。';
 const event=r.catalog.find(e=>e.event_id===r.case.event_id)!,a=preview?.analysis||r.analysis;
 const percent=(n:number)=>`${(n*100).toFixed(6)}%`;
 const cell=(value:unknown)=>String(value??'待核验').replaceAll('|','\\|').replace(/\r?\n/g,' ');
 const period=(value:string)=>value.replace(/(20\d{2})Q1/,'$1年第一季度').replace(/(20\d{2})Q3/,'$1年第三季度').replace(/(20\d{2})H1/,'$1年半年度').replace(/(20\d{2})FY/,'$1年年度');
 const scope=(value:string)=>value==='consolidated'?'合并报表':value==='parent'?'母公司报表':value;
 const pageUrl=(page:number)=>`http://127.0.0.1:8010/api/v1/event-study/document?event_id=${encodeURIComponent(r.case.event_id)}#page=${page}`;
 const sourceUrl=safeSourceUrl(event.url),pdfUrl=safeSourceUrl(String((r.case as unknown as Record<string,unknown>).pdf_url||''));
 const evidenceTable=['| 指标 | 原始金额 | 单位 | 期间 | 报表范围 | 原文页 |','|---|---:|---|---|---|---|',...r.case.evidence.map(e=>`| ${cell(e.label)} | ${cell(e.value)} | ${cell(e.unit)} | ${cell(period(e.period))} | ${cell(scope(e.scope))} | [第${e.page}页](${pageUrl(e.page)}) |`)].join('\n');
 const dailyTable=['| 日期 | 事件日偏移 | 股票收益 | 市场收益 | 市场模型预期收益 | 异常收益 AR | 累计异常收益 CAR |','|---|---:|---:|---:|---:|---:|---:|',...a.rows.map(row=>`| ${row.session} | ${row.offset} | ${percent(row.stock_return)} | ${percent(row.benchmark_return)} | ${percent(row.expected_return)} | ${percent(row.abnormal_return)} | ${percent(row.cumulative_abnormal_return)} |`)].join('\n');
 const engineSha=preview?.engine_sha256||(r.sources as Record<string,string>|undefined)?.['backend/src/platform_app/experiments/event_study.py']||'见完整JSON记录';
 return ['# 公告与市场反应实验',`**公告：${event.title}**（${event.symbol}）`,
 `公告日期：${event.publication_date}；报告期间：${period(event.report_period||'见原文')}。\n\n时间精度：${event.time_precision==='date'?'仅日期，具体首次公开时刻未核定':event.publication_at||'待核定'}。事件交易日：${a.event_session}。${a.mapping.rule}`,
 preview?'本报告使用已应用的区间预览，原始发布结果仍保留在完整JSON中。':'本报告使用原始发布结果。',
 '## 我的学习假设',hypothesis||'尚未填写。','假设为用户当前页面草稿，不改变模型或计算；事件反应描述不等于公告的因果效应，也不是交易收益。',
 '## 财报证据',evidenceTable,...r.case.evidence.map(e=>`**${e.label} · 原文第${e.page}页**\n\n> ${e.excerpt.replace(/\r?\n/g,'\n> ')}\n\n提取方式：${e.method==='rule'?'规则抽取':e.method}；核验状态：${/visual_reviewed|visually_verified/.test(e.verification)?'已核对原文页':'待核验登记'}。`),
 '模型抽取尚未运行，独立人工金标准尚未建立，本报告不提供抽取准确率。',
 '## 固定估计口径与当前窗口',
 `市场模型：预期收益 = α + β × 市场收益。估计区间固定为事件日前第130至21个交易日，本案例实际使用 ${a.estimation.start} 至 ${a.estimation.end} 的 ${a.estimation.n} 个样本。观察窗口改变不会重估参数。`,
 `α = ${a.estimation.alpha.toFixed(8)}；β = ${a.estimation.beta.toFixed(6)}；R² = ${a.estimation.r_squared===null?'未定义':a.estimation.r_squared.toFixed(6)}；残差标准差 = ${a.estimation.residual_sigma.toFixed(8)}。`,
 `当前窗口：T−${a.config.pre} 至 T+${a.config.post}。\n\n窗口 CAR：**${percent(a.summary.car)}**；事件当日 AR：${percent(a.summary.event_ar)}。`,
 'AR = 实际股票收益 − 市场模型预期收益；CAR 为当前窗口内 AR 的累计和。百分比保留六位小数，完整精度数据见JSON导出。',
 '## 逐日市场反应',dailyTable,
 '## 解释边界',...[...new Set([...r.limitations,...a.limitations])].map(s=>`- ${s}`),
 '## 来源与版本',sourceUrl?`[公告目录原文链接](${sourceUrl})`:'公告原文URL尚未登记。',pdfUrl?`[本案例实际取得的官方PDF](${pdfUrl})`:'',
 `本地原文页链接需本机实验服务运行；公开来源链接可用于追溯原始文件。\n\nPDF SHA256：${r.case.pdf_sha256}\n\n实验版本：${r.run_id}\n\n发布记录 SHA256：${body.record_sha256}\n\n计算引擎 SHA256：${engineSha}\n\n发布时间：${r.created_at}`,
 '本报告只列本次学习案例与观察窗口。完整公告目录、行情数组、来源清单和原始/预览结果保留在单独的JSON导出中。'
 ].filter(Boolean).join('\n\n');
}
