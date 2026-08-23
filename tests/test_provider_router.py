"""
Tests for litellm_providers/provider_router.py IBM provider integration.

Covers:
- Dynamic discovery from /chat-models endpoint
- Fallback static list when discovery fails
- Provider entry structure
- Environment variable handling
- Runtime appending of discovered models
"""
import os
import sys
import time
import json
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from litellm_providers.provider_router import (
    _fetch_ibm_chat_models,
    _get_available_providers,
    get_configured_providers,
    get_llm,
    PROVIDERS,
    IBM_ADVANTAGE_BASE_URL,
    IBM_CHAT_MODELS_URL,
    _refresh_ibm_models,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _clear_ibm_cache():
    _refresh_ibm_models()


def _set_ibm_key(key: str):
    os.environ["IBM_ADVANTAGE_API_KEY"] = key


def _clear_ibm_key():
    os.environ.pop("IBM_ADVANTAGE_API_KEY", None)


# ─────────────────────────────────────────────────────────────────────────────
# _fetch_ibm_chat_models
# ─────────────────────────────────────────────────────────────────────────────

class TestFetchIbmChatModels:
    def test_returns_empty_when_no_api_key(self):
        _clear_ibm_cache()
        _clear_ibm_key()
        assert _fetch_ibm_chat_models() == []

    def test_returns_cached_models_within_ttl(self):
        _clear_ibm_cache()
        _set_ibm_key("sk-test")
        with patch("litellm_providers.provider_router.requests.get") as mock_get:
            mock_get.return_value = MagicMock(status_code=200, json=lambda: ["m1", "m2"])
            first = _fetch_ibm_chat_models()
            assert first == ["m1", "m2"]
            mock_get.reset_mock()
            second = _fetch_ibm_chat_models()
            assert second == ["m1", "m2"]
            mock_get.assert_not_called()

    def test_parses_list_response(self):
        _clear_ibm_cache()
        _set_ibm_key("sk-test")
        with patch("litellm_providers.provider_router.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200,
                json=lambda: [
                    {"id": "granite-4-h-small"},
                    {"id": "llama-4-maverick-17b-instruct-fp8"},
                    "legacy-model-name",
                ]
            )
            result = _fetch_ibm_chat_models()
            assert "granite-4-h-small" in result
            assert "llama-4-maverick-17b-instruct-fp8" in result
            assert "legacy-model-name" in result

    def test_parses_dict_response_with_data_key(self):
        _clear_ibm_cache()
        _set_ibm_key("sk-test")
        with patch("litellm_providers.provider_router.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200,
                json=lambda: {
                    "data": [
                        {"model_id": "model-a"},
                        {"name": "model-b"},
                    ]
                }
            )
            result = _fetch_ibm_chat_models()
            assert "model-a" in result
            assert "model-b" in result

    def test_returns_empty_on_401(self):
        _clear_ibm_cache()
        _set_ibm_key("sk-bad")
        with patch("litellm_providers.provider_router.requests.get") as mock_get:
            mock_get.return_value = MagicMock(status_code=401)
            assert _fetch_ibm_chat_models() == []

    def test_returns_empty_on_timeout(self):
        _clear_ibm_cache()
        _set_ibm_key("sk-test")
        import requests as req
        with patch("litellm_providers.provider_router.requests.get", side_effect=req.exceptions.Timeout()):
            assert _fetch_ibm_chat_models() == []

    def test_cache_expires(self):
        _clear_ibm_cache()
        _set_ibm_key("sk-test")
        with patch("litellm_providers.provider_router.requests.get") as mock_get:
            mock_get.return_value = MagicMock(status_code=200, json=lambda: ["fresh"])
            _fetch_ibm_chat_models()
            # Fast-forward past TTL
            import litellm_providers.provider_router as pr
            pr._ibm_chat_models_cache_ts -= 400
            _fetch_ibm_chat_models()
            assert mock_get.call_count == 2


# ─────────────────────────────────────────────────────────────────────────────
# _get_available_providers
# ─────────────────────────────────────────────────────────────────────────────

class TestGetAvailableProviders:
    def test_ibm_excluded_without_key(self):
        _clear_ibm_cache()
        _clear_ibm_key()
        available = _get_available_providers()
        ibm_models = [p[0] for p in available if p[1] == "IBM_ADVANTAGE_API_KEY"]
        assert len(ibm_models) == 0

    def test_ibm_included_with_key_and_discovered_models(self):
        _clear_ibm_cache()
        _set_ibm_key("sk-test")
        with patch("litellm_providers.provider_router._fetch_ibm_chat_models", return_value=["ibm/test-model"]):
            available = _get_available_providers()
            ibm_models = [p[0] for p in available if p[1] == "IBM_ADVANTAGE_API_KEY"]
            assert "ibm/test-model" in ibm_models

    def test_ibm_fallback_used_when_key_set_but_discovery_fails(self):
        _clear_ibm_cache()
        _set_ibm_key("sk-test")
        with patch("litellm_providers.provider_router._fetch_ibm_chat_models", return_value=[]):
            available = _get_available_providers()
            ibm_models = [p[0] for p in available if p[1] == "IBM_ADVANTAGE_API_KEY"]
            assert "ibm/granite-4-h-small" in ibm_models

    def test_ibm_entries_have_correct_structure(self):
        _clear_ibm_cache()
        _clear_ibm_key()
        available = _get_available_providers()
        for entry in available:
            if entry[1] == "IBM_ADVANTAGE_API_KEY":
                model, env_var, weight, api_key, api_base = entry
                assert model.startswith("ibm/") or "/" in model
                assert env_var == "IBM_ADVANTAGE_API_KEY"
                assert weight == 3
                assert api_key == os.getenv("IBM_ADVANTAGE_API_KEY", "")
                assert api_base == IBM_ADVANTAGE_BASE_URL


# ─────────────────────────────────────────────────────────────────────────────
# PROVIDERS list integration
# ─────────────────────────────────────────────────────────────────────────────

class TestProvidersList:
    def test_ibm_entries_are_present(self):
        _clear_ibm_cache()
        _clear_ibm_key()
        ibm_entries = [p for p in PROVIDERS if p[1] == "IBM_ADVANTAGE_API_KEY"]
        assert len(ibm_entries) >= 1

    def test_ibm_entries_have_correct_structure(self):
        _clear_ibm_cache()
        _clear_ibm_key()
        for entry in PROVIDERS:
            if entry[1] == "IBM_ADVANTAGE_API_KEY":
                model, env_var, weight, requires_key, api_base = entry
                assert model.startswith("ibm/") or "/" in model
                assert env_var == "IBM_ADVANTAGE_API_KEY"
                assert weight == 3
                assert requires_key is True
                assert api_base == IBM_ADVANTAGE_BASE_URL

    def test_fallback_does_not_include_wrong_models(self):
        _clear_ibm_cache()
        _clear_ibm_key()
        ibm_entries = [p for p in PROVIDERS if p[1] == "IBM_ADVANTAGE_API_KEY"]
        model_names = [e[0] for e in ibm_entries]
        assert "ibm/claude-haiku-4-5" not in model_names
        assert "ibm/gemma-4-26b-a4b-it" not in model_names


# ─────────────────────────────────────────────────────────────────────────────
# get_configured_providers
# ─────────────────────────────────────────────────────────────────────────────

class TestGetConfiguredProviders:
    def test_returns_list_of_strings(self):
        _clear_ibm_cache()
        _clear_ibm_key()
        providers = get_configured_providers()
        assert isinstance(providers, list)
        assert all(isinstance(p, str) for p in providers)

    def test_returns_kilo_gateway_by_default(self):
        _clear_ibm_cache()
        _clear_ibm_key()
        providers = get_configured_providers()
        assert any("kilo" in p for p in providers)

    def test_returns_ibm_models_when_key_set(self):
        _clear_ibm_cache()
        _set_ibm_key("sk-test")
        with patch("litellm_providers.provider_router._fetch_ibm_chat_models", return_value=["ibm/discovered-model"]):
            providers = get_configured_providers()
            assert "ibm/discovered-model" in providers


# ─────────────────────────────────────────────────────────────────────────────
# get_llm integration
# ─────────────────────────────────────────────────────────────────────────────

class TestGetLlm:
    def test_creates_llm_without_key(self):
        _clear_ibm_cache()
        _clear_ibm_key()
        llm = get_llm()
        assert llm is not None
        assert hasattr(llm, "invoke")

    def test_creates_llm_with_ibm_key_and_discovered_model(self):
        _clear_ibm_cache()
        _set_ibm_key("sk-test")
        with patch("litellm_providers.provider_router._fetch_ibm_chat_models", return_value=["ibm/granite-4-h-small"]):
            llm = get_llm(provider_override="ibm")
            assert llm is not None
            assert llm.model.startswith("ibm/")
