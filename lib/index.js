/**
 * dsh-plugin-advisor — host half.
 *
 * Registers the `find_dsh_plugins` model tool: natural-language plugin
 * discovery backed by a bundled quality-scored index (daily-refreshed snapshot
 * of the whole dsh-plugin topic) plus an optional live `gh search` pass.
 * Zero network LLM calls: recommendation ranking is rule-based and free;
 * the agent's own turn does the reasoning.
 */
import { readFileSync } from 'node:fs'
import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import { rank, tokenize } from './score.js'

const execFileP = promisify(execFile)

const TOOL_DESCRIPTION = [
  'Find and recommend DeepSeek Harness (DSH) plugins for the user.',
  'Use this tool when the user asks to find / recommend / discover / install a DSH plugin,',
  'or describes a capability they want (e.g. "给纯文本模型读图", "想要终端界面", "手机上看会话").',
  'Ranking is rule-based over a daily quality-scored index of the whole dsh-plugin GitHub topic,',
  'plus a live GitHub search pass when the gh CLI is available.',
  'How to answer: present the top 2-3 matches in the user\'s language (default Chinese),',
  'with one line each explaining WHY it matches (cluster + quality + installable + license risk),',
  'and the install command. Warn when license is NOASSERTION/none or quality is low.',
  'Do NOT run the install command yourself unless the user explicitly asks you to install.',
].join(' ')

let cachedIndex = null
let cachedMeta = null

function loadIndex() {
  if (cachedIndex !== null) return cachedIndex
  try {
    const raw = readFileSync(new URL('../data/index.json', import.meta.url), 'utf8')
    cachedIndex = JSON.parse(raw)
  } catch {
    cachedIndex = []
  }
  return cachedIndex
}

function loadMeta() {
  if (cachedMeta !== null) return cachedMeta
  try {
    const raw = readFileSync(new URL('../data/meta.json', import.meta.url), 'utf8')
    cachedMeta = JSON.parse(raw)
  } catch {
    cachedMeta = {}
  }
  return cachedMeta
}

/** Best-effort live search through the user's gh CLI (their own rate limit, no API key needed). */
async function liveSearch(query) {
  try {
    const { stdout } = await execFileP('gh', [
      'search', 'repos', 'topic:dsh-plugin', query,
      '--limit', '20',
      '--json', 'fullName,stargazersCount,description,language,updatedAt,url',
    ], { timeout: 20000, maxBuffer: 4 * 1024 * 1024 })
    return JSON.parse(stdout).map((r) => ({
      full_name: r.fullName,
      stars: r.stargazersCount,
      desc: r.description || '',
      language: r.language,
      updated: (r.updatedAt || '').slice(0, 10),
      url: r.url,
      quality: 45,
      cluster: null,
      license: null,
      installable: false,
      flags: ['live-unverified'],
    }))
  } catch {
    return []
  }
}

function resultOf(p, indexRecord) {
  const flags = [...(p.flags || [])]
  if (indexRecord === undefined) flags.push('未收录')
  const warn = flags.length ? flags.join('/') : ''
  return {
    full_name: p.full_name,
    url: p.url,
    stars: p.stars,
    quality: Math.round(p.quality),
    cluster: p.cluster || null,
    language: p.language || null,
    license: p.license || null,
    installable: Boolean(p.installable),
    updated: p.updated || null,
    flags,
    warn,
    desc: (p.desc || '').slice(0, 200),
    install_cmd: p.installable
      ? `dsh plugin --profile web add -w github:${p.full_name}`
      : null,
    why: `功能位:${p.cluster || '未分类'} | 质量分:${Math.round(p.quality)} | ${p.installable ? '声明可安装(dsh.bundle)' : '未声明可安装'}${warn ? ' | 风险:' + warn : ''}`,
  }
}

export const name = 'dsh-plugin-advisor'
export const inject = ['tools']

export function apply(ctx) {
  ctx.tools.register({
    name: 'find_dsh_plugins',
    description: TOOL_DESCRIPTION,
    parameters: {
      type: 'object',
      additionalProperties: false,
      properties: {
        query: {
          type: 'string',
          description: 'User\'s need in natural language (Chinese or English), e.g. "给纯文本模型读图片的能力", "手机上查看会话进度", "Claude Code 风格的终端界面".',
        },
        limit: {
          type: 'number',
          description: 'Max results to return (default 5, max 10).',
        },
        installable_only: {
          type: 'boolean',
          description: 'Return only plugins that declare a dsh.bundle manifest and can be installed with dsh plugin add. Default false.',
        },
      },
      required: ['query'],
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          query: { type: 'string' },
          data_date: { type: 'string' },
          total_indexed: { type: 'integer' },
          live: { type: 'boolean' },
          results: {
            type: 'array',
            items: {
              type: 'object',
              additionalProperties: true,
              properties: {
                full_name: { type: 'string' },
                url: { type: 'string' },
                stars: { type: 'integer' },
                quality: { type: 'integer' },
                cluster: { type: 'string' },
                license: { type: 'string' },
                installable: { type: 'boolean' },
                updated: { type: 'string' },
                warn: { type: 'string' },
                desc: { type: 'string' },
                install_cmd: { type: 'string' },
                why: { type: 'string' },
              },
            },
          },
        },
      },
      render: (_args, value) => [{
        type: 'text',
        text: (value.results || []).map((r) =>
          `- ${r.full_name} ★${r.stars} Q${r.quality} [${r.cluster || '未分类'}] ${r.license || '无许可'}${r.warn ? ' ⚠' + r.warn : ''}\n  ${r.desc}\n  ${r.install_cmd || '(未声明可安装)'}`).join('\n'),
      }],
    },
    async execute(args) {
      const query = String(args.query || '').trim()
      const limit = Math.min(10, Math.max(1, Math.trunc(args.limit) || 5))
      if (!query) throw new Error('invalid query: expected a non-empty string')

      const index = loadIndex()
      const byName = new Map(index.map((p) => [p.full_name.toLowerCase(), p]))
      const candidates = [...index]
      let live = false

      const liveRows = await liveSearch(query)
      for (const r of liveRows) {
        live = true
        if (byName.has(r.full_name.toLowerCase())) continue
        candidates.push(r)
      }

      let pool = rank(query, candidates, 40)
      if (args.installable_only) pool = pool.filter((p) => p.installable)
      const results = pool.slice(0, limit).map((p) => resultOf(p, byName.get(p.full_name.toLowerCase())))

      return {
        query,
        data_date: loadMeta().date || 'unknown',
        total_indexed: index.length,
        live,
        results,
      }
    },
  })
  ctx.logger.info('[dsh-plugin-advisor] find_dsh_plugins tool registered')
}
