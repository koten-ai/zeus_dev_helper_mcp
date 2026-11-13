# How to test a coding agent in isolation with SBX

Test one coding agent in its own local SBX microVM, gate every new outbound host with a sandbox-scoped network approval, and install Zeus Dev Helper inside that VM so the helper process stays with the agent.

This matches `sbx` v0.51.0 on this Mac (`/opt/homebrew/bin/sbx`). An upgrade to v0.53.0 is available. Re-check `sbx <command> --help` after `brew upgrade docker/tap/sbx`. This machine already has a live policy and the sandboxes `claude-claude` and `codex-codex`. Create a new sandbox name for the test, and leave `sbx policy reset` alone.

## What the sandbox isolates

The agent runs in a microVM with its own kernel, filesystem, and Docker daemon. It can use sudo inside that VM. These are the only paths back to the Mac:

- The workspace you mount. `sbx run` and `sbx create` mount it read-write. `--clone` mounts the host repo read-only and gives the agent a private clone.
- Outbound TCP that network policy allows. The host proxy checks every connection. UDP stays blocked unless you turn that experiment on. ICMP stays blocked.
- The host MCP gateway, if you load a server into that sandbox. A local stdio server then runs on the Mac with your user privileges. That is outside the VM.
- Model and GitHub credentials, which stay in the macOS Keychain. The proxy injects them. The VM sees a sentinel such as `proxy-managed`.

## 1. Prerequisites

```bash
sbx version
sbx login
docker info >/dev/null
```

Store the model key on the host. The prompt keeps it out of shell history:

```bash
sbx secret set anthropic          # Claude
# sbx secret set openai           # Codex / OpenAI
# sbx secret set xai              # Grok / xAI
sbx secret set github --command 'gh auth token'
sbx secret ls
```

On this Mac, `zeus-dev.local` is `192.168.1.223` in `/etc/hosts`, and Zeus is the public API on port **8080**.

## 2. Create one sandbox for the agent under test

Use a scratch checkout. `--clone` keeps the host tree read-only. `--skills off` keeps the host skills store out of the VM. `--static-mcp none` starts with no host MCP servers, so the only helper is the one you install inside the VM.

```bash
mkdir -p "$HOME/sbx-agent-tests/agent-test"
cd "$HOME/sbx-agent-tests/agent-test"
git init

sbx policy ls
```

If that command tells you the network policy is not initialized, set the Balanced preset once. On this Mac it is already initialized (`default-deny-all` plus a large local allow list), so skip `init`:

```bash
sbx policy init balanced
```

Create the sandbox without opening the agent yet. Agents on this CLI: `claude`, `codex`, `copilot`, `cursor`, `devin`, `docker-agent`, `droid`, `gemini`, `kiro`, `opencode`, `shell`.

```bash
sbx create \
  --name agent-test \
  --clone \
  --skills off \
  --static-mcp none \
  --deny-network "169.254.169.254,metadata.google.internal" \
  claude .
```

`--deny-network` is per sandbox and can only narrow egress. Repeat the flag for more hosts. Confirm the row:

```bash
sbx ls
sbx policy ls agent-test
```

`exec` starts a stopped sandbox, so the next command is safe while the row says stopped.

## 3. Allow the hosts this test needs

Rules apply to TCP. A bare hostname is checked as port 443, so Zeus must be written with `:8080`. Scope every test rule to `agent-test`. A deny in any scope beats an allow. If the same scope already has the opposite decision for that host, `allow` is refused until you remove the old rule.

Check first:

```bash
sbx policy check network --sandbox agent-test --verbose pypi.org
sbx policy check network --sandbox agent-test --verbose files.pythonhosted.org
sbx policy check network --sandbox agent-test --verbose github.com
sbx policy check network --sandbox agent-test --verbose zeus-dev.local:8080
sbx policy check http --sandbox agent-test --method GET \
  http://zeus-dev.local:8080/
```

`check` does not open a connection. Allow only what came back blocked:

```bash
sbx policy allow network --sandbox agent-test \
  "pypi.org,files.pythonhosted.org,github.com,zeus-dev.local:8080"
```

`zeus-dev.local:8080` is already allowed for the existing `claude-claude` sandbox. A new sandbox does not inherit that sandbox-scoped rule. Add it again for `agent-test`.

Inside the VM, set Zeus to `http://zeus-dev.local:8080`. A request from inside the VM to the raw address `192.168.1.223:8080` gets HTTP 403 from Zeus.

## 4. Network approval

Under Balanced (`sbx policy init balanced`) and Locked Down (`deny-all`), a destination with no allow and no deny is blocked, and SBX records one approval. Open allows everything and never asks. A destination that matches a deny is blocked with no prompt.

The blocked call does not wait. Approving affects the next attempt. Retries collapse into one row.

From a second terminal while the agent or `pip` is reaching a new host:

```bash
sbx policy approval ls
```

```text
APPROVAL                                              SANDBOX     TITLE                    DETAIL                          OPTIONS
network:cWtN-4xUrNjxh4ouezcstgjrky6Rg57QfeRe3WEkyyY   agent-test  zeus-dev.local:8080      Protocol: TCP ...               allow (Allow), dismiss (Dismiss)
```

Read it, then answer with one of the option ids that row offers:

```bash
sbx policy approval inspect network:cWtN-4xUrNjxh4ouezcstgjrky6Rg57QfeRe3WEkyyY

sbx policy approval respond network:cWtN-4xUrNjxh4ouezcstgjrky6Rg57QfeRe3WEkyyY \
  --option allow
```

`dismiss` leaves it blocked. The next attempt asks again.

An approval is one exact host and port, for that sandbox only. `zeus-dev.local:8080` and `zeus-dev.local:443` are separate. `api.example.com` and `cdn.example.com` are separate. An HTTP rule that matched the request records that method and path, so `GET /v1/data` and `POST /v1/data` are separate.

Retry the command that was blocked. Then confirm the recorded rule:

```bash
sbx policy ls --wide --created-via approval
sbx policy log agent-test --limit 20
```

Remove one approval later with the rule id from `--wide`:

```bash
sbx policy rm network --sandbox agent-test --id RULE_ID
```

To refuse a host that some other rule allows:

```bash
sbx policy deny network --sandbox agent-test ads.example.com
```

Watch the proxy while the agent works:

```bash
sbx policy log agent-test
```

## 5. Install Zeus Dev Helper inside that sandbox

Install with `pip --user` as the sandbox user `agent`. `uv` and `uvx` abort in this microVM (`jemalloc` unsupported system page size). The helper needs Python 3.11 or newer, and the `[agent]` extra so `verify_local_setup` and `smoke_test_agent` can import `zeus_client`. The app `.venv` does not satisfy that check.

The pin below is the release that already came up inside `claude-claude` (`0.7.12`, 17 tools, `doctor` ok). Published helper docs currently describe source `0.7.11`. Keep one pin for the whole test.

```bash
sbx exec -u agent agent-test bash -lc 'python3 --version'

sbx exec -u agent agent-test bash -lc \
  'python3 -m pip install --user "zeus-dev-helper-mcp[agent]==0.7.12"'
```

If `pip` prints `Approval required for …`, go to section 4, allow that host, and run the same `pip` command again.

Confirm the console script and the client import:

```bash
sbx exec -u agent agent-test bash -lc '
  test -x "$HOME/.local/bin/zeus-dev-helper-mcp" && echo binary-ok
  python3 -c "import importlib.metadata as m; print(m.version(\"zeus-dev-helper-mcp\"))"
  python3 -c "import zeus_client; print(\"zeus_client\", getattr(zeus_client, \"__version__\", \"ok\"))"
'
```

Register it in Claude Code’s user scope. User scope lives in the sandbox home, which persists until `sbx rm`. Default scope `local` is tied to one project path.

```bash
sbx exec -u agent agent-test bash -lc '
  claude mcp add --scope user --transport stdio zeus-dev-helper \
    -e ZEUS_URL=http://zeus-dev.local:8080 \
    -e ZEUS_DEV_HELPER_STATE_DIR=/home/agent/.config/zeus_dev_helper \
    -- "$HOME/.local/bin/zeus-dev-helper-mcp"
  claude mcp list
'
```

For a Codex sandbox, write the server into the sandbox user’s Codex config instead of `claude mcp add`:

```bash
sbx exec -u agent agent-test bash -lc 'mkdir -p "$HOME/.codex" && cat >> "$HOME/.codex/config.toml" <<EOF
[mcp_servers.zeus-dev-helper]
command = "/home/agent/.local/bin/zeus-dev-helper-mcp"

[mcp_servers.zeus-dev-helper.env]
ZEUS_URL = "http://zeus-dev.local:8080"
ZEUS_DEV_HELPER_STATE_DIR = "/home/agent/.config/zeus_dev_helper"
EOF'
```

Codex’s own permission profile can still block DNS inside the VM after SBX has allowed the host. In that Codex config, set a profile that extends `:workspace` and enables network, and start a new thread:

```toml
default_permissions = "workspace-net"

[permissions.workspace-net]
description = "Workspace writes plus outbound network."
extends = ":workspace"

[permissions.workspace-net.network]
enabled = true
```

Open a new agent session. Claude reads MCP config at session start.

```bash
sbx run --name agent-test
```

In that session, `/mcp` should show `zeus-dev-helper` connected. Ask the agent to call `doctor`, then `start_project` only after `doctor` is ok. State for this in-VM install is `/home/agent/.config/zeus_dev_helper`.

Helper order, once it is connected: `doctor` → `set_prereq` with the Zeus URL the user named → `start_project` → `next_step`. Public API stays on `:8080`. Passwords, bearer tokens, and LLM keys stay out of tool arguments. The helper writes a mode `600` env file.

## 6. Run the isolation test

Give the agent a task that has to edit code, install a package, and call Zeus. In a second terminal:

```bash
sbx policy log agent-test --limit 50
sbx exec -u agent agent-test bash -lc 'curl -sS -o /dev/null -w "%{http_code}\n" http://zeus-dev.local:8080/'
git -C "$HOME/sbx-agent-tests/agent-test" status
```

With `--clone`, the host worktree stays clean. The agent’s commits are on the host remote `sandbox-agent-test`. A direct mount would show edits in the host tree immediately, including files `git diff` does not show, such as `.git/hooks`.

A server the agent binds inside the VM is reachable on the Mac only after you publish the port at create time, for example `-p 127.0.0.1:5000:5000`.

## 7. Host gateway, when the helper should run on the Mac

`sbx mcp load` attaches a registered server to one sandbox. The process is still a host stdio process. Use a new registration name and a private state directory so it does not share `claude-claude` or `codex-codex` state. Skip this section if you already installed the helper inside the VM. Loading both shows the same tools twice.

`sbx mcp add` has no `--env` flag. Put the variables in front of `uvx` via `/usr/bin/env`. On the host, `uvx` is fine. This is the shape already registered for the other two sandboxes:

```bash
UVX="$(command -v uvx)"
mkdir -p "$HOME/.config/zeus_dev_helper-agent-test"

sbx mcp add zeus-dev-helper-agent-test \
  --command /usr/bin/env \
  --args "ZEUS_URL=http://zeus-dev.local:8080,ZEUS_DEV_HELPER_STATE_DIR=$HOME/.config/zeus_dev_helper-agent-test,$UVX,--isolated,--from,zeus-dev-helper-mcp[agent]==0.7.12,zeus-dev-helper-mcp"

sbx mcp inspect zeus-dev-helper-agent-test
sbx mcp load zeus-dev-helper-agent-test --sandbox agent-test
```

`load` works on a running sandbox, and the agent gets `tools/list_changed`. A stopped sandbox receives the server the next time it starts. Claude’s `/mcp` screen lists gateway servers as one entry, `mcp-gateway`, so `zeus-dev-helper-agent-test` does not appear there as its own row. Start a new Claude session after the load so `/mcp` refreshes.

```bash
sbx mcp unload zeus-dev-helper-agent-test --sandbox agent-test
sbx mcp rm zeus-dev-helper-agent-test
```

The existing registrations `zeus-dev-helper` and `zeus-dev-helper-codex` already point at their own state dirs and `ZEUS_URL=http://192.168.1.223:8080`. Leave them in place.

## Best practices

- One sandbox name per agent under test. `sbx run --name agent-test` reattaches. A second agent gets its own name and its own helper state directory.
- Pass `--clone`, `--skills off`, and `--static-mcp none` at creation. Those flags are ignored on a later reattach.
- Keep the global preset on Balanced or Locked Down. Open (`allow-all`) never asks for approval, so it is a poor isolation test.
- Pre-allow `pypi.org`, `files.pythonhosted.org`, `github.com`, and `zeus-dev.local:8080` for that sandbox. Let unfamiliar hosts raise an approval, and answer them with `sbx policy approval respond … --option allow` or `dismiss`.
- Scope allows and denies with `--sandbox`. A deny beats an allow. Add denies for link-local metadata addresses at create time with `--deny-network`.
- Read `sbx policy log <name>` during the run. The approval you grant does not revive the call that was blocked. Run that call again.
- Keep API keys in `sbx secret set`. Do not pass them with `sbx run -e`.
- Inside the VM, install the helper with `pip --user` and pin `zeus-dev-helper-mcp[agent]`. Point `ZEUS_URL` at `http://zeus-dev.local:8080`.
- Give every sandbox its own `ZEUS_DEV_HELPER_STATE_DIR`.
- Treat a host-gateway helper as a trusted host program. Use the in-VM install when the test is supposed to include the helper inside the boundary.
- Publish only the ports you intend to open, bound to `127.0.0.1`.
- For a script, pass `--no-input`. Initialize policy and register MCP before `sbx run`, because `--no-input` fails instead of prompting.
- `sbx exec` starts a stopped sandbox. `sbx stop agent-test` keeps the VM disk. `sbx rm agent-test` deletes that disk, including the in-VM pip install and `/home/agent/.config/zeus_dev_helper`. The host worktree and host Keychain secrets remain.
- Review the `sandbox-agent-test` git remote before copying any commit back to the host.

## Clean up

```bash
sbx stop agent-test
sbx rm agent-test
sbx policy rm network --sandbox agent-test --resource zeus-dev.local:8080
sbx ls
sbx policy approval ls
```

Removing the sandbox also removes rules that were scoped to it.
