#!/usr/bin/env node
// npx @ashusnapx/prodgate: installs the prodgate skill for Claude Code, plus the caveman and ponytail
// plugins it requires. Flags: --skip-plugins (skill only), --dir <path> (skills folder, default ~/.claude/skills).
import { cpSync, existsSync, lstatSync, readFileSync, renameSync, rmSync } from 'node:fs'
import { homedir } from 'node:os'
import { dirname, join } from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

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
  if (!isLink(dst) && existsSync(backup)) console.log(`  kept your old copy at ${backup}`)
}
cpSync(src, dst, { recursive: true })
console.log(`✓ prodgate skill installed at ${dst}`)

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
if (!missing.length) console.log('✓ caveman and ponytail already installed')
else if (flag('--skip-plugins')) console.log(`! prodgate requires ${missing.map(m => m[0]).join(' and ')}; install them before running it`)
else {
  const claude = spawnSync('claude', ['--version'], { encoding: 'utf8' })
  for (const [name, repo] of missing) {
    if (claude.status !== 0) {
      console.log(`! install ${name}: claude plugin marketplace add ${repo} && claude plugin install ${name}@${name}`)
      continue
    }
    const add = spawnSync('claude', ['plugin', 'marketplace', 'add', repo], { stdio: 'inherit' })
    const inst = add.status === 0 && spawnSync('claude', ['plugin', 'install', `${name}@${name}`], { stdio: 'inherit' })
    console.log(inst && inst.status === 0 ? `✓ ${name} installed` : `! ${name} did not install; run: claude plugin install ${name}@${name}`)
  }
}
console.log('\nRestart Claude Code, then say "/prodgate" or "run QA" in any repo.')

function isLink(p) {
  try {
    return lstatSync(p).isSymbolicLink()
  } catch {
    return false
  }
}
