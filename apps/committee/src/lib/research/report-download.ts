export async function fetchReportMarkdown(url: string, fetcher: typeof fetch = fetch): Promise<string> {
  const response = await fetcher(url, { credentials: 'same-origin', cache: 'no-store', headers: { 'ngrok-skip-browser-warning': '1' } })
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(typeof data?.error === 'string' ? data.error : `报告下载失败（HTTP ${response.status}），请稍后重试。`)
  }
  const contentType = response.headers.get('content-type') ?? ''
  const markdown = await response.text()
  if (!/text\/(markdown|plain)/i.test(contentType) || !markdown.trim() || /ERR_NGROK_|^\s*<!doctype|^\s*<html/i.test(markdown)) {
    throw new Error('下载服务未返回有效报告，请刷新页面后重试。')
  }
  return markdown
}
