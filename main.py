from Core.telegram_client import TelegramClient
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def main():
    # Configuration: get from environment variables
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    group_id = os.getenv("TELEGRAM_GROUP_ID")

    # Initialize the Telegram client
    telegram_bot = TelegramClient(api_id, api_hash, bot_token, group_id)

    try:
        # Start the Telegram bot
        telegram_bot.start()
    except KeyboardInterrupt:
        print("Bot stopped manually.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
