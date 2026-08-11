"""
NotebookLM (Gemini Notebook) provider — grounded research over YOUR notebooks.

This is a first-class knowledge provider, wired the same way the LLM providers in
`litellm_providers` are: all config comes from environment variables, it is
non-fatal when unconfigured, and it self-heals its session from a durable master
token so it runs headless on a server with no browser popups.

Auth model (server-friendly, documented by teng-lin/notebooklm-py):
    Generate ONCE on any machine with a browser:
        notebooklm login --master-token --account you@example.com
    Then set in .env:
        NOTEBOOKLM_MASTER_TOKEN=aas_et/...
        NOTEBOOKLM_ACCOUNT=you@example.com
        NOTEBOOKLM_ANDROID_ID=<printed by the login command>   # optional but recommended
        NOTEBOOKLM_ID=<notebook id>                            # optional; auto-detected otherwise

The bot mints fresh web cookies on demand from the master token — no interactive
login, no cookie file to babysit. If no token is configured, `is_configured()`
returns False and the researcher silently falls back to its local RAG.
"""

import os
import asyncio
import logging
from typing import Optional

logger = logging.getLogger("notebooklm_provider")

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


class NotebookLMProvider:
    """Live connection to your NotebookLM/Gemini Notebook workspace."""

    def __init__(self):
        self.master_token = os.getenv("NOTEBOOKLM_MASTER_TOKEN", "").strip()
        self.account = os.getenv("NOTEBOOKLM_ACCOUNT", "").strip()
        self.android_id = os.getenv("NOTEBOOKLM_ANDROID_ID", "").strip()
        self.notebook_id = os.getenv("NOTEBOOKLM_ID", "").strip() or None
        # match a notebook by title when no explicit id is given
        self.notebook_match = os.getenv("NOTEBOOKLM_MATCH", "goldshark,trading").lower()
        self._auth = None

    # ── configuration gate (mirrors get_configured_providers style) ──
    def is_configured(self) -> bool:
        return bool(self.master_token and self.account)

    # ── auth: mint fresh cookies from the durable master token ──
    async def _ensure_auth(self) -> bool:
        if self._auth is not None:
            return True
        if not self.is_configured():
            return False
        try:
            from notebooklm.auth import mint_cookies, AuthTokens, generate_android_id
            from notebooklm._auth.tokens import fetch_tokens_with_domains  # type: ignore
        except Exception:
            # fall back to the public surface only
            from notebooklm.auth import mint_cookies, AuthTokens, generate_android_id  # type: ignore

        try:
            android_id = self.android_id or generate_android_id()
            jar = await mint_cookies(self.account, self.master_token, android_id)
            # Build AuthTokens from the freshly minted jar (fetches CSRF/session).
            from notebooklm.auth import build_cookie_jar  # noqa: F401
            # AuthTokens needs csrf + session; the client refresh will populate them
            # from the homepage using these cookies.
            self._auth = AuthTokens(
                cookies={},
                csrf_token="",
                session_id="",
                cookie_jar=jar,
                account_email=self.account,
            )
            # Prime CSRF/session tokens via a homepage refresh.
            from notebooklm.client import NotebookLMClient
            async with NotebookLMClient(self._auth) as client:
                await client.refresh_auth()
            return True
        except Exception as e:
            logger.warning(f"NotebookLM auth (master-token mint) failed: {e}")
            self._auth = None
            return False

    async def _resolve_notebook_id(self, client) -> Optional[str]:
        if self.notebook_id:
            return self.notebook_id
        try:
            notebooks = await client.notebooks.list()
        except Exception as e:
            logger.warning(f"NotebookLM list notebooks failed: {e}")
            return None
        wanted = [w.strip() for w in self.notebook_match.split(",") if w.strip()]
        for nb in notebooks:
            title = (getattr(nb, "title", "") or "").lower()
            if any(w in title for w in wanted):
                self.notebook_id = nb.id
                logger.info(f"NotebookLM auto-selected notebook '{nb.title}' ({nb.id})")
                return nb.id
        if notebooks:
            self.notebook_id = notebooks[0].id
            logger.info(f"NotebookLM using first notebook ({self.notebook_id})")
            return self.notebook_id
        return None

    async def ask_async(self, question: str) -> Optional[str]:
        if not await self._ensure_auth():
            return None
        try:
            from notebooklm.client import NotebookLMClient
            async with NotebookLMClient(self._auth) as client:
                nb_id = await self._resolve_notebook_id(client)
                if not nb_id:
                    return None
                result = await client.chat.ask(nb_id, question)
                return getattr(result, "answer", None)
        except Exception as e:
            logger.warning(f"NotebookLM ask failed: {e}")
            return None

    # ── sync bridge used by the (sync) ContinualResearcher ──
    def _run(self, coro):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        # already inside a loop (rare here) — run in a fresh loop on a thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(lambda: asyncio.run(coro)).result()

    def ask(self, question: str) -> Optional[str]:
        return self._run(self.ask_async(question))

    def research(self, query: str, n_results: int = 3) -> list[dict]:
        """RAG-compatible shape so it drops into the researcher's knowledge list."""
        if not self.is_configured():
            return []
        answer = self.ask(query)
        if not answer:
            return []
        return [{
            "text": answer,
            "similarity": 0.99,
            "metadata": {"title": "NotebookLM (Gemini Notebook)", "source": "notebooklm"},
        }]


_PROVIDER: Optional[NotebookLMProvider] = None


def get_notebooklm() -> NotebookLMProvider:
    """Singleton accessor, mirroring get_llm()'s lazy pattern."""
    global _PROVIDER
    if _PROVIDER is None:
        _PROVIDER = NotebookLMProvider()
    return _PROVIDER
