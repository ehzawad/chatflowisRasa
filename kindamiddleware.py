import asyncio
import aiohttp
import requests
import json
import time
import argparse
import os
import pwd
from typing import Dict, Any, Optional, List
from datetime import datetime

class RasaClient:
    def __init__(self, 
                rasa_url: str = "http://localhost:5005", 
                original_number: str = "01568725958",
                rasa_port: Optional[int] = None,
                action_port: Optional[int] = None):
        """Initialize Rasa client that mimics middleware behavior."""
        current_time = int(time.time() * 1000)

        # Allow port override
        # Use default ports if not specified 
        self.rasa_port = rasa_port or 5005
        self.action_port = action_port or 5055

        # Configure URLs with appropriate ports
        self.rasa_url = f"http://localhost:{self.rasa_port}"
        self.action_url = f"http://localhost:{self.action_port}"
        self.via_number = "8809611888444"  # Always fixed
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
        
        self.rasa_url = rasa_url
        self.active_form = None
        self.slots = {}
        self.session = aiohttp.ClientSession()

    async def close(self):
        """Close the aiohttp session."""
        await self.session.close()

    async def send_message(self, message_text: str) -> Dict[Any, Any]:
        """Send message to Rasa server and get response."""
        try:
            # First get NLU parse result
            async with self.session.post(
                f"{self.rasa_url}/model/parse",
                json={"sender": self.sender_id, "text": message_text}
            ) as parse_response:
                parse_result = await parse_response.json()
                intent_info = parse_result.get('intent', {})
                intent_name = intent_info.get('name', 'unknown')
                intent_confidence = intent_info.get('confidence', 0.0)
                entities = parse_result.get('entities', [])
                
                if intent_name == 'inform':
                    message_text = message_text.replace('মাস', 'পাঁচ')

            # Send message to webhook
            payload = {"sender": self.sender_id, "message": message_text}
            async with self.session.post(
                f"{self.rasa_url}/webhooks/rest/webhook",
                json=payload
            ) as response:
                bot_response = await response.json()

            # Get tracker state
            async with self.session.get(
                f"{self.rasa_url}/conversations/{self.sender_id}/tracker"
            ) as tracker_response:
                tracker_data = await tracker_response.json()

            self.active_form = tracker_data.get("active_loop", {}).get("name")
            self.slots = tracker_data.get("slots", {})

            if self.active_form:
                await asyncio.sleep(1)

            return {
                "response": bot_response,
                "intent": {"name": intent_name, "confidence": intent_confidence},
                "entities": entities,
                "active_form": self.active_form,
                "slots": self.slots,
                "tracker_data": tracker_data
            }

        except Exception as e:
            print(f"Error communicating with Rasa server: {e}")
            return {
                "response": [],
                "intent": {"name": "unknown", "confidence": 0.0},
                "entities": [],
                "active_form": None,
                "slots": {},
                "tracker_data": {}
            }

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
                    print(f"Error parsing user tuple '{line}': {e}")
                    continue
            
            # If not a user line and not empty, add to current messages
            elif current_user and line:
                current_messages.append(line)
    
    # Don't forget last user's messages
    if current_user and current_messages:
        users[current_user]['messages'] = current_messages
    
    return users

async def process_file(
    input_file: str, 
    output_file: str, 
    rasa_port: Optional[int] = None,
    action_port: Optional[int] = None
):
    try:
        print(f"\nStarting to process input file using Rasa server on port {rasa_port} and Action server on port {action_port}...")
        users = extract_user_info(input_file)

        if not users:
            print("No valid user information found in input file")
            return

        print(f"\nFound {len(users)} users to process\n")
        
        # Get appadm user and group IDs
        uid = pwd.getpwnam('appadm').pw_uid
        gid = pwd.getpwnam('appadm').pw_gid
        
        # Set umask to 002 (this will result in 664 permissions)
        old_umask = os.umask(0o002)
        
        try:
            # Create the file with proper ownership
            with open(output_file, 'w', encoding='utf-8') as outfile:
                os.chown(output_file, uid, gid)  # Set ownership right after creation
                
                for user_id, user_data in users.items():
                    user_tuple = user_data['tuple']
                    messages = user_data['messages']
                    
                    # Write user tuple preserving original User_ format
                    user_tuple_line = f"{user_id} = {user_tuple}"
                    outfile.write(f"{user_tuple_line}\n")
                    print(user_tuple_line)
                    
                    original_number = user_tuple[2]
                    
                    # Create RasaClient with proper ports
                    client = RasaClient(
                        original_number=original_number, 
                        rasa_port=rasa_port, 
                        action_port=action_port
                    )
                    
                    for msg_idx, message in enumerate(messages, 1):
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
                            print(f"{bot_line}")
                        
                        await asyncio.sleep(1)
                    
                    outfile.write("\n")
                    print("")
                    await client.close()
                    await asyncio.sleep(1)

        finally:
            # Restore original umask
            os.umask(old_umask)
            
    except Exception as e:
        print(f"An error occurred: {e}")
        raise e

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
        print(f"Warning: Could not set file permissions/ownership: {e}")

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('input_file', help='Input file containing messages')
    parser.add_argument('output_file', help='Output file to save responses')
    parser.add_argument('--rasa-port', type=int, help='Rasa server port (default: 5005)')
    parser.add_argument('--action-port', type=int, help='Action server port (default: 5055)')
    
    args = parser.parse_args()
    
    # Directly await process_file instead of using asyncio.run()
    await process_file(
        args.input_file,
        args.output_file,
        rasa_port=args.rasa_port,
        action_port=args.action_port
    )

if __name__ == "__main__":
    # Only use asyncio.run() at the top level
    asyncio.run(main())
