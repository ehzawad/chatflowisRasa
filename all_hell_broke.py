#!/usr/bin/env python3
import asyncio
import aiohttp
import json
import time
import argparse
import os
import pwd
from typing import (
    Dict,
    Any,
    Optional,
    List,
    Tuple,
    Generator
)
from datetime import datetime

class RasaClientError(Exception):
    """Custom exception for Rasa client errors."""
    pass


def get_appadm_ids() -> Tuple[Optional[int], Optional[int]]:
    """
    Safely retrieve the user/group IDs for 'appadm'.
    If 'appadm' doesn't exist, return (None, None).
    """
    try:
        uid = pwd.getpwnam('appadm').pw_uid
        gid = pwd.getpwnam('appadm').pw_gid
        return uid, gid
    except KeyError:
        return None, None


def set_file_permissions(filepath: str) -> None:
    """
    Set file permissions and ownership to appadm:appadm with 664 permissions.
    If the 'appadm' user does not exist, skip ownership and log a warning.
    """
    uid, gid = get_appadm_ids()
    if uid is not None and gid is not None:
        try:
            os.chown(filepath, uid, gid)
            os.chmod(filepath, 0o664)
        except Exception as e:
            print(f"Warning: Could not set file ownership/permissions: {e}")
    else:
        print("Warning: 'appadm' user/group not found. Skipping chown.")
        try:
            os.chmod(filepath, 0o664)
        except Exception as e:
            print(f"Warning: Could not set file permissions to 664: {e}")


class RasaClient:
    """
    A client for interacting with a Rasa server via HTTP API endpoints.
    Includes conversation endpoints, model management, domain info, etc.
    """

    # Optional concurrency limit across all RasaClient instances
    semaphore = asyncio.Semaphore(10)  # Limit concurrency to 10

    def __init__(
        self,
        rasa_url: str = "http://localhost",
        original_number: str = "01568725958",
        rasa_port: Optional[int] = None,
        action_port: Optional[int] = None,
        sleep_delay: float = 1.0
    ):
        """
        Construct a RasaClient. Use the async classmethod 'create()' to get
        an initialized instance with an active aiohttp.ClientSession.
        """
        self.rasa_url = rasa_url
        self.rasa_port = rasa_port or 5009
        self.action_port = action_port or 5059

        # Build final endpoints
        self.rasa_url = f"{self.rasa_url}:{self.rasa_port}"
        self.action_url = f"http://0.0.0.0:{self.action_port}"

        # For generating unique conversation IDs
        current_time = int(time.time() * 1000)
        self.via_number = "8809611888444"  # Always fixed
        self.original_number = original_number

        # For demonstration: mask certain test numbers if their last 11 digits match
        self.test_numbers = [
            '09696387582', '09638372914', '01924560627', '01518472623',
            '01580582654', '01833626976', '01571321136', '01764655648',
            '09638317055', '09638080760', '09696173224', '09611888444',
            '01911310316', '19723182900', '01558666739', '01714007806',
            '01714020387'
        ]
        if len(self.original_number) >= 11 and self.original_number[-11:] in self.test_numbers:
            self.masked_number = '01568725958'
        else:
            self.masked_number = self.original_number

        self.sender_id = f"{current_time}_{self.via_number}_{self.masked_number}"

        self.active_form: Optional[str] = None
        self.slots: Dict[str, Any] = {}

        # We'll open the session in the async factory method
        self.session: Optional[aiohttp.ClientSession] = None

        # Configurable delay for each message send
        self.sleep_delay = sleep_delay

    @classmethod
    async def create(
        cls,
        rasa_url: str = "http://localhost",
        original_number: str = "01568725958",
        rasa_port: Optional[int] = None,
        action_port: Optional[int] = None,
        sleep_delay: float = 1.0
    ) -> "RasaClient":
        """
        Async factory method that initializes the aiohttp session.
        Usage:
            client = await RasaClient.create(...)
        """
        instance = cls(
            rasa_url=rasa_url,
            original_number=original_number,
            rasa_port=rasa_port,
            action_port=action_port,
            sleep_delay=sleep_delay
        )
        instance.session = aiohttp.ClientSession()
        return instance

    async def close(self) -> None:
        """Close the aiohttp session."""
        if self.session is not None:
            await self.session.close()

    # ------------------------------------------------------------------
    #         SERVER INFORMATION ENDPOINTS
    # ------------------------------------------------------------------
    async def get_server_root(self) -> str:
        """GET / -- Some servers may not implement this route; returns raw text or empty string."""
        if not self.session:
            raise RasaClientError("Client session is not initialized.")
        url = f"{self.rasa_url}/"
        async with self.semaphore:
            try:
                async with self.session.get(url) as resp:
                    # Not all servers implement '/', so no raise_for_status() here
                    return await resp.text()
            except Exception as e:
                print(f"Error calling GET / : {e}")
                return ""

    async def get_server_version(self) -> Dict[str, Any]:
        """GET /version"""
        if not self.session:
            raise RasaClientError("Client session is not initialized.")
        url = f"{self.rasa_url}/version"
        async with self.semaphore:
            async with self.session.get(url) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def get_server_status(self) -> Dict[str, Any]:
        """GET /status"""
        if not self.session:
            raise RasaClientError("Client session is not initialized.")
        url = f"{self.rasa_url}/status"
        async with self.semaphore:
            async with self.session.get(url) as resp:
                resp.raise_for_status()
                return await resp.json()

    # ------------------------------------------------------------------
    #         CONVERSATION TRACKER ENDPOINTS
    # ------------------------------------------------------------------
    async def get_tracker(self, conversation_id: str) -> Dict[str, Any]:
        """GET /conversations/{conversation_id}/tracker"""
        if not self.session:
            raise RasaClientError("Client session is not initialized.")
        url = f"{self.rasa_url}/conversations/{conversation_id}/tracker"
        async with self.semaphore:
            async with self.session.get(url) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def add_event_to_tracker(
        self, conversation_id: str, event_payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        POST /conversations/{conversation_id}/tracker/events
        """
        if not self.session:
            raise RasaClientError("Client session is not initialized.")
        url = f"{self.rasa_url}/conversations/{conversation_id}/tracker/events"
        async with self.semaphore:
            async with self.session.post(url, json=event_payload) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def update_event_in_tracker(
        self, conversation_id: str, event_payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        PUT /conversations/{conversation_id}/tracker/events
        """
        if not self.session:
            raise RasaClientError("Client session is not initialized.")
        url = f"{self.rasa_url}/conversations/{conversation_id}/tracker/events"
        async with self.semaphore:
            async with self.session.put(url, json=event_payload) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def get_story(self, conversation_id: str) -> str:
        """GET /conversations/{conversation_id}/story"""
        if not self.session:
            raise RasaClientError("Client session is not initialized.")
        url = f"{self.rasa_url}/conversations/{conversation_id}/story"
        async with self.semaphore:
            async with self.session.get(url) as resp:
                resp.raise_for_status()
                return await resp.text()

    async def trigger_intent(
        self, conversation_id: str, intent_name: str, entities: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """POST /conversations/{conversation_id}/trigger_intent"""
        if not self.session:
            raise RasaClientError("Client session is not initialized.")
        url = f"{self.rasa_url}/conversations/{conversation_id}/trigger_intent"
        payload = {"name": intent_name, "entities": entities or []}
        async with self.semaphore:
            async with self.session.post(url, json=payload) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def predict_next_action(self, conversation_id: str) -> Dict[str, Any]:
        """POST /conversations/{conversation_id}/predict"""
        if not self.session:
            raise RasaClientError("Client session is not initialized.")
        url = f"{self.rasa_url}/conversations/{conversation_id}/predict"
        async with self.semaphore:
            async with self.session.post(url) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def post_message_to_conversation(
        self, conversation_id: str, message_text: str
    ) -> Dict[str, Any]:
        """POST /conversations/{conversation_id}/messages"""
        if not self.session:
            raise RasaClientError("Client session is not initialized.")
        url = f"{self.rasa_url}/conversations/{conversation_id}/messages"
        payload = {"sender": conversation_id, "text": message_text}
        async with self.semaphore:
            async with self.session.post(url, json=payload) as resp:
                resp.raise_for_status()
                return await resp.json()

    # ------------------------------------------------------------------
    #         MODEL MANAGEMENT ENDPOINTS
    # ------------------------------------------------------------------
    async def train_model(self, training_data: Dict[str, Any]) -> Dict[str, Any]:
        """POST /model/train"""
        if not self.session:
            raise RasaClientError("Client session is not initialized.")
        url = f"{self.rasa_url}/model/train"
        async with self.semaphore:
            async with self.session.post(url, json=training_data) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def predict_model(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """POST /model/predict"""
        if not self.session:
            raise RasaClientError("Client session is not initialized.")
        url = f"{self.rasa_url}/model/predict"
        async with self.semaphore:
            async with self.session.post(url, json=payload) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def parse_model(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """POST /model/parse"""
        if not self.session:
            raise RasaClientError("Client session is not initialized.")
        url = f"{self.rasa_url}/model/parse"
        async with self.semaphore:
            async with self.session.post(url, json=payload) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def update_model(self, model_file_bytes: bytes) -> Dict[str, Any]:
        """PUT /model"""
        if not self.session:
            raise RasaClientError("Client session is not initialized.")
        url = f"{self.rasa_url}/model"
        async with self.semaphore:
            async with self.session.put(url, data=model_file_bytes) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def delete_model(self) -> Dict[str, Any]:
        """DELETE /model"""
        if not self.session:
            raise RasaClientError("Client session is not initialized.")
        url = f"{self.rasa_url}/model"
        async with self.semaphore:
            async with self.session.delete(url) as resp:
                resp.raise_for_status()
                return await resp.json()

    # ------------------------------------------------------------------
    #         DOMAIN ENDPOINT
    # ------------------------------------------------------------------
    async def get_domain(self) -> Dict[str, Any]:
        """GET /domain"""
        if not self.session:
            raise RasaClientError("Client session is not initialized.")
        url = f"{self.rasa_url}/domain"
        async with self.semaphore:
            async with self.session.get(url) as resp:
                resp.raise_for_status()
                return await resp.json()

    # ------------------------------------------------------------------
    #         ORIGINAL METHODS (MAIN USAGE) with REFINEMENTS
    # ------------------------------------------------------------------
    async def get_next_action(self) -> Optional[str]:
        """
        Return the next predicted action for the current sender_id,
        or None on error.
        """
        if not self.session:
            raise RasaClientError("Client session is not initialized.")
        url = f"{self.rasa_url}/conversations/{self.sender_id}/predict"
        async with self.semaphore:
            try:
                async with self.session.post(url) as response:
                    response.raise_for_status()
                    prediction = await response.json()
                    return prediction.get("scores", [{}])[0].get("action", None)
            except Exception as e:
                print(f"Error getting next action prediction: {e}")
                return None

    async def send_message(self, message_text: str) -> Dict[str, Any]:
        """
        Send a message to the Rasa server and retrieve the response.
        This call:
          1) Parses the message (NLU)
          2) Posts the message to /conversations/{conversation_id}/messages
          3) Retrieves the tracker
          4) Predicts the next action
        """
        if not self.session:
            raise RasaClientError("Client session is not initialized.")

        # 1) NLU parse
        parse_url = f"{self.rasa_url}/model/parse"
        parse_payload = {"sender": self.sender_id, "text": message_text}
        async with self.semaphore:
            async with self.session.post(parse_url, json=parse_payload) as parse_response:
                parse_response.raise_for_status()
                parse_result = await parse_response.json()

        intent_info = parse_result.get('intent', {})
        intent_name = intent_info.get('name', 'unknown')
        intent_confidence = intent_info.get('confidence', 0.0)
        entities = parse_result.get('entities', [])

        # 2) Send the message to the conversation endpoint
        bot_response = await self.post_message_to_conversation(self.sender_id, message_text)

        # 3) Retrieve tracker data
        tracker_data = await self.get_tracker(self.sender_id)

        # 4) Predict next action
        prediction_data = await self.predict_next_action(self.sender_id)
        if prediction_data:
            scores = prediction_data.get("scores", [])
            if scores:
                next_action = scores[0].get("action", None)
                confidence = scores[0].get("score", 0.0)
            else:
                next_action = None
                confidence = 0.0
        else:
            next_action = None
            confidence = 0.0

        self.active_form = tracker_data.get("active_loop", {}).get("name")
        self.slots = tracker_data.get("slots", {})

        # Optional delay
        if self.active_form:
            await asyncio.sleep(self.sleep_delay)

        return {
            "response": bot_response,
            "intent": {"name": intent_name, "confidence": intent_confidence},
            "entities": entities,
            "active_form": self.active_form,
            "slots": self.slots,
            "tracker_data": tracker_data,
            "next_action": {"name": next_action, "confidence": confidence}
        }

    def get_bot_response_text(self, response: Dict[str, Any]) -> str:
        """
        Extract text from bot response.
        """
        if not response.get("response"):
            return "No response from bot"
        response_texts = []
        for msg in response["response"]:
            if "text" in msg:
                response_texts.append(msg["text"])
        return " ".join(response_texts) if response_texts else "No text response from bot"


def extract_user_info(input_file: str) -> Generator[Tuple[str, Dict[str, Any]], None, None]:
    """
    Incrementally parse user information from a file in a streaming fashion.
    Yields (user_id, {'tuple': (call_id, via, original), 'messages': [...]})
    for each user block found. This avoids building large in-memory structures
    for extremely large files.
    """
    current_user: Optional[str] = None
    current_messages: List[str] = []
    current_tuple: Optional[Tuple[str, str, str]] = None

    with open(input_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('<userStyle'):
                continue

            # We found the start of a new user block
            if line.startswith('User_'):
                # If we already have a user block in progress, yield it first
                if current_user is not None:
                    yield current_user, {
                        'tuple': current_tuple,
                        'messages': current_messages
                    }

                current_messages = []
                current_tuple = None

                # Parse new user ID and tuple
                try:
                    user_id = line.split(' = ')[0].strip()
                    tuple_part = line[line.find('(')+1:line.find(')')]

                    # Only parse if we found parentheses
                    if '(' in line and ')' in line and tuple_part:
                        parts = [
                            p.strip().strip('"').strip("'").strip('+')
                            for p in tuple_part.split(',')
                        ]
                        if len(parts) == 3:
                            call_id = parts[0].strip()
                            via = parts[1].strip()
                            original = parts[2].strip()
                            current_user = user_id
                            current_tuple = (call_id, via, original)
                        else:
                            # If parts length is unexpected, skip
                            current_user = None
                            continue
                    else:
                        # If we fail to parse, skip
                        current_user = None
                        continue

                except Exception as e:
                    print(f"Error parsing user tuple '{line}': {e}")
                    current_user = None
                    current_tuple = None
                    continue
            else:
                # Additional lines for the current user's messages
                if current_user:
                    current_messages.append(line)

        # After the loop ends, yield the final user block if it exists
        if current_user is not None:
            yield current_user, {
                'tuple': current_tuple,
                'messages': current_messages
            }


async def process_file(
    input_file: str,
    output_file: str,
    rasa_port: Optional[int] = None,
    action_port: Optional[int] = None,
    sleep_delay: float = 1.0
) -> None:
    """
    Reads user conversation data from 'input_file' (streamed),
    sends messages to the Rasa server, and writes output to 'output_file'.
    """
    try:
        print(f"Processing input file using Rasa server on port {rasa_port} and "
              f"Action server on port {action_port}...")

        old_umask = os.umask(0o002)  # set umask to 002
        users_found = 0

        try:
            with open(output_file, 'w', encoding='utf-8') as outfile:
                # Write some initial server info using a temporary client
                temp_client = await RasaClient.create(
                    rasa_port=rasa_port,
                    action_port=action_port,
                    sleep_delay=sleep_delay
                )
                try:
                    root_info = await temp_client.get_server_root()
                    version_info = await temp_client.get_server_version()
                    status_info = await temp_client.get_server_status()
                    domain_info = await temp_client.get_domain()

                    outfile.write("=== Server Root Info ===\n")
                    outfile.write(f"{root_info}\n\n")
                    outfile.write("=== Server Version Info ===\n")
                    outfile.write(f"{json.dumps(version_info, indent=2)}\n\n")
                    outfile.write("=== Server Status Info ===\n")
                    outfile.write(f"{json.dumps(status_info, indent=2)}\n\n")
                    outfile.write("=== Domain Info ===\n")
                    outfile.write(f"{json.dumps(domain_info, indent=2)}\n\n")

                    # Demonstration of hitting the train endpoint with dummy data
                    dummy_training_data = {"nlu": [], "stories": []}
                    try:
                        train_response = await temp_client.train_model(dummy_training_data)
                        outfile.write("=== Training Model Response ===\n")
                        outfile.write(f"{json.dumps(train_response, indent=2)}\n\n")
                    except Exception as e:
                        outfile.write("=== Training Model Response ===\n")
                        outfile.write(f"Error encountered during training: {e}\n\n")

                finally:
                    await temp_client.close()

                # Stream through each user block
                for user_id, user_data in extract_user_info(input_file):
                    users_found += 1

                    user_tuple = user_data['tuple']
                    messages = user_data['messages']

                    if not user_tuple:
                        # If we failed to parse the tuple for some reason, skip
                        continue

                    user_tuple_line = f"{user_id} = {user_tuple}"
                    outfile.write(f"{user_tuple_line}\n")
                    print(user_tuple_line)

                    original_number = user_tuple[2]
                    client = await RasaClient.create(
                        original_number=original_number,
                        rasa_port=rasa_port,
                        action_port=action_port,
                        sleep_delay=sleep_delay
                    )

                    try:
                        for message in messages:
                            response_data = await client.send_message(message)

                            intent_name = response_data["intent"]["name"]
                            intent_confidence = response_data["intent"]["confidence"]
                            user_line = f"User: {message} [{intent_name}] [{intent_confidence}]"
                            outfile.write(f"{user_line}\n")
                            print(user_line)

                            bot_text = client.get_bot_response_text(response_data)
                            if bot_text:
                                bot_text = bot_text.replace('[service_response]', '').strip()
                                bot_line = f"Disha: {bot_text}"
                                outfile.write(f"{bot_line}\n")
                                print(bot_line)

                            # Print tracker info
                            tracker_data = response_data.get("tracker_data", {})
                            print("\n" + "="*40)
                            print("TRACKER STATE".center(40))

                            active_form = tracker_data.get("active_loop", {}).get("name")
                            print(f"Active Form: {active_form or 'None'}")
                            print(f"Intent name: {intent_name}")

                            print("\nCurrent Slots:")
                            slots = tracker_data.get("slots", {})
                            for slot, value in slots.items():
                                if value is not None and value != "":
                                    print(f"  - {slot}: {repr(value)}")

                            latest_action = tracker_data.get("latest_action_name", "None")
                            next_action = response_data.get("next_action", {})
                            print(f"\nLatest Action: {latest_action}")
                            print(f"Next Predicted Action: {next_action.get('name')} "
                                  f"(confidence: {next_action.get('confidence', 0.0):.4f})")

                            # Show recent events (up to last 5)
                            print("\nRecent Events:")
                            events = tracker_data.get("events", [])[-5:]
                            for event in reversed(events):
                                event_type = event.get("event")
                                if event_type == "user":
                                    parsed_intent = (
                                        event.get("parse_data", {})
                                             .get("intent", {})
                                             .get("name", "None")
                                    )
                                    print(f"  User: {event.get('text')} → Intent: {parsed_intent}")
                                elif event_type == "bot":
                                    print(f"  Bot: {repr(event.get('text'))}")
                                elif event_type == "action":
                                    print(f"  Action Executed: {event.get('name')}")
                                elif event_type == "slot":
                                    print(f"  Slot Set: {event.get('name')} = {repr(event.get('value'))}")
                                elif event_type == "active_loop":
                                    status = "Started" if event.get("is_active") else "Stopped"
                                    print(f"  Active Loop: {event.get('name')} ({status})")

                            print("="*40 + "\n")
                            await asyncio.sleep(0.1)  # small gap for demonstration

                        outfile.write("\n")
                        print("")

                    finally:
                        await client.close()
                        await asyncio.sleep(0.1)

                # End for all users
                print(f"\nFound {users_found} user blocks to process.\n")

        finally:
            os.umask(old_umask)
            set_file_permissions(output_file)

    except Exception as e:
        print(f"An error occurred in process_file: {str(e)}")
        raise


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('input_file', help='Input file containing messages')
    parser.add_argument('output_file', help='Output file to save responses')
    parser.add_argument('--rasa-port', type=int, help='Rasa server port (default: 5009)')
    parser.add_argument('--action-port', type=int, help='Action server port (default: 5059)')
    parser.add_argument('--sleep-delay', type=float, default=1.0,
                        help='Time to sleep after each user message')
    args = parser.parse_args()

    await process_file(
        input_file=args.input_file,
        output_file=args.output_file,
        rasa_port=args.rasa_port,
        action_port=args.action_port,
        sleep_delay=args.sleep_delay
    )

if __name__ == "__main__":
    asyncio.run(main())
