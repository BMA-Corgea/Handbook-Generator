"""
tests/test_llm_router.py

Unit tests for server/llm_router.py.
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch, mock_open

import pytest

import server.llm_router as llm_router
from server.llm_router import (
    AuthFailure,
    ClaudeCLIProvider,
    CodexCLIProvider,
    GrokClientAdapter,
    ProviderError,
    QuotaExhausted,
    _detect_provider_error,
    _resolve_bin,
    infer,
)


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------

def test_quota_exhausted_is_provider_error():
    assert issubclass(QuotaExhausted, ProviderError)

def test_auth_failure_is_provider_error():
    assert issubclass(AuthFailure, ProviderError)

def test_provider_error_is_exception():
    assert issubclass(ProviderError, Exception)


# ---------------------------------------------------------------------------
# _resolve_bin
# ---------------------------------------------------------------------------

def test_resolve_bin_uses_env_var(tmp_path, monkeypatch):
    fake_bin = tmp_path / "claude"
    fake_bin.touch()
    monkeypatch.setenv("HANDBOOK_CLAUDE_BIN", str(fake_bin))
    result = _resolve_bin("claude", "HANDBOOK_CLAUDE_BIN")
    assert result == str(fake_bin)


def test_resolve_bin_env_var_missing_file(tmp_path, monkeypatch):
    monkeypatch.setenv("HANDBOOK_CLAUDE_BIN", str(tmp_path / "nonexistent"))
    with pytest.raises(RuntimeError, match="does not exist"):
        _resolve_bin("claude", "HANDBOOK_CLAUDE_BIN")


def test_resolve_bin_uses_path(monkeypatch):
    monkeypatch.delenv("HANDBOOK_CLAUDE_BIN", raising=False)
    with patch("shutil.which", return_value="/usr/local/bin/claude") as mock_which:
        result = _resolve_bin("claude", "HANDBOOK_CLAUDE_BIN")
    mock_which.assert_called_once_with("claude")
    assert result == "/usr/local/bin/claude"


def test_resolve_bin_uses_login_shell_fallback(monkeypatch):
    monkeypatch.delenv("HANDBOOK_CLAUDE_BIN", raising=False)
    with patch("shutil.which", return_value=None), \
         patch("subprocess.check_output", return_value="/home/user/.nvm/bin/claude\n") as mock_co:
        result = _resolve_bin("claude", "HANDBOOK_CLAUDE_BIN")
    assert result == "/home/user/.nvm/bin/claude"


def test_resolve_bin_returns_none_when_not_found(monkeypatch):
    monkeypatch.delenv("HANDBOOK_CLAUDE_BIN", raising=False)
    with patch("shutil.which", return_value=None), \
         patch("subprocess.check_output", side_effect=FileNotFoundError):
        result = _resolve_bin("claude", "HANDBOOK_CLAUDE_BIN")
    assert result is None


def test_resolve_bin_env_var_takes_precedence_over_path(tmp_path, monkeypatch):
    """Env var path wins even when shutil.which would also find something."""
    fake_bin = tmp_path / "claude"
    fake_bin.touch()
    monkeypatch.setenv("HANDBOOK_CLAUDE_BIN", str(fake_bin))
    with patch("shutil.which", return_value="/usr/bin/claude") as mock_which:
        result = _resolve_bin("claude", "HANDBOOK_CLAUDE_BIN")
    mock_which.assert_not_called()
    assert result == str(fake_bin)


# ---------------------------------------------------------------------------
# _detect_provider_error
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("stderr", ["rate limit exceeded", "429 Too Many Requests", "too many requests"])
def test_detect_quota_exhausted(stderr):
    with pytest.raises(QuotaExhausted):
        _detect_provider_error(stderr, 1)


@pytest.mark.parametrize("stderr", ["not logged in", "unauthorized access", "401 Unauthorized", "authentication failed"])
def test_detect_auth_failure(stderr):
    with pytest.raises(AuthFailure):
        _detect_provider_error(stderr, 1)


def test_detect_no_error_on_clean_stderr():
    _detect_provider_error("everything is fine", 0)  # should not raise


# ---------------------------------------------------------------------------
# ClaudeCLIProvider
# ---------------------------------------------------------------------------

def test_claude_provider_success(monkeypatch):
    monkeypatch.delenv("HANDBOOK_CLAUDE_BIN", raising=False)
    with patch.object(llm_router, "_resolve_bin", return_value="/usr/bin/claude"), \
         patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="  hello world  ", stderr="", returncode=0)
        result = ClaudeCLIProvider().infer("test prompt")
    assert result == "hello world"
    cmd = mock_run.call_args[0][0]
    assert cmd == ["/usr/bin/claude", "--print"]
    assert mock_run.call_args[1]["input"] == "test prompt"


def test_claude_provider_raises_when_bin_not_found():
    with patch.object(llm_router, "_resolve_bin", return_value=None):
        with pytest.raises(ProviderError, match="claude binary not found"):
            ClaudeCLIProvider().infer("prompt")


def test_claude_provider_raises_on_nonzero_exit():
    with patch.object(llm_router, "_resolve_bin", return_value="/usr/bin/claude"), \
         patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="", stderr="something went wrong", returncode=1)
        with pytest.raises(ProviderError):
            ClaudeCLIProvider().infer("prompt")


def test_claude_provider_raises_quota_on_rate_limit():
    with patch.object(llm_router, "_resolve_bin", return_value="/usr/bin/claude"), \
         patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="", stderr="rate limit exceeded", returncode=1)
        with pytest.raises(QuotaExhausted):
            ClaudeCLIProvider().infer("prompt")


# ---------------------------------------------------------------------------
# CodexCLIProvider
# ---------------------------------------------------------------------------

def test_codex_provider_success(tmp_path):
    fake_out = tmp_path / "out.txt"
    fake_out.write_text("codex response")

    with patch.object(llm_router, "_resolve_bin", return_value="/usr/bin/codex"), \
         patch("tempfile.NamedTemporaryFile") as mock_ntf, \
         patch("subprocess.run") as mock_run, \
         patch("builtins.open", mock_open(read_data="codex response")), \
         patch("pathlib.Path.unlink"):
        mock_ntf.return_value.__enter__.return_value.name = str(fake_out)
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
        result = CodexCLIProvider().infer("test prompt")

    assert result == "codex response"
    cmd = mock_run.call_args[0][0]
    assert "codex" in cmd[0]
    assert "exec" in cmd
    assert "--ephemeral" in cmd
    assert "--sandbox" in cmd
    assert "read-only" in cmd
    assert "--output-last-message" in cmd
    assert "-" in cmd
    assert mock_run.call_args[1]["input"] == "test prompt"


def test_codex_provider_raises_when_bin_not_found():
    with patch.object(llm_router, "_resolve_bin", return_value=None):
        with pytest.raises(ProviderError, match="codex binary not found"):
            CodexCLIProvider().infer("prompt")


# ---------------------------------------------------------------------------
# GrokClientAdapter
# ---------------------------------------------------------------------------

def test_grok_adapter_raises_not_implemented():
    with pytest.raises(NotImplementedError, match="Grok not configured"):
        GrokClientAdapter().infer("anything")


def test_grok_adapter_no_required_args():
    # Must be constructible without arguments
    adapter = GrokClientAdapter()
    assert adapter is not None


# ---------------------------------------------------------------------------
# top-level infer() — provider failover
# ---------------------------------------------------------------------------

def test_infer_uses_first_provider(monkeypatch):
    monkeypatch.setenv("HANDBOOK_LLM_PROVIDERS", "claude,codex")
    with patch.object(ClaudeCLIProvider, "infer", return_value="from claude") as mock_claude:
        result = infer("hello")
    assert result == "from claude"
    mock_claude.assert_called_once_with("hello")


def test_infer_fails_over_to_codex_on_provider_error(monkeypatch):
    monkeypatch.setenv("HANDBOOK_LLM_PROVIDERS", "claude,codex")
    with patch.object(ClaudeCLIProvider, "infer", side_effect=ProviderError("down")), \
         patch.object(CodexCLIProvider, "infer", return_value="from codex"):
        result = infer("hello")
    assert result == "from codex"


def test_infer_fails_over_on_timeout(monkeypatch):
    monkeypatch.setenv("HANDBOOK_LLM_PROVIDERS", "claude,codex")
    with patch.object(ClaudeCLIProvider, "infer", side_effect=subprocess.TimeoutExpired("claude", 10)), \
         patch.object(CodexCLIProvider, "infer", return_value="from codex"):
        result = infer("hello")
    assert result == "from codex"


def test_infer_raises_runtime_error_when_all_fail(monkeypatch):
    monkeypatch.setenv("HANDBOOK_LLM_PROVIDERS", "claude,codex")
    with patch.object(ClaudeCLIProvider, "infer", side_effect=ProviderError("claude down")), \
         patch.object(CodexCLIProvider, "infer", side_effect=ProviderError("codex down")):
        with pytest.raises(RuntimeError, match="All inference providers failed"):
            infer("hello")


def test_infer_raises_runtime_error_when_no_providers_configured(monkeypatch):
    monkeypatch.setenv("HANDBOOK_LLM_PROVIDERS", "")
    with pytest.raises(RuntimeError, match="No valid inference providers configured"):
        infer("hello")


def test_infer_default_provider_order_is_claude_then_codex(monkeypatch):
    monkeypatch.delenv("HANDBOOK_LLM_PROVIDERS", raising=False)
    call_order = []

    def mock_claude_infer(self, prompt):
        call_order.append("claude")
        raise ProviderError("down")

    def mock_codex_infer(self, prompt):
        call_order.append("codex")
        return "ok"

    with patch.object(ClaudeCLIProvider, "infer", mock_claude_infer), \
         patch.object(CodexCLIProvider, "infer", mock_codex_infer):
        result = infer("test")

    assert call_order == ["claude", "codex"]
    assert result == "ok"


def test_grok_not_in_default_providers(monkeypatch):
    monkeypatch.delenv("HANDBOOK_LLM_PROVIDERS", raising=False)
    assert "grok" not in llm_router._provider_order()


def test_infer_quota_exhaustion_on_claude_failsover_to_codex(monkeypatch):
    """AC3: quota exhaustion stderr on claude triggers QuotaExhausted and failover to codex."""
    monkeypatch.setenv("HANDBOOK_LLM_PROVIDERS", "claude,codex")
    with patch.object(ClaudeCLIProvider, "infer", side_effect=QuotaExhausted("rate limit exceeded")), \
         patch.object(CodexCLIProvider, "infer", return_value="codex fallback") as mock_codex:
        result = infer("hello")
    assert result == "codex fallback"
    mock_codex.assert_called_once_with("hello")


def test_infer_auth_failure_on_claude_failsover_to_codex(monkeypatch):
    """AC4: auth failure stderr on claude triggers AuthFailure and failover to codex."""
    monkeypatch.setenv("HANDBOOK_LLM_PROVIDERS", "claude,codex")
    with patch.object(ClaudeCLIProvider, "infer", side_effect=AuthFailure("not logged in")), \
         patch.object(CodexCLIProvider, "infer", return_value="codex fallback") as mock_codex:
        result = infer("hello")
    assert result == "codex fallback"
    mock_codex.assert_called_once_with("hello")


def test_infer_codex_only_provider_skips_claude(monkeypatch):
    """AC6: HANDBOOK_LLM_PROVIDERS=codex causes claude to be skipped entirely."""
    monkeypatch.setenv("HANDBOOK_LLM_PROVIDERS", "codex")
    with patch.object(ClaudeCLIProvider, "infer") as mock_claude, \
         patch.object(CodexCLIProvider, "infer", return_value="codex only") as mock_codex:
        result = infer("hello")
    assert result == "codex only"
    mock_claude.assert_not_called()
    mock_codex.assert_called_once_with("hello")
