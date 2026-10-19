# Host settings verification

Advisor 0.3.2 adds native settings declarations for Claude Code and Cursor. Both reuse the existing profile validator and default app overrides off. Installing these adapters preserves the shared configuration; enabling overrides replaces both complete profiles. ZCode retains its existing default of overrides on.

## Claude Code

The [plugin reference](https://code.claude.com/docs/en/plugins-reference) documents `userConfig`, `${user_config.KEY}` substitution, and replacement of a root `.mcp.json` server by a same-name inline manifest server. Advisor supplies the complete inline server, including all seven settings. Its neutral root `.mcp.json` is unchanged for other consumers. The effort option-picker feature is documented from Claude Code 2.1.271; the installed version tested was **2.1.301**.

No-inference checks on October 19, 2026:

- Strict package validation passed without warnings or errors.
- `plugin configure advisor@inline --values-stdin --json` accepted all seven settings in an isolated configuration directory. Test values explicitly disabled Claude and enabled `gpt-6.1-sol` at `max`.
- `mcp get plugin:advisor:advisor` connected the actual Advisor stdio server from the production package.
- A private package copy replaced only the launch command with an environment-recording wrapper. The real host resolved all seven strings correctly, including `"false"` for Claude enablement. The wrapper checked effective Advisor status, then connected the same shared stdio implementation. This verifies interpolation separately from the unmodified production command.

These commands inspect an inline package without installing it or requesting a Claude response:

```sh
claude plugin validate plugins/advisor --strict --json
claude --plugin-dir "$PWD/plugins/advisor" plugin configure advisor@inline --json
claude --plugin-dir "$PWD/plugins/advisor" mcp get plugin:advisor:advisor
```

The complete automated suite passes **279 tests on Python 3.11 and 3.12**, with resource warnings treated as errors. Ten new host-configuration tests cover declarations, opt-in precedence, disabled profiles, retained shared policy, and invalid or unresolved values. The script lock check also passes.

The `/config` GUI and an agent's consultation lifecycle were not tested. The local Claude Desktop Code tab uses its own bundled version; ordinary Desktop chat requires a separate MCP configuration or MCPB package.

## Cursor

The [plugin reference](https://cursor.com/docs/reference/plugins) documents a `variables` JSON Schema and `${VAR}` interpolation. Advisor declares seven uppercase `ADVISOR_*` variables in its Cursor manifest and forwards them only through `.cursor-plugin/mcp.json`. Boolean controls use string enums `true`/`false` because boolean-to-environment serialization is undocumented.

Team administrators configure variables through dashboard **Plugins → Configure**. Cursor is not installed on the test machine. Tests verify declarations, defaults, matching placeholders, simulated environment resolution, shared-config precedence, and invalid-value rejection. They do not establish Cursor runtime interpolation or individual/CLI UI availability.

## Other hosts

Use the shared file and guided `advisor.py configure` command until a host adapter is verified. ChatGPT's [structured settings extension](https://developers.openai.com/plugins/build/extensions) uses MCP read/update tools and server-owned persistence; it is not a manifest-to-launch-environment equivalent. Advisor does not expose a configuration-writing model tool.

Antigravity and Muse package validation currently discovers only the skill in this portable package. Grok discovers the Claude-compatible skill and neutral MCP configuration, but its native settings interpolation is undocumented. These checks do not prove automatic triggering, context capture, completion notification, or advice use. See [host compatibility](compatibility.md).

All live advice requested during this integration work used **Codex CLI, `gpt-6.1-sol`, Max effort**. Configuration checks and automated tests made no model calls. Private test settings, provider sessions, and advice remain outside Git.
