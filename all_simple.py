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
from typing import Dict, Any, Optional, List

# Set up basic logging
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

    semaphore = asyncio.Semaphore(10)  # Up to 10 concurrent requests.

    def __init__(
        self,
        server_url: str = "http://localhost",
        server_port: int = 5005,
        sleep_delay: float = 0.0
    ) -> None:
        """
        Initialize the Rasa client.
        """
        self.server_url = f"{server_url}:{server_port}"
        self.sleep_delay = sleep_delay
        self.sender_id = "user"  # Fixed sender ID
        self.active_form = None
        self.slots = {}
        self.session = None

    @classmethod
    async def create(
        cls,
        server_url: str = "http://localhost",
        server_port: int = 5005,
        sleep_delay: float = 0.0
    ) -> "RasaClient":
        """
        Async factory method that creates a RasaClient instance 
        and initializes its aiohttp.ClientSession.
        """
        instance = cls(server_url, server_port, sleep_delay)
        timeout = aiohttp.ClientTimeout(total=30)
        instance.session = aiohttp.ClientSession(timeout=timeout)
        return instance

    async def close(self) -> None:
        """Close the aiohttp session."""
        if self.session:
            await self.session.close()
            self.session = None

    async def get_server_status(self) -> Dict[str, Any]:
        """GET /status"""
        if not self.session:
            raise RasaClientError("Client session is not initialized.")
        url = f"{self.server_url}/status"
        async with self.semaphore:
            async with self.session.get(url) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def get_tracker(self) -> Dict[str, Any]:
        """GET /conversations/{sender_id}/tracker"""
        if not self.session:
            raise RasaClientError("Client session is not initialized.")
        url = f"{self.server_url}/conversations/{self.sender_id}/tracker"
        async with self.semaphore:
            async with self.session.get(url) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def send_message(self, message_text: str) -> List[Dict[str, Any]]:
        """
        Send a message to Rasa using the webhook endpoint.
        Returns the bot's response messages.
        """
        if not self.session:
            raise RasaClientError("Client session is not initialized.")

        url = f"{self.server_url}/webhooks/rest/webhook"
        payload = {
            "sender": "user",
            "message": message_text
        }

        async with self.semaphore:
            try:
                async with self.session.post(url, json=payload) as resp:
                    resp.raise_for_status()
                    response = await resp.json()
                    
                    # Update tracker after message
                    tracker_data = await self.get_tracker()
                    self.active_form = tracker_data.get("active_loop", {}).get("name")
                    self.slots = tracker_data.get("slots", {})

                    # Add optional delay if a form is active
                    if self.active_form and self.sleep_delay > 0:
                        await asyncio.sleep(self.sleep_delay)

                    return response if response else [{"text": "No response from bot"}]

            except aiohttp.ClientError as e:
                logger.error(f"Error sending message: {e}")
                return [{"text": "Error communicating with the bot"}]

    @staticmethod
    def get_bot_response_text(messages: List[Dict[str, Any]]) -> List[str]:
        """
        Extract textual responses from the bot's reply.
        Returns a list of strings for each bot message.
        """
        if not messages:
            return ["[No response from bot]"]
        
        texts = []
        for msg in messages:
            if "text" in msg:
                texts.append(msg["text"])
                
        return texts or ["[No text response from bot]"]


async def interactive_chat(client: RasaClient) -> None:
    """
    Simple command-line loop to interact with the Rasa bot.
    Type 'quit' or 'exit' to end the session.
    """
    print("Bot: Hello! I'm your Rasa chatbot. Type 'quit' or 'exit' to leave.")
    
    while True:
        try:
            user_message = input("You: ").strip()
            if user_message.lower() in ("quit", "exit"):
                print("Bot: Goodbye!")
                break

            bot_messages = await client.send_message(user_message)
            bot_responses = client.get_bot_response_text(bot_messages)
            
            for text in bot_responses:
                print(f"Bot: {text}")

        except Exception as e:
            logger.error(f"Error in conversation: {e}")
            print("Bot: Sorry, an error occurred. Please try again.")


async def main() -> None:
    """
    Main entry point (single server, no authentication).
    Adjust server_url and server_port as needed.
    """
    server_url = "http://localhost"
    server_port = 5005
    sleep_delay = 0.0

    try:
        # Check if Rasa server is running
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{server_url}:{server_port}/status") as resp:
                    await resp.json()
            except Exception as e:
                print("Error: Could not connect to Rasa server. Is it running?")
                return

        # Create and run client
        client = await RasaClient.create(
            server_url=server_url,
            server_port=server_port,
            sleep_delay=sleep_delay
        )
        
        try:
            await interactive_chat(client)
        finally:
            await client.close()

    except Exception as e:
        logger.error(f"Error in main: {e}")
        print("Error: Something went wrong. Please check the logs.")


if __name__ == "__main__":
    if sys.version_info < (3, 7):
        print("Please run this script with Python 3.7 or higher.")
        sys.exit(1)

    asyncio.run(main())
