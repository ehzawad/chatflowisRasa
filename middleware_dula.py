import requests
import asyncio
from typing import List

class RasaChatClient:
    def __init__(self, base_url: str):
        self.webhook_url = f"{base_url}/webhooks/rest/webhook"

    async def send_message(self, message: str) -> List[str]:
        try:
            response = requests.post(
                self.webhook_url,
                json={"sender": "user", "message": message},
                timeout=10
            )
            if response.status_code == 200:
                return [f"Bot: {bot_response['text']}" for bot_response in response.json() if "text" in bot_response]
            return [f"Error: Received status code {response.status_code}"]
        except requests.exceptions.RequestException as e:
            return [f"Error: Could not connect to Rasa server: {str(e)}"]

    async def start_conversation(self):
        print("Bot: Hello! I'm your Rasa chatbot. Type 'quit' to exit.")
        while True:
            user_message = input("You: ").strip()
            if user_message.lower() == 'quit':
                print("Bot: Goodbye!")
                break
            bot_responses = await self.send_message(user_message)
            for response in bot_responses:
                print(response)

async def main():
    # Choose the Rasa server you want to interact with
    server_choice = input("Choose a server (1 for ProjectA, 2 for ProjectB): ").strip()
    if server_choice == "1":
        client = RasaChatClient(base_url="http://localhost:5005")
    elif server_choice == "2":
        client = RasaChatClient(base_url="http://localhost:5006")
    else:
        print("Invalid choice. Exiting.")
        return
    await client.start_conversation()

if __name__ == "__main__":
    asyncio.run(main())
