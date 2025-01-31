import json
import ast
from datetime import datetime
from typing import List, Dict, Any

def fix_json_string(content: str) -> str:
    """Convert single-quoted string to valid JSON."""
    try:
        # Use ast.literal_eval to safely evaluate the string as a Python literal
        python_obj = ast.literal_eval(content)
        # Convert to proper JSON string
        return json.dumps(python_obj)
    except:
        # If ast.literal_eval fails, try basic string replacement
        content = content.replace("'", '"')
        content = content.replace('None', 'null')
        content = content.replace('True', 'true')
        content = content.replace('False', 'false')
        return content

class ConversationLogFormatter:
    def __init__(self, log_data: List[Dict[str, Any]]):
        self.log_data = log_data
        self.formatted_output = []

    def _format_timestamp(self, timestamp: float) -> str:
        """Convert Unix timestamp to readable format."""
        return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')

    def _get_user_interaction(self) -> Dict[str, Any]:
        """Extract user interaction details."""
        user_events = [event for event in self.log_data if event['event'] == 'user']
        if not user_events:
            return {}
        
        user_event = user_events[0]
        return {
            'text': user_event.get('text', ''),
            'intent': user_event['parse_data']['intent']['name'],
            'confidence': user_event['parse_data']['intent']['confidence'],
            'timestamp': self._format_timestamp(user_event['timestamp'])
        }

    def _get_bot_response(self) -> Dict[str, Any]:
        """Extract bot response details."""
        bot_events = [event for event in self.log_data if event['event'] == 'bot']
        if not bot_events:
            return {}
        
        bot_event = bot_events[0]
        return {
            'text': bot_event.get('text', ''),
            'timestamp': self._format_timestamp(bot_event['timestamp'])
        }

    def _get_session_details(self) -> Dict[str, Any]:
        """Extract session metadata."""
        if not self.log_data:
            return {}
        
        first_event = self.log_data[0]
        metadata = first_event.get('metadata', {})
        return {
            'model_id': metadata.get('model_id', ''),
            'assistant_id': metadata.get('assistant_id', ''),
            'channel': next((event['input_channel'] for event in self.log_data 
                           if 'input_channel' in event), 'unknown')
        }

    def _get_slot_updates(self) -> List[Dict[str, Any]]:
        """Extract slot updates."""
        return [{
            'name': event['name'],
            'value': event['value'],
            'timestamp': self._format_timestamp(event['timestamp'])
        } for event in self.log_data if event['event'] == 'slot']

    def _get_action_flow(self) -> List[Dict[str, Any]]:
        """Extract action sequence."""
        return [{
            'name': event['name'],
            'timestamp': self._format_timestamp(event['timestamp']),
            'confidence': event.get('confidence')
        } for event in self.log_data if event['event'] == 'action']

    def format_logs(self) -> str:
        """Format the entire log into readable text."""
        user_interaction = self._get_user_interaction()
        bot_response = self._get_bot_response()
        session_details = self._get_session_details()
        slot_updates = self._get_slot_updates()
        action_flow = self._get_action_flow()

        formatted_text = []
        formatted_text.append("# Conversation Log Analysis\n")

        # User Interaction
        formatted_text.append("## User Interaction")
        if user_interaction:
            formatted_text.append(f"- Text: {user_interaction['text']}")
            formatted_text.append(f"- Intent: {user_interaction['intent']}")
            formatted_text.append(f"- Confidence: {user_interaction['confidence']:.2%}")
            formatted_text.append(f"- Timestamp: {user_interaction['timestamp']}\n")

        # Bot Response
        formatted_text.append("## Bot Response")
        if bot_response:
            formatted_text.append(f"- Text: {bot_response['text']}")
            formatted_text.append(f"- Timestamp: {bot_response['timestamp']}\n")

        # Session Details
        formatted_text.append("## Session Details")
        formatted_text.append(f"- Model ID: {session_details['model_id']}")
        formatted_text.append(f"- Assistant ID: {session_details['assistant_id']}")
        formatted_text.append(f"- Channel: {session_details['channel']}\n")

        # Slot Updates
        formatted_text.append("## Slot Updates")
        for slot in slot_updates:
            formatted_text.append(f"- {slot['name']}: {slot['value']} ({slot['timestamp']})")
        formatted_text.append("")

        # Action Flow
        formatted_text.append("## Action Flow")
        for idx, action in enumerate(action_flow, 1):
            confidence_str = f" (confidence: {action['confidence']:.2%})" if action['confidence'] else ""
            formatted_text.append(f"{idx}. {action['name']}{confidence_str} at {action['timestamp']}")

        return "\n".join(formatted_text)

def read_file_content(file_path: str) -> str:
    """Read file content with proper error handling."""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read().strip()
    except FileNotFoundError:
        raise Exception(f"File not found: {file_path}")
    except UnicodeDecodeError:
        # Try reading with a different encoding if UTF-8 fails
        try:
            with open(file_path, 'r', encoding='latin-1') as file:
                return file.read().strip()
        except:
            raise Exception("Unable to read file with either UTF-8 or Latin-1 encoding")
    except Exception as e:
        raise Exception(f"Error reading file: {str(e)}")

def format_conversation_logs(log_file_path: str) -> str:
    """Read and format conversation logs from a file."""
    try:
        # Read the file content
        content = read_file_content(log_file_path)
        print("File content loaded successfully.")
        
        # Fix the JSON format
        fixed_content = fix_json_string(content)
        print("JSON format fixed successfully.")
        
        # Parse the JSON
        log_data = json.loads(fixed_content)
        print("JSON parsed successfully.")
        
        # Ensure log_data is a list
        if not isinstance(log_data, list):
            log_data = [log_data]
        
        # Format the logs
        formatter = ConversationLogFormatter(log_data)
        return formatter.format_logs()
    
    except json.JSONDecodeError as e:
        error_msg = f"Error: Invalid JSON format in log file: {str(e)}"
        print(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"Error processing log file: {str(e)}"
        print(error_msg)
        return error_msg

def save_output(formatted_text: str, output_file: str):
    """Save the formatted output to a file."""
    try:
        with open(output_file, 'w', encoding='utf-8') as file:
            file.write(formatted_text)
        print(f"\nFormatted output has been saved to {output_file}")
    except Exception as e:
        print(f"Error saving output file: {str(e)}")

if __name__ == "__main__":
    try:
        # Input and output file paths
        input_file = "event.txt"
        output_file = "formatted_events.txt"
        
        print(f"Processing file: {input_file}")
        
        # Format the logs
        formatted_output = format_conversation_logs(input_file)
        
        # Save to file
        save_output(formatted_output, output_file)
        
        # Print to console
        print("\nFormatted Output:")
        print("-" * 50)
        print(formatted_output)
        print("-" * 50)
        
    except Exception as e:
        print(f"Error in main execution: {str(e)}")
