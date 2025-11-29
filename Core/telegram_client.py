"""
Telegram Bot Client
Handle Telegram bot interactions
"""
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from typing import Callable, Optional
from utils.config import Config
from utils.logger import logger

class TelegramClient:
    def __init__(self):
        self.token = Config.TELEGRAM_BOT_TOKEN
        self.chat_id = Config.TELEGRAM_CHAT_ID
        self.app = None
        
        # Callbacks
        self.on_signal_callback: Optional[Callable] = None
        self.on_command_callback: Optional[Callable] = None
    
    async def initialize(self):
        """Initialize Telegram bot"""
        try:
            self.app = Application.builder().token(self.token).build()
            
            # Add handlers
            self.app.add_handler(CommandHandler("start", self._cmd_start))
            self.app.add_handler(CommandHandler("status", self._cmd_status))
            self.app.add_handler(CommandHandler("balance", self._cmd_balance))
            self.app.add_handler(CommandHandler("positions", self._cmd_positions))
            self.app.add_handler(CommandHandler("close", self._cmd_close))
            self.app.add_handler(CommandHandler("stop", self._cmd_stop))
            self.app.add_handler(CommandHandler("help", self._cmd_help))
            
            # Message handler for signals
            self.app.add_handler(
                MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message)
            )
            
            logger.info("Telegram bot initialized")
            
        except Exception as e:
            logger.error(f"Telegram init error: {str(e)}")
            raise
    
    async def start(self):
        """Start bot polling"""
        if not self.app:
            await self.initialize()
        
        logger.info("Starting Telegram bot...")
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling(drop_pending_updates=True)
    
    async def stop(self):
        """Stop bot"""
        if self.app:
            logger.info("Stopping Telegram bot...")
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()
    
    async def send_message(self, text: str, parse_mode: str = "HTML"):
        """Send message to configured chat"""
        try:
            if self.app and self.app.bot:
                await self.app.bot.send_message(
                    chat_id=self.chat_id,
                    text=text,
                    parse_mode=parse_mode
                )
        except Exception as e:
            logger.error(f"Send message error: {str(e)}")
    
    def set_signal_callback(self, callback: Callable):
        """Set callback for signal processing"""
        self.on_signal_callback = callback
    
    def set_command_callback(self, callback: Callable):
        """Set callback for command processing"""
        self.on_command_callback = callback
    
    # Command handlers
    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        await update.message.reply_text(
            "🤖 Trading Bot Started!\n\n"
            "Send trading signals to execute trades.\n"
            "Use /help to see available commands."
        )
    
    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_text = """
📚 <b>Available Commands:</b>

/start - Start the bot
/status - Show bot status
/balance - Check account balance
/positions - List open positions
/close [SYMBOL] - Close position
/stop - Stop the bot
/help - Show this help

<b>Signal Format:</b>
SYMBOL: BTCUSDT
SIDE: LONG
ENTRY: 50000
SL: 49000
TP: 52000, 54000
LEVERAGE: 10X
        """
        await update.message.reply_text(help_text, parse_mode="HTML")
    
    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        if self.on_command_callback:
            response = await self.on_command_callback("status", None)
            await update.message.reply_text(response, parse_mode="HTML")
        else:
            await update.message.reply_text("Bot is running ✅")
    
    async def _cmd_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /balance command"""
        if self.on_command_callback:
            response = await self.on_command_callback("balance", None)
            await update.message.reply_text(response, parse_mode="HTML")
        else:
            await update.message.reply_text("Balance command not available")
    
    async def _cmd_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /positions command"""
        if self.on_command_callback:
            response = await self.on_command_callback("positions", None)
            await update.message.reply_text(response, parse_mode="HTML")
        else:
            await update.message.reply_text("No positions found")
    
    async def _cmd_close(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /close command"""
        # Extract symbol from command
        args = context.args
        symbol = args[0] if args else None
        
        if not symbol:
            await update.message.reply_text("Usage: /close [SYMBOL]\nExample: /close BTCUSDT")
            return
        
        if self.on_command_callback:
            response = await self.on_command_callback("close", symbol.upper())
            await update.message.reply_text(response, parse_mode="HTML")
        else:
            await update.message.reply_text(f"Close command not available")
    
    async def _cmd_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stop command"""
        await update.message.reply_text("⚠️ Stopping bot... All positions will remain open.")
        if self.on_command_callback:
            await self.on_command_callback("stop", None)
    
    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming messages (signals)"""
        message_text = update.message.text
        
        # Forward to signal callback
        if self.on_signal_callback:
            await self.on_signal_callback(message_text)
        else:
            logger.warning("No signal callback configured")
    
    async def send_alert(self, title: str, message: str, level: str = "INFO"):
        """
        Send formatted alert
        
        Args:
            title: Alert title
            message: Alert message
            level: INFO/WARNING/ERROR
        """
        emoji_map = {
            "INFO": "ℹ️",
            "WARNING": "⚠️",
            "ERROR": "🚨",
            "SUCCESS": "✅"
        }
        
        emoji = emoji_map.get(level.upper(), "📢")
        
        formatted = f"{emoji} <b>{title}</b>\n\n{message}"
        await self.send_message(formatted)
    
    async def send_trade_notification(
        self,
        symbol: str,
        side: str,
        entry: float,
        quantity: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ):
        """Send trade execution notification"""
        message = f"""
🎯 <b>TRADE EXECUTED</b>

Symbol: {symbol}
Side: {side}
Entry: {entry}
Quantity: {quantity}
"""
        
        if stop_loss:
            message += f"Stop Loss: {stop_loss}\n"
        
        if take_profit:
            message += f"Take Profit: {take_profit}\n"
        
        await self.send_message(message)
    
    async def send_position_update(
        self,
        symbol: str,
        pnl: float,
        pnl_percent: float,
        unrealized_pnl: float
    ):
        """Send position update"""
        pnl_emoji = "📈" if pnl > 0 else "📉"
        
        message = f"""
{pnl_emoji} <b>POSITION UPDATE</b>

Symbol: {symbol}
PnL: ${pnl:.2f} ({pnl_percent:.2f}%)
Unrealized: ${unrealized_pnl:.2f}
"""
        
        await self.send_message(message)
    
    async def send_error(self, error_msg: str):
        """Send error notification"""
        await self.send_alert("ERROR", error_msg, "ERROR")