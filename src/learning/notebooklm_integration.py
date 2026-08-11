import os
import json
import logging
import asyncio
from pathlib import Path
from typing import Optional

from src import config

logger = logging.getLogger("learning.notebooklm_integration")

class RemoteNotebookLM:
    """
    Real connection to Google's NotebookLM via the unofficial python client.
    Requires a valid 'data/storage_state.json' generated via 'notebooklm login'.
    """
    
    def __init__(self, notebook_id: Optional[str] = None):
        self.storage_path = Path(os.path.join(config.DATA_DIR, "storage_state.json"))
        self.notebook_id = notebook_id or os.getenv("NOTEBOOKLM_ID")
        self._auth = None
        
    async def _init_auth(self):
        if self._auth is not None:
            return True
        if not self.storage_path.exists():
            logger.warning(f"NotebookLM storage_state.json not found at {self.storage_path}. Run 'notebooklm login' locally and copy it here.")
            return False
            
        try:
            from notebooklm.auth import AuthTokens
            self._auth = await AuthTokens.from_storage(path=self.storage_path)
            return True
        except Exception as e:
            logger.error(f"Failed to authenticate with NotebookLM: {e}")
            return False

    async def get_or_find_notebook_id(self) -> Optional[str]:
        if self.notebook_id:
            return self.notebook_id
            
        if not await self._init_auth():
            return None
            
        try:
            from notebooklm.client import NotebookLMClient
            async with NotebookLMClient(self._auth) as client:
                notebooks = await client.notebooks.list()
                for nb in notebooks:
                    if "goldshark" in nb.title.lower() or "trading" in nb.title.lower():
                        logger.info(f"Auto-selected NotebookLM notebook: {nb.title} ({nb.id})")
                        self.notebook_id = nb.id
                        return nb.id
                
                if notebooks:
                    self.notebook_id = notebooks[0].id
                    logger.info(f"Using default NotebookLM notebook: {notebooks[0].title} ({self.notebook_id})")
                    return self.notebook_id
                    
        except Exception as e:
            logger.error(f"Failed to list notebooks from NotebookLM: {e}")
            
        return None

    async def ask_async(self, query: str) -> Optional[str]:
        nb_id = await self.get_or_find_notebook_id()
        if not nb_id:
            return None
            
        try:
            from notebooklm.client import NotebookLMClient
            async with NotebookLMClient(self._auth) as client:
                result = await client.chat.ask(nb_id, query)
                return result.answer
        except Exception as e:
            logger.error(f"NotebookLM chat failed: {e}")
            return None

    def research(self, query: str, n_results: int = 3) -> list[dict]:
        """
        Synchronous wrapper for the ContinualResearcher to query the remote NotebookLM.
        Returns a mock 'hits' list compatible with the RAG format.
        """
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        answer = loop.run_until_complete(self.ask_async(query))
        
        if not answer:
            return []
            
        # Wrap the response in the expected RAG dict shape
        return [{
            "text": answer,
            "similarity": 0.99,
            "metadata": {"title": "Google NotebookLM (Live)"}
        }]
