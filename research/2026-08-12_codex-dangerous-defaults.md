# Codex Dangerous Defaults Audit

**Date:** 2026-08-12
**Topic:** codex-dangerous-defaults

## Summary

The installed Codex CLI exposes `--dangerously-bypass-approvals-and-sandbox` as the unrestricted execution flag. Zsh and Bash now route interactive agent commands through that flag by default, while administrative commands remain unchanged and `codex-safe` provides an explicit safe entry point. Codex loop shortcuts pass the unrestricted flag directly because their tmux launch path may not inherit interactive shell functions.

## Findings

### Updated entry points

- `codex`: unrestricted by default for bare prompts, `exec`, `review`, `resume`, and `fork` flows.
- `codex-safe`: invokes the real Codex binary without injecting the unrestricted flag.
- `codexd`: preserved as the resume shortcut and now inherits the `codex` default.
- `zx`: preserved as the short `codex` alias and now inherits the `codex` default.
- `loopcxb` and `loopcxf`: pass the unrestricted flag explicitly in both Zsh and Bash.

### Administrative exceptions

Login, logout, update, doctor, completion, MCP/plugin administration, app/server utilities, feature inspection, archive management, help, and version commands invoke the underlying binary without the unrestricted flag.

### Scope and activation

- Updated `/Users/ns0bj/.zshrc` and `/Users/ns0bj/.bashrc`.
- Existing terminal processes are not force-reloaded. New Zsh/Bash sessions load the behavior automatically.
- `LOOP_CODEX_CMD` remains an override for custom loop launch behavior.

## Sources

- Installed CLI: `codex-cli 0.147.0`, local `codex --help` output.
- Official Codex CLI documentation lookup attempted at `https://developers.openai.com/codex/cli/reference`; the local installed help was used as the authoritative executable contract for this machine.
- Shell configuration: `/Users/ns0bj/.zshrc`, `/Users/ns0bj/.bashrc`.
