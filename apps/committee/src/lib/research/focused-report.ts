interface FocusedOutput {summary:string;details?:Record<string,unknown>;highlights:string[];concerns:string[]}

/** Preserve generated calculations without upgrading them to verified source facts. */
export function focusedReportObservation(output:FocusedOutput):string {
  const details=Object.fromEntries(Object.entries(output.details??{}).filter(([key])=>key!=='semanticReview'))
  return [output.summary,
    ...(output.highlights.length?['必要结论：'+output.highlights.join('；')]:[]),
    ...(Object.keys(details).length?['模型计算与补充（推算，待人工复核，非独立登记事实）：'+JSON.stringify(details)]:[]),
    ...(output.concerns.length?['资料缺口：'+output.concerns.join('；')]:[]),
  ].join('；')
}
