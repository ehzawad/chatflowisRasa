import asyncio
import aiohttp
import json
import argparse
from typing import Dict, Any, Optional, List
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

class RasaClient:
    semaphore = asyncio.Semaphore(10)

    def __init__(
        self,
        rasa_url: str = "http://localhost",
        rasa_port: int = 5005,
        action_port: int = 5055,
        sleep_delay: float = 1.0,
        auth_token: Optional[str] = None,
        jwt_token: Optional[str] = None
    ):
        self.rasa_url = f"{rasa_url}:{rasa_port}"
        self.action_url = f"http://0.0.0.0:{action_port}"
        self.sleep_delay = sleep_delay
        self.sender_id = "user"
        self.active_loop: Optional[str] = None
        self.slots: Dict[str, Any] = {}
        self.session: Optional[aiohttp.ClientSession] = None
        self.auth_token = auth_token
        self.jwt_token = jwt_token
        self.last_event_timestamp = 0.0

    @classmethod
    async def create(cls, *args, **kwargs) -> "RasaClient":
        instance = cls(*args, **kwargs)
        headers = {"Accept": "application/json"}
        if instance.auth_token:
            headers["Authorization"] = f"Token {instance.auth_token}"
        if instance.jwt_token:
            headers["Authorization"] = f"Bearer {instance.jwt_token}"
        instance.session = aiohttp.ClientSession(headers=headers)
        return instance

    async def close(self) -> None:
        if self.session:
            await self.session.close()

    async def reset_conversation(self) -> None:
        """Reset the conversation by posting a restart event."""
        if not self.session:
            raise Exception("Client session is not initialized.")
        
        # Use tracker events endpoint to post restart event
        url = f"{self.rasa_url}/conversations/{self.sender_id}/tracker/events"
        async with self.semaphore:
            try:
                async with self.session.post(url, json=[{"event": "restart"}]) as resp:
                    resp.raise_for_status()
            except Exception as e:
                logger.error(f"Failed to reset conversation: {e}")
                raise
        
        # Reset internal state
        self.last_event_timestamp = 0.0
        self.active_loop = None
        self.slots = {}
        await asyncio.sleep(0.5)  # Brief pause to let reset complete





    # async def send_message(self, message_text: str) -> Dict[str, Any]:


    async def send_message(self, message_text: str) -> Dict[str, Any]:
        if not self.session:
            raise Exception("Client session is not initialized.")

        # Send message
        webhook_url = f"{self.rasa_url}/webhooks/rest/webhook"
        payload = {"sender": self.sender_id, "message": message_text}
        
        async with self.semaphore:
            try:
                async with self.session.post(webhook_url, json=payload) as response:
                    response.raise_for_status()
                    bot_response = await response.json()
            except Exception as e:
                logger.error(f"Error sending message: {e}")
                bot_response = [{"text": "Error communicating with the bot"}]

        # Get tracker data
        url = f"{self.rasa_url}/conversations/{self.sender_id}/tracker"
        async with self.semaphore:
            async with self.session.get(url) as resp:
                tracker_data = await resp.json()

        # Update internal state
        self.active_loop = tracker_data.get("active_loop", {}).get("name")
        self.slots = tracker_data.get("slots", {})

        # Get events
        events = tracker_data.get("events", [])
        
        # Filter new events by checking message_text
        start_collecting = False
        current_message_events = []
        
        for event in events:
            if event.get("event") == "user" and event.get("text") == message_text:
                start_collecting = True
                continue
            if start_collecting:
                current_message_events.append(event)
                if event.get("event") == "action" and event.get("name") == "action_listen":
                    break

        return {
            "response": bot_response,
            "tracker_data": tracker_data,
            "new_events": current_message_events
        }
    

    @staticmethod
    def get_bot_response_text(messages: List[Dict[str, Any]]) -> str:
        if not messages:
            return "No response from bot"
        response_texts = [msg.get("text", "") for msg in messages if "text" in msg]
        return " ".join(response_texts) if response_texts else "No text response from bot"


async def process_file(
    input_file: str,
    output_file: str, 
    rasa_port: Optional[int] = None,
    action_port: Optional[int] = None,
    sleep_delay: float = 1.0,
    auth_token: Optional[str] = None,
    jwt_token: Optional[str] = None
) -> None:
    """Process conversations from file while tracking events properly."""
    
    try:
        logger.info(f"Processing input file using Rasa server on port {rasa_port or 5005} and "
                    f"Action server on port {action_port or 5055}...")

        client = await RasaClient.create(
            rasa_port=rasa_port or 5005,
            action_port=action_port or 5055,
            sleep_delay=sleep_delay,
            auth_token=auth_token,
            jwt_token=jwt_token
        )

        try:
            # Get initial server info
            status_info = await client.get_server_status()
            version_info = await client.get_server_version()
            domain_info = await client.get_domain()

            # Write server info
            with open(output_file, 'w', encoding='utf-8') as outfile:
                outfile.write("=== Server Info ===\n")
                outfile.write(f"{json.dumps(status_info, indent=2)}\n\n")
                outfile.write(f"{json.dumps(version_info, indent=2)}\n\n")
                outfile.write(f"{json.dumps(domain_info, indent=2)}\n\n")

            last_event_index = 0  # Track processed events

            # Process messages
            for user_id, messages in extract_user_info(input_file):
                logger.info(f"Processing conversation for user: {user_id}")

                for message in messages:
                    logger.info(f"Sending message: {message}")
                    response_data = await client.send_message(message)
                    bot_response = response_data["response"]
                    tracker_data = response_data.get("tracker_data", {})

                    with open(output_file, 'a', encoding='utf-8') as outfile:
                        # Write conversation
                        outfile.write(f"User: {message}\n")
                        bot_text = client.get_bot_response_text(bot_response)
                        if bot_text:
                            outfile.write(f"Bot: {bot_text}\n")

                        # Get and filter new events
                        events = tracker_data.get("events", [])
                        new_events = events[last_event_index:]
                        last_event_index = len(events)

                        if new_events:
                            outfile.write("\n" + "="*80 + "\nTRACKER STATE\n" + "="*80 + "\n")
                            for event in new_events:
                                event_type = event.get("event", "unknown")
                                timestamp = event.get("timestamp", "N/A")
                                outfile.write(f"  Event Type: {event_type} | Timestamp: {timestamp}\n")

                                if event_type == "user":
                                    text = event.get("text", "")
                                    intent_info = event.get("parse_data", {}).get("intent", {})
                                    intent_name = intent_info.get("name", "None")
                                    confidence = intent_info.get("confidence", 0.0)
                                    entities = event.get("parse_data", {}).get("entities", [])
                                    
                                    outfile.write(f"    User Message: {text}\n")
                                    outfile.write(f"    Intent: {intent_name} (Confidence: {confidence:.2f})\n")
                                    outfile.write(f"    Entities: {entities}\n")

                                elif event_type == "bot":
                                    text = event.get("text", "")
                                    outfile.write(f"    Bot Message: {text}\n")

                                elif event_type == "action":
                                    action_name = event.get("name", "Unknown Action")
                                    policy = event.get("policy", "None")
                                    confidence = event.get("confidence", "N/A")
                                    action_type = ("Default Action" if action_name in DEFAULT_ACTIONS 
                                                else "Custom Action")
                                    
                                    outfile.write(f"    Action Executed: {action_name} ({action_type})\n")
                                    outfile.write(f"    Policy: {policy}\n")
                                    outfile.write(f"    Confidence: {confidence}\n")

                                elif event_type == "slot":
                                    slot_name = event.get("name", "Unknown Slot")
                                    slot_value = event.get("value", "None")
                                    outfile.write(f"    Slot Set: {slot_name} = {repr(slot_value)}\n")

                                elif event_type == "active_loop":
                                    loop_name = event.get("name", "Unknown Loop")
                                    is_active = event.get("is_active", False)
                                    status = "Started" if is_active else "Stopped"
                                    outfile.write(f"    Active Loop: {loop_name} ({status})\n")

                            outfile.write("="*80 + "\n\n")

                    # Optional delay between messages
                    await asyncio.sleep(0.1)

        finally:
            await client.close()

    except Exception as e:
        logger.error(f"Error in process_file: {str(e)}")
        raise

async def process_conversation(
    client: RasaClient,
    messages: List[str],
    output_file: str
) -> None:
    """Process a single conversation with the given messages."""
    
    for message in messages:
        logger.info(f"Sending message: {message}")
        response_data = await client.send_message(message)

        # Write conversation to file
        with open(output_file, 'a', encoding='utf-8') as outfile:
            # Write user message
            outfile.write(f"User: {message}\n")
            print(f"User: {message}")
            
            # Write bot response
            bot_text = client.get_bot_response_text(response_data["response"])
            if bot_text:
                bot_text = bot_text.replace('[service_response]', '').strip()
                outfile.write(f"Bot: {bot_text}\n")
                print(f"Bot: {bot_text}")

            # Write new events
            new_events = response_data.get("new_events", [])
            if new_events:
                event_header = "\n" + "="*80 + "\nTRACKER STATE\n" + "="*80 + "\n"
                outfile.write(event_header)
                print(event_header)
                
                # Sort events by timestamp to ensure correct order
                new_events.sort(key=lambda x: x.get("timestamp", 0))
                
                for event in new_events:
                    event_type = event.get("event", "unknown")
                    timestamp = event.get("timestamp", "N/A")
                    event_line = f"  Event Type: {event_type} | Timestamp: {timestamp}\n"
                    outfile.write(event_line)
                    print(event_line)

                    # Process event details based on type
                    if event_type == "user":
                        text = event.get("text", "")
                        intent_info = event.get("parse_data", {}).get("intent", {})
                        intent_name = intent_info.get("name", "None")
                        confidence = intent_info.get("confidence", 0.0)
                        entities = event.get("parse_data", {}).get("entities", [])
                        
                        details = [
                            f"    User Message: {text}",
                            f"    Intent: {intent_name} (Confidence: {confidence:.2f})",
                            f"    Entities: {entities}"
                        ]
                        for detail in details:
                            outfile.write(f"{detail}\n")
                            print(detail)
                    
                    elif event_type == "bot":
                        text = event.get("text", "")
                        outfile.write(f"    Bot Message: {text}\n")
                        print(f"    Bot Message: {text}")
                    
                    elif event_type == "action":
                        details = [
                            f"    Action: {event.get('name', 'Unknown')}",
                            f"    Policy: {event.get('policy', 'None')}",
                            f"    Confidence: {event.get('confidence', 'N/A')}"
                        ]
                        for detail in details:
                            outfile.write(f"{detail}\n")
                            print(detail)
                    
                    elif event_type == "slot":
                        slot_name = event.get("name", "Unknown Slot")
                        slot_value = event.get("value", "None")
                        outfile.write(f"    Slot Set: {slot_name} = {slot_value}\n")
                        print(f"    Slot Set: {slot_name} = {slot_value}")
                    
                    elif event_type == "active_loop":
                        status = "Started" if event.get("name") else "Stopped"
                        loop_name = event.get("name", "None")
                        outfile.write(f"    Active Loop: {loop_name} ({status})\n")
                        print(f"    Active Loop: {loop_name} ({status})")

                footer = "="*80 + "\n"
                outfile.write(footer)
                print(footer)
            outfile.write("\n")
            print("")

        await asyncio.sleep(0.1)


async def main(
    input_file: str,
    output_file: str,
    rasa_port: int = 5005,
    action_port: int = 5055,
    sleep_delay: float = 1.0
) -> None:
    # Initialize client
    client = await RasaClient.create(
        rasa_port=rasa_port,
        action_port=action_port,
        sleep_delay=sleep_delay
    )

    try:
        # Read messages from input file
        with open(input_file, 'r', encoding='utf-8') as f:
            messages = [line.strip() for line in f if line.strip() and not line.startswith('<')]

        # Clear output file
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("=== New Conversation ===\n\n")

        # Process conversation
        await process_conversation(client, messages, output_file)
        
    finally:
        await client.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rasa Client Script")
    parser.add_argument('input_file', help='Input file containing messages')
    parser.add_argument('output_file', help='Output file to save responses')
    parser.add_argument('--rasa-port', type=int, default=5005)
    parser.add_argument('--action-port', type=int, default=5055)
    parser.add_argument('--sleep-delay', type=float, default=1.0)
    
    args = parser.parse_args()
    
    asyncio.run(main(
        args.input_file,
        args.output_file,
        args.rasa_port,
        args.action_port,
        args.sleep_delay
    ))
