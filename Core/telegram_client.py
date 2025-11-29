from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
import logging
from .signal_parser import parse_signal  # Import the signal parser to process the signals

# Enable logging to debug or track bot activities
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# Command handler for /start command
def start(update: Update, context: CallbackContext) -> None:
    update.message.reply_text('Hello! I am your trading bot. Send me a signal to process.')

# Handle trading signal messages
def handle_signal(update: Update, context: CallbackContext) -> None:
    signal_text = update.message.text  # Get the text of the signal sent by the user
    
    # Parse the signal using our signal parser
    signal = parse_signal(signal_text)
    
    # If the signal is valid, send the processed message
    if signal["validation"]["status"] == "valid":
        update.message.reply_text(f"Processed Signal: {signal['signal']}")
    else:
        # If the signal is invalid, send the errors
        update.message.reply_text(f"Invalid Signal: {signal['validation']['errors']}")

def main():
    """Start the bot and listen for messages."""
    # Set up your bot token from BotFather here
    bot_token = "YOUR_BOT_TOKEN"  # Replace with your actual bot token
    
    # Create an Application object using your bot's token
    application = Application.builder().token(bot_token).build()

    # Get the dispatcher to register handlers
    dispatcher = application.dispatcher

    # Handle /start command
    dispatcher.add_handler(CommandHandler("start", start))

    # Handle all text messages (signals)
    dispatcher.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_signal))

    # Start the bot and run it until you press Ctrl+C
    application.run_polling()

if __name__ == '__main__':
    main()
