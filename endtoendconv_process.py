import asyncio
import aiohttp
import json
import time
import argparse
import os
import pwd
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class RasaClient:
    def __init__(
        self,
        original_number: str = "01568725958",
        rasa_port: Optional[int] = None,
        action_port: Optional[int] = None
    ):
        """Initialize Rasa client that mimics middleware behavior."""
        current_time = int(time.time() * 1000)

        # Use default ports if not specified
        self.rasa_port = rasa_port or 5005
        self.action_port = action_port or 5054

        # Configure base URLs with appropriate ports
        self.rasa_base_url = f"http://localhost:{self.rasa_port}"
        self.action_base_url = f"http://localhost:{self.action_port}"
        
        self.via_number = "8809611888444"  # Fixed via number
        self.original_number = original_number

        # Test numbers for masking
        self.test_numbers = [
            '09696387582', '09638372914', '01924560627', '01518472623',
            '01580582654', '01833626976', '01571321136', '01764655648',
            '09638317055', '09638080760', '09696173224', '09611888444',
            '01911310316', '19723182900', '01558666739', '01714007806',
            '01714020387'
        ]

        # Handle number masking
        if original_number[-11:] in self.test_numbers:
            self.masked_number = '01568725958'
        else:
            self.masked_number = original_number

        # Construct sender_id with fixed via number
        self.sender_id = f"{current_time}_{self.via_number}_{self.masked_number}"

        self.active_form = None
        self.slots = {}
        self.session = None  # Will be initialized in connect()
        
    async def connect(self):
        """Create aiohttp session if not already created."""
        if self.session is None:
            timeout = aiohttp.ClientTimeout(total=30)  # 30 second timeout
            self.session = aiohttp.ClientSession(timeout=timeout)

    async def close(self):
        """Close the aiohttp session."""
        if self.session:
            await self.session.close()
            self.session = None

    async def send_message(self, message_text: str) -> Dict[Any, Any]:
        """Send message to Rasa server and get response."""
        try:
            await self.connect()
            
            # First get NLU parse result
            async with self.session.post(
                f"{self.rasa_base_url}/model/parse",
                json={"text": message_text},
                raise_for_status=True
            ) as parse_response:
                parse_result = await parse_response.json()
                intent_info = parse_result.get('intent', {})
                intent_name = intent_info.get('name', 'unknown')
                intent_confidence = intent_info.get('confidence', 0.0)
                entities = parse_result.get('entities', [])

            # Send message to webhook
            async with self.session.post(
                f"{self.rasa_base_url}/webhooks/rest/webhook",
                json={"sender": self.sender_id, "message": message_text},
                raise_for_status=True
            ) as response:
                bot_response = await response.json()

            # Get tracker state
            async with self.session.get(
                f"{self.rasa_base_url}/conversations/{self.sender_id}/tracker",
                raise_for_status=True
            ) as tracker_response:
                tracker_data = await tracker_response.json()

            # Get next action prediction
            async with self.session.post(
                f"{self.rasa_base_url}/conversations/{self.sender_id}/predict",
                raise_for_status=True
            ) as predict_response:
                prediction = await predict_response.json()
                next_action = prediction.get("scores", [{}])[0].get("action", "None")
                confidence = prediction.get("scores", [{}])[0].get("score", 0.0)

            self.active_form = tracker_data.get("active_loop", {}).get("name")
            self.slots = tracker_data.get("slots", {})

            return {
                "response": bot_response,
                "intent": {"name": intent_name, "confidence": intent_confidence},
                "entities": entities,
                "active_form": self.active_form,
                "slots": self.slots,
                "tracker_data": tracker_data,
                "next_action": {
                    "name": next_action,
                    "confidence": confidence
                }
            }

        except aiohttp.ClientError as e:
            logger.error(f"Error communicating with Rasa server: {str(e)}")
            return {
                "response": [],
                "intent": {"name": "unknown", "confidence": 0.0},
                "entities": [],
                "active_form": None,
                "slots": {},
                "tracker_data": {},
                "next_action": {"name": "None", "confidence": 0.0}
            }
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            raise

    def get_bot_response_text(self, response: Dict[Any, Any]) -> str:
        """Extract text from bot response."""
        if not response.get("response"):
            return "No response from bot"

        response_texts = []
        for message in response["response"]:
            if "text" in message:
                response_texts.append(message["text"])

        return " ".join(response_texts) if response_texts else "No text response from bot"

def extract_user_info(input_file: str) -> Dict[str, Dict]:
    """Extract user information and messages from input file."""
    users = {}
    current_user = None
    current_messages = []

    with open(input_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()

            # Skip empty lines and style tags
            if not line or line.startswith('<userStyle'):
                continue

            # If we find a User line
            if line.startswith('User_'):
                # Save previous user's messages if any
                if current_user and current_messages:
                    users[current_user]['messages'] = current_messages
                    current_messages = []

                try:
                    # Extract the exact User_ identifier from the input line
                    user_id = line.split(' = ')[0].strip()

                    # Extract the content between parentheses
                    tuple_str = line[line.find('(')+1:line.find(')')]
                    # Split by comma and clean up each part
                    parts = [part.strip().strip('"').strip("'").strip('+') for part in tuple_str.split(',')]

                    call_id = parts[0].strip()
                    via = parts[1].strip()
                    original = parts[2].strip()

                    # Use the exact User_ identifier from input
                    current_user = user_id
                    users[current_user] = {
                        'tuple': (call_id, via, original),
                        'messages': []
                    }
                except Exception as e:
                    logger.error(f"Error parsing user tuple '{line}': {e}")
                    continue

            # If not a user line and not empty, add to current messages
            elif current_user and line:
                current_messages.append(line)

    # Don't forget last user's messages
    if current_user and current_messages:
        users[current_user]['messages'] = current_messages

    return users

def print_tracker_state(response_data: Dict[str, Any]):
    """Print formatted tracker state information."""
    print("\n" + "="*40)
    print("TRACKER STATE".center(40))

    tracker_data = response_data.get("tracker_data", {})
    
    # Active form
    active_form = tracker_data.get("active_loop", {}).get("name")
    print(f"Active Form: {active_form or 'None'}")

    # Intent
    intent_name = response_data["intent"]["name"]
    print(f"Intent Name: {intent_name}")

    # Slots
    print("\nCurrent Slots:")
    slots = tracker_data.get("slots", {})
    for slot, value in slots.items():
        if value:  # Only print non-empty slots
            print(f"  - {slot}: {repr(value)}")

    # Actions
    latest_action = tracker_data.get("latest_action_name", "None")
    next_action = response_data.get("next_action", {})
    print(f"\nLatest Action: {latest_action}")
    print(f"Next Predicted Action: {next_action.get('name')} (confidence: {next_action.get('confidence', 0.0):.4f})")

    # Recent Events
    print("\nRecent Events:")
    events = tracker_data.get("events", [])[-5:]  # Last 5 events
    for event in reversed(events):
        event_type = event.get("event")
        if event_type == "user":
            intent = event.get("parse_data", {}).get("intent", {}).get("name", "None")
            print(f"  User: {event.get('text')} → Intent: {intent}")
        elif event_type == "bot":
            print(f"  Bot: {repr(event.get('text'))}")
        elif event_type == "action":
            print(f"  Action Executed: {event.get('name')}")
        elif event_type == "slot":
            print(f"  Slot Set: {event.get('name')} = {repr(event.get('value'))}")
        elif event_type == "active_loop":
            status = "Started" if event.get("name") else "Stopped"
            print(f"  Active Loop: {event.get('name', 'None')} ({status})")
            
    print("="*40 + "\n")

def set_file_permissions(filepath: str):
    """Set file permissions and ownership to appadm:appadm with 664 permissions."""
    try:
        # Get appadm user and group IDs
        uid = pwd.getpwnam('appadm').pw_uid
        gid = pwd.getpwnam('appadm').pw_gid

        # Set ownership to appadm:appadm
        os.chown(filepath, uid, gid)

        # Set permissions to -rw-rw-r-- (664)
        os.chmod(filepath, 0o664)

    except Exception as e:
        logger.warning(f"Could not set file permissions/ownership: {e}")

async def process_file(
    input_file: str,
    output_file: str,
    rasa_port: Optional[int] = None,
    action_port: Optional[int] = None
):
    try:
        logger.info(f"Starting to process input file using Rasa server on port {rasa_port or 5005}")
        users = extract_user_info(input_file)

        if not users:
            logger.error("No valid user information found in input file")
            return

        logger.info(f"Found {len(users)} users to process")

        # Get appadm user and group IDs
        try:
            uid = pwd.getpwnam('appadm').pw_uid
            gid = pwd.getpwnam('appadm').pw_gid
        except KeyError:
            logger.warning("appadm user not found, using current user permissions")
            uid = os.getuid()
            gid = os.getgid()

        # Set umask to 002 (this will result in 664 permissions)
        old_umask = os.umask(0o002)

        try:
            with open(output_file, 'w', encoding='utf-8') as outfile:
                try:
                    os.chown(output_file, uid, gid)
                except PermissionError:
                    logger.warning("Could not change file ownership")

                for user_id, user_data in users.items():
                    user_tuple = user_data['tuple']
                    messages = user_data['messages']

                    # Write user tuple
                    user_tuple_line = f"{user_id} = {user_tuple}"
                    outfile.write(f"{user_tuple_line}\n")
                    print(user_tuple_line)

                    original_number = user_tuple[2]
                    client = RasaClient(
                        original_number=original_number,
                        rasa_port=rasa_port,
                        action_port=action_port
                    )

                    try:
                        await client.connect()  # Ensure connection is established

                        for msg_idx, message in enumerate(messages, 1):
                            try:
                                response_data = await client.send_message(message)

                                # Print user message with intent
                                intent_name = response_data["intent"]["name"]
                                intent_confidence = response_data["intent"]["confidence"]
                                user_line = f"User: {message} [{intent_name}] [{intent_confidence:.4f}]"
                                outfile.write(f"{user_line}\n")
                                print(user_line)

                                # Print bot response
                                bot_text = client.get_bot_response_text(response_data)
                                if bot_text:
                                    bot_text = bot_text.replace('[service_response]', '').strip()
                                    bot_line = f"Disha: {bot_text}"
                                    outfile.write(f"{bot_line}\n")
                                    print(f"{bot_line}")

                                # Print detailed tracker state
                                print_tracker_state(response_data)

                                await asyncio.sleep(0.5)  # Reduced sleep time

                            except Exception as e:
                                logger.error(f"Error processing message {msg_idx}: {str(e)}")
                                continue

                        outfile.write("\n")
                        print("")

                    finally:
                        await client.close()  # Ensure client is properly closed

                    await asyncio.sleep(0.5)  # Small delay between users

        finally:
            os.umask(old_umask)
            try:
                set_file_permissions(output_file)
            except Exception as e:
                logger.warning(f"Could not set file permissions: {str(e)}")

    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        raise

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('input_file', help='Input file containing messages')
    parser.add_argument('output_file', help='Output file to save responses')
    parser.add_argument('--rasa-port', type=int, help='Rasa server port (default: 5005)')
    parser.add_argument('--action-port', type=int, help='Action server port (default: 5054)')

    args = parser.parse_args()

    # Don't use asyncio.run() here, just await the coroutine
    await process_file(
        args.input_file,
        args.output_file,
        rasa_port=args.rasa_port,
        action_port=args.action_port
    )

if __name__ == "__main__":
    # Only use asyncio.run() at the top level
    asyncio.run(main())