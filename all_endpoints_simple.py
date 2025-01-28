#!/usr/bin/env python3
"""
A single Rasa client (no authentication) that demonstrates 
various endpoints (tracker retrieval, model operations) 
plus an interactive chat loop.
Simply configure `server_url`, `server_port` if needed, 
then run:

    python3 scriptname.py

When launched, it starts an interactive CLI session. 
Type 'quit' or 'exit' to end the session.
"""

import asyncio
import aiohttp
import json
import time
import sys
import logging
from typing import (
    Dict,
    Any,
    Optional,
    List
)

# Set up basic logging (you can customize formatting and levels as needed).
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s"))
logger.addHandler(console_handler)


class RasaClientError(Exception):
    """Custom exception for Rasa client errors."""
    pass


class RasaClient:
    """
    A client for interacting with a Rasa server via HTTP API endpoints.
    Includes conversation endpoints, model management, domain info, etc.
    No authentication logic; purely open endpoints.
    """

    # Global semaphore to limit concurrency (optional).
    semaphore = asyncio.Semaphore(10)  # Up to 10 concurrent requests.

    def __init__(
        self,
        server_url: str = "http://localhost",
        server_port: int = 5005,
        original_number: str = "00000000000",
        sleep_delay: float = 0.0
    ) -> None:
        """
        :param server_url: Base URL of the Rasa server (e.g., http://localhost).
        :param server_port: Port where Rasa server is running (default 5005).
        :param original_number: Arbitrary string for generating a unique sender/conversation ID.
        :param sleep_delay: Delay in seconds after each user message (useful if forms need time).
        """
        self.server_url = f"{server_url}:{server_port}"
        self.original_number = original_number
        self.sleep_delay = sleep_delay

        # Generate a unique conversation ID incorporating the original_number.
        current_time = int(time.time() * 1000)
        self.sender_id = f"{current_time}_{self.original_number}"

        # Conversation state
        self.active_form: Optional[str] = None
        self.slots: Dict[str, Any] = {}

        # We'll initialize the aiohttp session in the async factory method.
        self.session: Optional[aiohttp.ClientSession] = None

    @classmethod
    async def create(
        cls,
        server_url: str = "http://localhost",
        server_port: int = 5005,
        original_number: str = "00000000000",
        sleep_delay: float = 0.0
    ) -> "RasaClient":
        """
        Async factory method that creates a RasaClient instance 
        and initializes its aiohttp.ClientSession.
        """
        instance = cls(server_url, server_port, original_number, sleep_delay)
        timeout = aiohttp.ClientTimeout(total=30)  # Adjust if needed
        instance.session = aiohttp.ClientSession(timeout=timeout)
        return instance

    async def close(self) -> None:
        """Close the aiohttp session."""
        if self.session is not None:
            await self.session.close()
            self.session = None

    # ------------------------------------------------------------------
    #                      Server Info
    # ------------------------------------------------------------------
    async def get_server_root(self) -> str:
        """GET / -- Some servers may not implement this route; returns raw text or empty string."""
        if not self.session:
            raise RasaClientError("Client session is not initialized.")
        url = f"{self.server_url}/"
        async with self.semaphore:
            try:
                async with self.session.get(url) as resp:
                    return await resp.text()
            except Exception as e:
                logger.error(f"Error calling GET /: {e}")
                return ""

    async def get_server_version(self) -> Dict[str, Any]:
        """GET /version"""
        if not self.session:
            raise RasaClientError("Client session is not initialized.")
        url = f"{self.server_url}/version"
        async with self.semaphore:
            async with self.session.get(url) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def get_server_status(self) -> Dict[str, Any]:
        """GET /status"""
        if not self.session:
            raise RasaClientError("Client session is not initialized.")
        url = f"{self.server_url}/status"
        async with self.semaphore:
            async with self.session.get(url) as resp:
                resp.raise_for_status()
                return await resp.json()

    # ------------------------------------------------------------------
    #               Conversation / Tracker Endpoints
    # ------------------------------------------------------------------
    async def get_tracker(self, conversation_id: str) -> Dict[str, Any]:
        """GET /conversations/{conversation_id}/tracker"""
        if not self.session:
            raise RasaClientError("Client session is not initialized.")
        url = f"{self.server_url}/conversations/{conversation_id}/tracker"
        async with self.semaphore:
            async with self.session.get(url) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def post_message_to_conversation(
        self, conversation_id: str, message_text: str
    ) -> List[Dict[str, Any]]:
        """POST /conversations/{conversation_id}/messages"""
        if not self.session:
            raise RasaClientError("Client session is not initialized.")
        url = f"{self.server_url}/conversations/{conversation_id}/messages"
        payload = {"sender": conversation_id, "text": message_text}

        async with self.semaphore:
            async with self.session.post(url, json=payload) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def predict_next_action(self, conversation_id: str) -> Dict[str, Any]:
        """POST /conversations/{conversation_id}/predict"""
        if not self.session:
            raise RasaClientError("Client session is not initialized.")
        url = f"{self.server_url}/conversations/{conversation_id}/predict"
        async with self.semaphore:
            async with self.session.post(url) as resp:
                resp.raise_for_status()
                return await resp.json()

    # ------------------------------------------------------------------
    #                Model Endpoints
    # ------------------------------------------------------------------
    async def parse_model(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """POST /model/parse"""
        if not self.session:
            raise RasaClientError("Client session is not initialized.")
        url = f"{self.server_url}/model/parse"
        async with self.semaphore:
            async with self.session.post(url, json=payload) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def train_model(self, training_data: Dict[str, Any]) -> Dict[str, Any]:
        """POST /model/train"""
        if not self.session:
            raise RasaClientError("Client session is not initialized.")
        url = f"{self.server_url}/model/train"
        async with self.semaphore:
            async with self.session.post(url, json=training_data) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def delete_model(self) -> Dict[str, Any]:
        """DELETE /model"""
        if not self.session:
            raise RasaClientError("Client session is not initialized.")
        url = f"{self.server_url}/model"
        async with self.semaphore:
            async with self.session.delete(url) as resp:
                resp.raise_for_status()
                return await resp.json()

    # ------------------------------------------------------------------
    #             High-Level Send-Message Flow
    # ------------------------------------------------------------------
    async def send_message(self, message_text: str) -> Dict[str, Any]:
        """
        Sends a user message to Rasa and retrieves the bot's response + updated tracker.
        Flow:
          1) NLU parse
          2) Post message to conversation
          3) Retrieve tracker
          4) Predict next action
        Returns a dict with:
          {
            "response": [...],
            "intent": ...,
            "entities": ...,
            "active_form": ...,
            "slots": ...,
            "tracker_data": ...,
            "next_action": ...
          }
        """
        if not self.session:
            raise RasaClientError("Client session is not initialized.")

        # 1) Parse with NLU
        parse_payload = {"sender": self.sender_id, "text": message_text}
        parse_result = await self.parse_model(parse_payload)
        intent_info = parse_result.get("intent", {})
        intent_name = intent_info.get("name", "unknown")
        intent_confidence = intent_info.get("confidence", 0.0)
        entities = parse_result.get("entities", [])

        # 2) Send message to conversation
        bot_messages = await self.post_message_to_conversation(self.sender_id, message_text)

        # 3) Retrieve tracker
        tracker_data = await self.get_tracker(self.sender_id)

        # 4) Predict next action
        prediction_data = await self.predict_next_action(self.sender_id)
        next_action = None
        action_confidence = 0.0
        if prediction_data and "scores" in prediction_data:
            scores = prediction_data["scores"]
            if scores:
                next_action = scores[0].get("action", None)
                action_confidence = scores[0].get("score", 0.0)

        # Update local references
        self.active_form = tracker_data.get("active_loop", {}).get("name")
        self.slots = tracker_data.get("slots", {})

        # Optional sleep (useful if forms need a small delay).
        if self.active_form and self.sleep_delay > 0:
            await asyncio.sleep(self.sleep_delay)

        return {
            "response": bot_messages,
            "intent": {"name": intent_name, "confidence": intent_confidence},
            "entities": entities,
            "active_form": self.active_form,
            "slots": self.slots,
            "tracker_data": tracker_data,
            "next_action": {"name": next_action, "confidence": action_confidence}
        }

    @staticmethod
    def get_bot_response_text(response_data: Dict[str, Any]) -> List[str]:
        """
        Extract textual responses from the "response" field (the Rasa server's reply).
        Returns a list of strings for each bot message.
        """
        messages = response_data.get("response", [])
        if not messages:
            return ["[No response from bot]"]
        texts = []
        for msg in messages:
            if "text" in msg:
                texts.append(msg["text"])
        return texts


async def interactive_chat(client: RasaClient) -> None:
    """
    Simple command-line loop to interact with the Rasa bot.
    Type 'quit' or 'exit' to end the session.
    """
    print("Bot: Hello! I'm your Rasa chatbot. Type 'quit' or 'exit' to leave.")
    while True:
        user_message = input("You: ").strip()
        if user_message.lower() in ("quit", "exit"):
            print("Bot: Goodbye!")
            break

        try:
            response_data = await client.send_message(user_message)
            # Extract the text from the bot's responses
            bot_responses = RasaClient.get_bot_response_text(response_data)
            for text_msg in bot_responses:
                print(f"Bot: {text_msg}")
        except Exception as exc:
            logger.error(f"Error in send_message: {exc}")
            print("Bot: Sorry, an error occurred. Please try again.")


async def main() -> None:
    """
    Main entry point (single server, no authentication).
    Adjust server_url, server_port, etc. as needed.
    """
    server_url = "http://localhost"   # or your server IP/domain
    server_port = 5005               # default Rasa port
    original_number = "user12345"     # can be any unique ID part
    sleep_delay = 0.0                # delay after each user message if needed

    # Create one RasaClient instance
    client = await RasaClient.create(
        server_url=server_url,
        server_port=server_port,
        original_number=original_number,
        sleep_delay=sleep_delay
    )

    try:
        await interactive_chat(client)
    finally:
        await client.close()


if __name__ == "__main__":
    if sys.version_info < (3, 7):
        print("Please run this script with Python 3.7 or higher.")
        sys.exit(1)

    asyncio.run(main())
