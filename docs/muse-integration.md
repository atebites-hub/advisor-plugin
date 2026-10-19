# Muse Code integration

Advisor's portable root manifest takes precedence over native overlays in Muse. Installing `plugins/advisor` directly discovers skills but does not activate its MCP server or hooks. Export a separate native package instead; the repository remains a marketplace with one plugin, `advisor`.

## Export and install

Run from this checkout with Python 3.11+ available through `uv`:

```sh
uv run --python 3.11 python scripts/export_muse.py /absolute/new/advisor-muse
muse plugins validate /absolute/new/advisor-muse --json
muse plugins install /absolute/new/advisor-muse --scope user
muse plugins inspect advisor --json
```

The destination must be new, outside the checkout, with an existing parent directory. Existing files, directories, and symlinks are never replaced. The exporter copies eight public runtime/skill files and writes one native manifest last. It excludes credentials, configuration, consultation state, Git metadata, caches, and other hosts' manifests. Paths are relocatable; the installed cache does not need the original checkout to run.

Only install after a successful export. Publication is not atomic: a failed write leaves partial output for inspection. Inspect that directory yourself and choose a new destination for the next export. The exporter never removes it or installs anything automatically.

Inspect the declared capabilities before approving them:

```sh
muse plugins approve advisor --json
```

Start a fresh Muse session. The package declares two skills, `advisor` and `advisor-setup`, a `SessionStart` instruction hook, and the `advisor` stdio MCP server. `uv` must be on Muse's executable search path. Initial dependency resolution can take longer than the hook's ten-second limit; retry with a fresh session after resolving runtime prerequisites.

## Configure and use

Use the existing shared wizard before starting the session:

```sh
uv run --script /absolute/new/advisor-muse/advisor.py configure
```

Native Muse plugin processes remove custom `ADVISOR_*` environment variables, so this route uses `~/.config/advisor/config.json`. The setup skill guides the same wizard; it does not add a native settings panel. A custom configuration path requires the [manual MCP route](compatibility.md#manual-mcp-setup). Compare effective profiles and configuration source with `advisor_status` before consulting. Executable discovery does not verify authentication or model access.

The hook supplies instructions; the working agent chooses one enabled advisor and invokes it. Supply explicit workspace, host, stable session/task IDs, question, stage, and relevant context. Retrieve the original result with `read_advice` and evaluate it before dependent work. Poll existing jobs using `poll_after_seconds`; Muse has no verified completion notification or automatic transcript transfer. ZCode's edit holds and final-review enforcement are not supplied here.

## Verification boundaries

Muse Code **1.4.9** passed native installation, approval, startup-hook execution, unchanged package hashes, and a TUI `/mcp` connection exposing all three tools. Its separate `mcpServer/list` response was empty, so use the native TUI connection state rather than that projection alone. See [host settings verification](host-settings.md) and [native acceptance](harness-acceptance.md#muse-code).

A single real working-model request to `muse-spark-1.3-contributor` failed before any output with HTTP 402 billing verification. No Advisor job or fixture edit occurred. The billing-failed request and the later correctly approved TUI check are separate evidence; host-routed tool invocation and autonomous advice use remain unverified until the account can run its working model. Advisor's Codex advising subscription does not supply Muse's working-model access.

Package validation establishes declared capabilities; connection establishes transport. Neither proves consultation, advice application, or account/model access. Inspect current diagnostics after execution.

Advisor's direct-script entry point disables bytecode generation so runtime imports leave installed package files unchanged. It does not delete caches from earlier experimental bundles. Export and install a fresh bundle rather than treating an already changed cache as approved.

Muse's [compatibility rules](https://meta-models.github.io/muse-code-sdk/next/guides/plugins/concepts/compatibility/) and [MCP settings](https://meta-models.github.io/muse-code-sdk/next/guides/extend/mcp-servers/) describe the underlying host routes.
