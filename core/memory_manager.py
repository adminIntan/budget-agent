import os
import time
import logging
from collections import defaultdict
from google.cloud import firestore
from google.api_core.exceptions import GoogleAPIError

logger = logging.getLogger(__name__)

class FirestoreMemoryManager:
    """
    Manages multi-turn conversation memory for Discord channels using Google Cloud Firestore.
    Maintains history of up to N recent interactions per channel.
    Includes in-memory fallback if Firestore is not accessible.
    """

    def __init__(self, project_id: str = None, collection_name: str = "discord_budget_memory"):
        self.project_id = project_id or os.getenv("GCP_PROJECT_ID")
        self.collection_name = collection_name
        self.db = None

        # Fallback local in-memory store if Firestore connection fails
        self._memory_cache = defaultdict(list)

        try:
            self.db = firestore.Client(project=self.project_id)
            logger.info(f"Firestore Client initialized for collection: {self.collection_name}")
        except Exception as e:
            logger.warning(f"Could not initialize Firestore client: {e}. Using local in-memory history fallback.")

    def get_recent_history(self, session_id: str, limit: int = 10) -> list[dict]:
        """
        Retrieves the last `limit` (default 10) conversation turns for a given session/channel ID.
        Returns a list of dicts: [{'user': '...', 'assistant': '...', 'sql': '...'}, ...]
        """
        if not session_id:
            return []

        if self.db:
            try:
                doc_ref = self.db.collection(self.collection_name).document(str(session_id))
                messages_ref = doc_ref.collection("messages").order_by(
                    "timestamp", direction=firestore.Query.DESCENDING
                ).limit(limit)

                docs = list(messages_ref.stream())
                history = []
                for doc in reversed(docs):
                    data = doc.to_dict()
                    history.append({
                        "user": data.get("user", ""),
                        "assistant": data.get("assistant", ""),
                        "sql": data.get("sql", "")
                    })
                return history
            except Exception as e:
                logger.warning(f"Firestore access unavailable ({e}). Falling back to local in-memory conversation memory.")
                self.db = None  # Disable Firestore so subsequent calls cleanly use in-memory cache

        # Fallback to local in-memory cache
        return self._memory_cache[str(session_id)][-limit:]

    def add_interaction(self, session_id: str, user_query: str, bot_response: str, sql_query: str = "", limit: int = 10):
        """
        Saves a user query and bot response turn into Firestore (and local cache).
        """
        if not session_id:
            return

        interaction = {
            "user": user_query,
            "assistant": bot_response,
            "sql": sql_query,
            "timestamp": time.time()
        }

        # Save to local cache first
        cache_list = self._memory_cache[str(session_id)]
        cache_list.append(interaction)
        if len(cache_list) > limit * 2:
            self._memory_cache[str(session_id)] = cache_list[-limit:]

        # Save to Firestore if available
        if self.db:
            try:
                doc_ref = self.db.collection(self.collection_name).document(str(session_id))
                doc_ref.collection("messages").add(interaction)
                doc_ref.set({"last_updated": time.time()}, merge=True)
                logger.info(f"Saved conversation turn to Firestore for session: {session_id}")
            except Exception as e:
                logger.warning(f"Failed to save interaction to Firestore ({e}). Continuing with in-memory cache.")
                self.db = None
