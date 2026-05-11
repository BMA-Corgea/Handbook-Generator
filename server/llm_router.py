"""
Subscription-backed LLM router for the Handbook Generator.

infer(prompt) — pure text generation; tries providers in order, fails over on errors.

Provider order: HANDBOOK_LLM_PROVIDERS (default: claude,codex)

Environment variables:
  HANDBOOK_CLAUDE_BIN               — explicit path to claude binary
  HANDBOOK_CODEX_BIN                — explicit path to codex binary
  HANDBOOK_LLM_PROVIDERS            — comma-separated provider order (default: claude,codex)
  HANDBOOK_INFERENCE_TIMEOUT_SECONDS — per-provider timeout (default: 120)
"""
from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import tempfile
import warnings
from pathlib import Path

_raw_timeout = os.environ.get("HANDBOOK_INFERENCE_TIMEOUT_SECONDS", "120")
try:
    _INFERENCE_TIMEOUT = int(_raw_timeout)
except ValueError:
    raise ValueError(
        f"HANDBOOK_INFERENCE_TIMEOUT_SECONDS must be an integer, got {_raw_timeout!r}"
    )


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ProviderError(Exception):
    """A provider failed in a way that warrants trying the next one."""

class QuotaExhausted(ProviderError):
    pass

class AuthFailure(ProviderError):
    pass


# ---------------------------------------------------------------------------
# Binary resolution
# ---------------------------------------------------------------------------

def _resolve_bin(name: str, env_var: str) -> str | None:
    """Return the binary path or None. Prefers env var, then PATH, then login shell."""
    explicit = os.environ.get(env_var, "").strip()
    if explicit:
        if not Path(explicit).is_file():
            raise RuntimeError(f"{env_var}={explicit!r} does not exist")
        return explicit

    found = shutil.which(name)
    if found:
        return found

    try:
        out = subprocess.check_output(
            ["bash", "-lc", f"which {shlex.quote(name)}"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        if out:
            return out
    except Exception:
        pass

    return None


# ---------------------------------------------------------------------------
# Provider error detection
# ---------------------------------------------------------------------------

def _detect_provider_error(stderr: str, returncode: int) -> None:
    """Raise a ProviderError subclass if stderr signals a recoverable fault."""
    low = (stderr or "").lower()
    if any(x in low for x in ("rate limit", "429", "too many requests")):
        raise QuotaExhausted(stderr[:200])
    if any(x in low for x in ("not logged in", "unauthorized", "401", "authentication failed")):
        raise AuthFailure(stderr[:200])


# ---------------------------------------------------------------------------
# Provider adapters
# ---------------------------------------------------------------------------

class ClaudeCLIProvider:
    def infer(self, prompt: str) -> str:
        claude_bin = _resolve_bin("claude", "HANDBOOK_CLAUDE_BIN")
        if not claude_bin:
            raise ProviderError("claude binary not found")

        result = subprocess.run(
            [claude_bin, "--print"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=_INFERENCE_TIMEOUT,
            check=False,
        )
        _detect_provider_error(result.stderr, result.returncode)
        output = result.stdout.strip()
        if result.returncode != 0 or not output:
            raise ProviderError(
                f"claude exited {result.returncode} — {(result.stderr or '').strip()[-300:]}"
            )
        return output


class CodexCLIProvider:
    def infer(self, prompt: str) -> str:
        codex_bin = _resolve_bin("codex", "HANDBOOK_CODEX_BIN")
        if not codex_bin:
            raise ProviderError("codex binary not found")

        out_path = None
        try:
            with tempfile.NamedTemporaryFile("r+", suffix=".txt", delete=False) as f:
                out_path = f.name

            result = subprocess.run(
                [
                    codex_bin, "exec",
                    "--ephemeral", "--skip-git-repo-check",
                    "--sandbox", "read-only",
                    "--output-last-message", out_path,
                    "-",
                ],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=_INFERENCE_TIMEOUT,
                check=False,
            )
            with open(out_path, encoding="utf-8") as f:
                output = f.read().strip()

            _detect_provider_error(result.stderr, result.returncode)
            if result.returncode != 0 or not output:
                raise ProviderError(
                    f"codex exited {result.returncode} — {(result.stderr or '').strip()[-300:]}"
                )
            return output

        finally:
            if out_path:
                Path(out_path).unlink(missing_ok=True)


class GrokClientAdapter:
    def infer(self, prompt: str) -> str:
        raise NotImplementedError("Grok not configured")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_PROVIDER_CLASSES: dict[str, type] = {
    "claude": ClaudeCLIProvider,
    "codex":  CodexCLIProvider,
}


def _provider_order() -> list[str]:
    raw = os.environ.get("HANDBOOK_LLM_PROVIDERS", "claude,codex")
    names = [p.strip() for p in raw.split(",") if p.strip()]
    unknown = [p for p in names if p not in _PROVIDER_CLASSES]
    if unknown:
        warnings.warn(
            f"Unknown LLM provider(s) in HANDBOOK_LLM_PROVIDERS will be ignored: {unknown}",
            stacklevel=2,
        )
    return [p for p in names if p in _PROVIDER_CLASSES]


def infer(prompt: str) -> str:
    """
    Inference entry point for all LLM calls in the Handbook Generator.

    Tries providers in HANDBOOK_LLM_PROVIDERS order (default: claude then codex).
    Fails over on ProviderError or TimeoutExpired. Raises RuntimeError if all fail.
    """
    providers = _provider_order()
    if not providers:
        raise RuntimeError(
            "No valid inference providers configured. "
            "Set HANDBOOK_LLM_PROVIDERS=claude,codex (or either alone)."
        )

    last_err: Exception | None = None
    for name in providers:
        try:
            return _PROVIDER_CLASSES[name]().infer(prompt)
        except (ProviderError, subprocess.TimeoutExpired) as exc:
            last_err = exc
            continue
        except OSError as exc:
            last_err = ProviderError(f"{name} binary unavailable: {exc}")
            continue

    raise RuntimeError(f"All inference providers failed. Last: {last_err}")
