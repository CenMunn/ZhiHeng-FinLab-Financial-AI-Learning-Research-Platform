/** Locate an explicit name/code without treating a code substring as another security. */
export function stockMentionPosition(query: string, mention: string): number {
  const q=query.toLowerCase(), key=mention.toLowerCase().trim()
  if (!key) return -1
  const numeric=/^\d+$/.test(key), ascii=/^[a-z0-9.]+$/.test(key)
  for(let pos=q.indexOf(key);pos!==-1;pos=q.indexOf(key,pos+1)) {
    const before=q[pos-1]??'', after=q[pos+key.length]??''
    if(numeric && (/\d/.test(before) || /\d/.test(after))) continue
    if(ascii && !numeric) {
      const prefix=q.slice(Math.max(0,pos-2),pos)
      const hasMarketPrefix=['us','hk','sh','sz','bj'].includes(prefix)
        && !/[a-z0-9]/.test(q[pos-3]??'')
      if((/[a-z0-9]/.test(before) && !hasMarketPrefix) || /[a-z0-9]/.test(after)) continue
    }
    return pos
  }
  return -1
}
