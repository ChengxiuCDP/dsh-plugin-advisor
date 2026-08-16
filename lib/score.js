/**
 * dsh-plugin-advisor — ranking primitives (pure functions, no imports).
 * Ported from the dsh-plugin-hub recommend endpoint so plugin and site share one ranking logic.
 */

const ALIASES = {
  '手机': '移动', '移动端': '移动', '手机上': '移动', '远程': '移动',
  '图片': '视觉', '看图': '视觉', '读图': '视觉', '截图': '视觉',
  '语音': '语音', '说话': '语音', '口述': '语音',
  '桌面': '桌面', '窗口': '桌面',
  '终端': '终端', '命令行': '终端',
  '余额': '余额', '费用': '余额', '花费': '余额', '用量': '余额', 'token': '余额',
  '审批': '审批', '批准': '审批',
  '宠物': '宠物', '吉祥物': '宠物',
  '主题': '主题', '皮肤': '主题',
  '记忆': '上下文', '上下文': '上下文',
  '任务': '任务', '待办': '任务',
  '分享': '分享', '导出': '分享',
  '模型': '模型', '供应商': '模型', 'api': '模型',
  '技能': '技能', '预设': '技能',
  '市场': '市场', '安装': '市场',
  '通知': '通知', '推送': '通知',
  '质量': '质量', '评审': '质量', '审查': '质量',
  '引导': '引导', '新手': '引导',
}

export function tokenize(text) {
  const t = String(text || '').toLowerCase()
  const out = []
  for (const m of t.matchAll(/[a-z0-9][a-z0-9._/-]*/g)) out.push(m[0])
  for (const m of t.matchAll(/[\u4e00-\u9fff]+/g)) {
    const run = m[0]
    out.push(run)
    for (let i = 0; i + 1 < run.length; i++) out.push(run.slice(i, i + 2))
  }
  return out.filter((x) => x.length >= 2)
}

function clusterHit(cluster, token) {
  const c = String(cluster || '').toLowerCase()
  if (c.includes(token)) return true
  const alias = ALIASES[token]
  return alias !== undefined && c.includes(alias)
}

/**
 * Score one candidate against a natural-language query.
 * p: { full_name, desc, cluster, quality, stars }
 */
export function scoreCandidate(p, query, tokens = tokenize(query)) {
  const text = (p.full_name + ' ' + (p.desc || '')).toLowerCase()
  let s = (p.quality || 40) / 100 * 55
  let hits = 0
  for (const t of tokens) {
    if (text.includes(t)) { s += 13; hits++ }
    if (p.cluster && clusterHit(p.cluster, t)) { s += 11; hits++ }
  }
  if (hits >= 2) s += 12
  s += Math.min(15, Math.log10((p.stars || 0) + 1) * 3)
  return s
}

export function rank(query, candidates, limit = 5) {
  const tokens = tokenize(query)
  return candidates
    .map((p) => ({ p, s: scoreCandidate(p, query, tokens) }))
    .sort((a, b) => b.s - a.s)
    .slice(0, limit)
    .map((x) => x.p)
}
