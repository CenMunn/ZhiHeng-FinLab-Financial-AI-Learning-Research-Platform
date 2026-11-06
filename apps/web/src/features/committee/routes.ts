export const SECTIONS=['research','evidence','filings','forecast','scenarios'] as const;
export type CommitteeSection=typeof SECTIONS[number];
export function committeeSection(hash:string):CommitteeSection {
  const value=hash.replace(/^#\/?/,'').replace(/\/$/,'');
  const legacy:Record<string,CommitteeSection>={risk:'scenarios',scenarios:'scenarios',evidence:'evidence',filings:'filings',forecast:'forecast'};
  if(legacy[value])return legacy[value];
  const section=value.replace(/^committee\//,'');
  return SECTIONS.includes(section as CommitteeSection)?section as CommitteeSection:'research';
}
export const committeeHash=(section:CommitteeSection)=>`#/committee/${section}`;
export function embeddedPath(section:CommitteeSection):string|null {
  return section==='scenarios'?null:section==='research'?'/':`/${section}`;
}
export function isLocalOrigin(value:string):boolean {
  try {const url=new URL(value);return url.protocol==='http:'&&['127.0.0.1','localhost'].includes(url.hostname)&&!!url.port&&!url.username&&!url.password&&url.pathname==='/'&&!url.search&&!url.hash;}catch{return false;}
}
