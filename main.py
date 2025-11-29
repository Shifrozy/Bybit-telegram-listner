import os
from dotenv import load_dotenv
from Core.telegram_client import TelegramClient

# Load environment variables from the .env file
load_dotenv()

def main():
    # Get values from .env file
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    group_id = os.getenv("TELEGRAM_GROUP_ID")

    # Initialize the Telegram client
    telegram_bot = TelegramClient(bot_token, group_id)

    try:
        # Start the Telegram bot
        telegram_bot.start()
    except KeyboardInterrupt:
        print("Bot stopped manually.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
