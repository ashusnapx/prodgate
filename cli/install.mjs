#!/usr/bin/env node
// npx @ashusnapx/prodgate: installs the prodgate skill for Claude Code, plus the caveman and ponytail
// plugins it requires. Flags: --skip-plugins (skill only), --dir <path> (skills folder, default ~/.claude/skills).
import { cpSync, existsSync, lstatSync, readFileSync, renameSync, rmSync } from 'node:fs'
import { homedir } from 'node:os'
import { dirname, join } from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

// colour only for a person at a terminal; NO_COLOR is honoured
const tty = process.stdout.isTTY && !process.env.NO_COLOR
const rgb = (r, g, b) => t => (tty ? `\x1b[38;2;${r};${g};${b}m${t}\x1b[39m` : t)
const bold = t => (tty ? `\x1b[1m${t}\x1b[22m` : t)
const dim = t => (tty ? `\x1b[2m${t}\x1b[22m` : t)
const ok = t => console.log(`${rgb(52, 211, 153)('✓')} ${t}`)
const warn = t => console.log(`${rgb(251, 191, 36)('!')} ${t}`)
const STOPS = [[167, 139, 250], [96, 165, 250], [34, 211, 238], [52, 211, 153]]
const gradient = word =>
  [...word]
    .map((ch, i) => {
      const x = (i / Math.max(1, word.length - 1)) * (STOPS.length - 1)
      const a = STOPS[Math.floor(x)], b = STOPS[Math.min(STOPS.length - 1, Math.floor(x) + 1)], f = x - Math.floor(x)
      return rgb(...a.map((v, k) => Math.round(v + (b[k] - v) * f)))(ch)
    })
    .join('')
console.log(`\n  ${bold(gradient('◆ prodgate'))}  ${dim('state bugs, hunted until zero, proven by failing tests')}\n`)

const argv = process.argv.slice(2)
const flag = name => argv.includes(name)
const value = name => (argv.includes(name) ? argv[argv.indexOf(name) + 1] : undefined)
const home = process.env.CLAUDE_CONFIG_DIR || join(homedir(), '.claude')
const skills = value('--dir') || join(home, 'skills')
const src = join(dirname(fileURLToPath(import.meta.url)), '..', 'skills', 'prodgate')
const dst = join(skills, 'prodgate')

if (existsSync(dst) || isLink(dst)) {
  const backup = `${dst}.bak-${Date.now()}`
  if (isLink(dst)) rmSync(dst)
  else renameSync(dst, backup)
  if (!isLink(dst) && existsSync(backup)) console.log(dim(`  kept your old copy at ${backup}`))
}
cpSync(src, dst, { recursive: true })
ok(`prodgate skill installed  ${dim(dst)}`)

const PLUGINS = [
  ['caveman', 'JuliusBrussee/caveman'],
  ['ponytail', 'DietrichGebert/ponytail'],
]
const installed = name => {
  try {
    return readFileSync(join(home, 'plugins', 'installed_plugins.json'), 'utf8').includes(`"${name}@`) || existsSync(join(skills, name, 'SKILL.md'))
  } catch {
    return existsSync(join(skills, name, 'SKILL.md'))
  }
}
const missing = PLUGINS.filter(([name]) => !installed(name))
if (!missing.length) ok('caveman and ponytail already installed (every agent runs both at ultra)')
else if (flag('--skip-plugins')) warn(`prodgate requires ${missing.map(m => m[0]).join(' and ')}; install them before running it`)
else {
  const claude = spawnSync('claude', ['--version'], { encoding: 'utf8' })
  for (const [name, repo] of missing) {
    if (claude.status !== 0) {
      warn(`install ${name}: ${bold(`claude plugin marketplace add ${repo} && claude plugin install ${name}@${name}`)}`)
      continue
    }
    const add = spawnSync('claude', ['plugin', 'marketplace', 'add', repo], { stdio: 'inherit' })
    const inst = add.status === 0 && spawnSync('claude', ['plugin', 'install', `${name}@${name}`], { stdio: 'inherit' })
    inst && inst.status === 0 ? ok(`${name} installed`) : warn(`${name} did not install; run: ${bold(`claude plugin install ${name}@${name}`)}`)
  }
}
console.log(`\n  ${rgb(96, 165, 250)('→')} Restart Claude Code, then say ${bold('/prodgate')} or ${bold('"run QA"')} in any repo.\n`)

function isLink(p) {
  try {
    return lstatSync(p).isSymbolicLink()
  } catch {
    return false
  }
}
