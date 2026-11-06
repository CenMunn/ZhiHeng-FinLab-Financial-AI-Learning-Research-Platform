import {committeeSection,type CommitteeSection} from '../features/committee/routes';

export type PlatformRoute={module:'home'|'lab'|'cashflow'|'training'}|{module:'committee';section:CommitteeSection};
export function platformRoute(hash:string):PlatformRoute {
  const value=hash.replace(/^#\/?/,'').replace(/\/$/,'');
  if(value==='lab'||value==='cashflow'||value==='training')return {module:value};
  if(/^committee(?:\/|$)/.test(value)||['risk','scenarios','research','evidence','filings','forecast'].includes(value))return {module:'committee',section:committeeSection(hash)};
  return {module:'home'};
}
