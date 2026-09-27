// @reinsdev/opencode — Reins for OpenCode.
// Reads the plugin's shared content at startup, the same files Claude Code
// and Codex use:
//   agents/*.md                  → subagents (access levels → OpenCode permission)
//   skills/{spec,bugfix,waive}   → /spec, /bugfix, /waive commands
//   skills/                      → added to skills.paths
// tool.execute.before forwards each tool call to the bundled spec-driven CLI,
// which decides; exit code 2 means block. chat.message forwards the user's own
// messages (prompt-submit), which is how a confirmation phrase issues a grant.
import { spawnSync } from "node:child_process"
import { readdirSync, readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const HERE = dirname(fileURLToPath(import.meta.url))
const ENTRY = join(HERE, "skills", "spec-driven-dev", "scripts", "spec-driven.py")
const COMMANDS = ["spec", "bugfix", "waive"]
const VERSION_CHECK = "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)"

const READONLY_BASH = {
  "*": "allow",
  "git commit*": "deny",
  "git push*": "deny",
  "git reset*": "deny",
  "git checkout*": "deny",
  "git restore*": "deny",
  "rm *": "deny",
}

// Same subset as spec_driven/frontmatter.py: `key: scalar` and `key: [a, b]`.
export function parseFrontmatter(text) {
  const m = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/.exec(text)
  if (!m) return [{}, text]
  const meta = {}
  const scalar = (raw) => {
    raw = raw.trim()
    if (raw.length >= 2 && raw[0] === raw.at(-1) && `"'`.includes(raw[0]))
      return raw[0] === '"' ? JSON.parse(raw) : raw.slice(1, -1)
    return raw
  }
  for (const line of m[1].split(/\r?\n/)) {
    const kv = /^([A-Za-z0-9_-]+):\s*(.*)$/.exec(line)
    if (!kv) continue
    const raw = kv[2].trim()
    meta[kv[1]] = raw.startsWith("[") && raw.endsWith("]")
      ? raw.slice(1, -1).split(",").filter((x) => x.trim()).map(scalar)
      : scalar(raw)
  }
  return [meta, m[2].replace(/^\r?\n/, "")]
}

export function permission(access) {
  const has = (...levels) => levels.some((l) => access.includes(l))
  return {
    edit: has("write", "write-own-report") ? "allow" : "deny",
    bash: has("shell") ? "allow" : has("shell-readonly") ? { ...READONLY_BASH } : "deny",
  }
}

export function loadContent(root = HERE) {
  const agents = {}
  for (const file of readdirSync(join(root, "agents")).filter((f) => f.endsWith(".md")).sort()) {
    const [meta, body] = parseFrontmatter(readFileSync(join(root, "agents", file), "utf8"))
    agents[meta.name] = {
      description: meta.description,
      mode: "subagent",
      prompt: body.trim(),
      permission: permission(meta.access || []),
      ...(meta.model ? { model: meta.model } : {}),
    }
  }
  const commands = {}
  for (const name of COMMANDS) {
    const [meta, body] = parseFrontmatter(readFileSync(join(root, "skills", name, "SKILL.md"), "utf8"))
    commands[name] = { description: meta.description, template: body.trim() + "\n\n用户输入：$ARGUMENTS" }
  }
  return { agents, commands }
}

let python // [cmd, ...args] once resolved; null when none found
function findPython() {
  if (python !== undefined) return python
  const candidates = process.platform === "win32"
    ? [["py", "-3"], ["python"], ["python3"]]
    : [["python3"], ["python"]]
  for (const [cmd, ...pre] of candidates) {
    const r = spawnSync(cmd, [...pre, "-c", VERSION_CHECK], { stdio: "ignore", windowsHide: true })
    if (!r.error && r.status === 0) return (python = [cmd, ...pre])
  }
  return (python = null)
}

function ask(event, payload) {
  const py = findPython()
  if (!py) return null // no Python: never break the user's session
  const [cmd, ...pre] = py
  const r = spawnSync(cmd, [...pre, ENTRY, "hook", event, "--runtime", "opencode"], {
    input: JSON.stringify(payload),
    encoding: "utf8",
    windowsHide: true,
    env: { ...process.env, PYTHONIOENCODING: "utf-8" },
  })
  if (r.error || r.status !== 2) return null
  return (r.stderr || "blocked by Reins").trim()
}

// Only messages the user typed in a top-level session count. A subagent session's
// first message is written by the parent model, so forwarding it would let the model
// forge a confirmation phrase; when we cannot tell, we do not forward.
async function isUserSession(client, sessionID) {
  if (!client || !sessionID) return false
  try {
    const r = await client.session.get({ path: { id: sessionID } })
    return Boolean(r && r.data) && !r.data.parentID
  } catch {
    return false
  }
}

export function userText(parts) {
  return (parts || [])
    .filter((p) => p && p.type === "text" && !p.synthetic)
    .map((p) => p.text || "")
    .join("\n")
    .trim()
}

export const ReinsPlugin = async ({ directory, client }) => ({
  config: async (cfg) => {
    const { agents, commands } = loadContent()
    // The user's own definitions win over Reins defaults.
    cfg.agent = { ...agents, ...(cfg.agent || {}) }
    cfg.command = { ...commands, ...(cfg.command || {}) }
    cfg.skills = cfg.skills || {}
    cfg.skills.paths = [...(cfg.skills.paths || []), join(HERE, "skills")]
  },
  "tool.execute.before": async (input, output) => {
    const reason = ask("pre-tool", {
      hook_event_name: "PreToolUse",
      tool_name: input.tool,
      tool_input: output.args,
      session_id: input.sessionID,
      cwd: directory,
    })
    if (reason) throw new Error(reason)
  },
  "chat.message": async (input, output) => {
    const prompt = userText(output.parts)
    if (!prompt || !(await isUserSession(client, input.sessionID))) return
    ask("prompt-submit", {
      hook_event_name: "UserPromptSubmit",
      prompt,
      session_id: input.sessionID,
      cwd: directory,
    })
  },
})
