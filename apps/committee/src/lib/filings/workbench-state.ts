type SourceIdentity={companyCode:string;companyName:string;reportYear:number;mappingDeclared:boolean;pages:{page:number}[]};
export function sourceForm(source:SourceIdentity,question:string){
  return {code:source.companyCode,name:source.companyName,year:String(source.reportYear),map:source.mappingDeclared?source.pages.map(p=>p.page).join(', '):'',question};
}
export function sampleQuestions(year:number){
  return [
    {label:'双口径资产负债',question:`列出${year}年、${year-1}年合并与母公司/本银行资产总计、负债合计，计算${year}年两种范围资产负债率，保留四位小数。注明单位与原页；资料不全时逐项说明缺口。`},
    {label:'经营现金流及缺口',question:`根据本次提供的原页，给出${year}年合并经营活动产生的现金流量净额；如果原页没有该信息，请说明缺少什么，不要推测。`},
    {label:'收入年度比较',question:`列出${year}年、${year-1}年合并营业收入，计算本年相对上年同比，保留四位小数。注明单位、币种与原页，不推测经营原因。`},
  ];
}
