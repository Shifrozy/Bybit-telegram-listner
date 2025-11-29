"""
Main Trading Bot
Orchestrates all components
"""
import asyncio
from core.bybit_client import BybitClient
from core.telegram_client import TelegramClient
from core.signal_parser import SignalParser
from core.order_engine import OrderEngine
from core.pyramid_engine import PyramidEngine
from core.trailing_engine import TrailingEngine
from core.hedge_engine import HedgeEngine
from core.reentry_engine import ReentryEngine
from core.risk_manager import RiskManager
from utils.config import Config
from utils.logger import logger

class TradingBot:
    def __init__(self):
        # Initialize components
        self.bybit = BybitClient()
        self.telegram = TelegramClient()
        self.signal_parser = SignalParser()
        self.risk = RiskManager()
        
        # Initialize engines
        self.orders = OrderEngine(self.bybit, self.risk)
        self.pyramid = PyramidEngine(self.bybit, self.orders)
        self.trailing = TrailingEngine(self.bybit)
        self.hedge = HedgeEngine(self.bybit, self.orders)
        self.reentry = ReentryEngine(self.bybit, self.orders)
        
        # Bot state
        self.is_running = False
        self.active_trades = {}
    
    async def start(self):
        """Start the trading bot"""
        logger.info("=" * 60)
        logger.info("🚀 TRADING BOT STARTING")
        logger.info("=" * 60)
        
        # Validate configuration
        if not Config.validate():
            logger.error("Invalid configuration! Check .env file")
            return
        
        # Set Telegram callbacks
        self.telegram.set_signal_callback(self.handle_signal)
        self.telegram.set_command_callback(self.handle_command)
        
        # Start Telegram bot
        await self.telegram.initialize()
        await self.telegram.start()
        
        # Start trailing monitor
        asyncio.create_task(self.trailing.start_monitoring())
        
        # Start position monitor
        asyncio.create_task(self.monitor_positions())
        
        self.is_running = True
        
        await self.telegram.send_alert(
            "Bot Started",
            f"Trading bot is now active\n"
            f"Testnet: {Config.BYBIT_TESTNET}\n"
            f"Max Positions: {Config.MAX_OPEN_POSITIONS}\n"
            f"Max Daily Loss: ${Config.MAX_DAILY_LOSS}",
            "SUCCESS"
        )
        
        logger.info("✅ Bot started successfully")
    
    async def stop(self):
        """Stop the trading bot"""
        logger.info("Stopping bot...")
        
        self.is_running = False
        
        # Stop trailing monitor
        self.trailing.stop_monitoring()
        
        # Close Telegram
        await self.telegram.stop()
        
        # Close Bybit client
        await self.bybit.close()
        
        logger.info("✅ Bot stopped")
    
    async def handle_signal(self, message_text: str):
        """
        Handle incoming trading signal
        
        Args:
            message_text: Raw signal text from Telegram
        """
        try:
            # Check for close signal
            close_symbol = self.signal_parser.parse_close_signal(message_text)
            if close_symbol:
                await self.close_position(close_symbol)
                return
            
            # Check for update signal
            update = self.signal_parser.parse_update_signal(message_text)
            if update:
                await self.update_position(update)
                return
            
            # Parse trading signal
            signal = self.signal_parser.parse_signal(message_text)
            if not signal:
                logger.warning("Could not parse signal")
                return
            
            # Log signal
            logger.info(f"Signal received: {signal['symbol']} {signal['side']}")
            
            # Send confirmation
            summary = self.signal_parser.format_signal_summary(signal)
            await self.telegram.send_message(summary)
            
            # Execute trade
            await self.execute_trade(signal)
            
        except Exception as e:
            logger.error(f"Signal handling error: {str(e)}")
            await self.telegram.send_error(f"Signal error: {str(e)}")
    
    async def execute_trade(self, signal: dict):
        """Execute trade from signal"""
        try:
            symbol = signal["symbol"]
            side = signal["side"]
            entry = signal["entry"]
            
            # Check risk limits
            can_trade, reason = self.risk.can_open_position()
            if not can_trade:
                logger.warning(f"Trade blocked: {reason}")
                await self.telegram.send_alert("Trade Blocked", reason, "WARNING")
                return
            
            # Get balance
            balance = await self.bybit.get_balance()
            if not balance:
                logger.error("Could not fetch balance")
                return
            
            # Set leverage
            leverage = signal.get("leverage", Config.DEFAULT_LEVERAGE)
            await self.bybit.set_leverage(symbol, leverage)
            
            # Calculate position size
            stop_loss = signal.get("stop_loss")
            if stop_loss:
                quantity = self.risk.calculate_position_size(
                    balance=balance,
                    entry_price=entry,
                    stop_loss=stop_loss,
                    leverage=leverage
                )
            else:
                # Default 1% of balance
                quantity = (balance * 0.01 * leverage) / entry
            
            # Validate order
            is_valid, msg = self.risk.validate_order(symbol, quantity, entry, stop_loss)
            if not is_valid:
                logger.error(f"Order validation failed: {msg}")
                await self.telegram.send_alert("Order Invalid", msg, "ERROR")
                return
            
            # Check for pyramid entries
            if signal.get("entries") and len(signal["entries"]) > 1:
                # Use pyramid strategy
                await self.execute_pyramid_trade(signal, quantity)
            else:
                # Use dual limit strategy
                take_profit = signal["targets"][0] if signal.get("targets") else None
                
                success = await self.orders.execute_dual_limit(
                    symbol=symbol,
                    side=side,
                    entry_price=entry,
                    quantity=quantity,
                    stop_loss=stop_loss,
                    take_profit=take_profit
                )
                
                if success:
                    # Track position
                    self.active_trades[symbol] = signal
                    
                    # Add to risk manager
                    self.risk.add_position(symbol, {
                        "entry_price": entry,
                        "quantity": quantity,
                        "side": side,
                        "stop_loss": stop_loss,
                        "take_profit": take_profit
                    })
                    
                    # Enable trailing stop
                    self.trailing.enable_trailing(symbol, side, entry)
                    
                    # Send notification
                    await self.telegram.send_trade_notification(
                        symbol, side, entry, quantity, stop_loss, take_profit
                    )
                    
                    logger.info(f"✅ Trade executed: {symbol}")
                else:
                    logger.error(f"Trade execution failed: {symbol}")
            
        except Exception as e:
            logger.error(f"Trade execution error: {str(e)}")
            await self.telegram.send_error(f"Execution error: {str(e)}")
    
    async def execute_pyramid_trade(self, signal: dict, total_quantity: float):
        """Execute pyramid scaling trade"""
        symbol = signal["symbol"]
        side = signal["side"]
        entries = signal["entries"]
        
        # Use first and last entry as range
        entry_price = entries[0]
        target_price = entries[-1]
        
        success = await self.pyramid.initialize_pyramid(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            target_price=target_price,
            total_quantity=total_quantity,
            stop_loss=signal.get("stop_loss")
        )
        
        if success:
            self.active_trades[symbol] = signal
            await self.telegram.send_alert(
                "Pyramid Trade",
                f"{symbol} pyramid initialized\n"
                f"Steps: {Config.PYRAMID_STEPS}\n"
                f"Range: {entry_price} - {target_price}",
                "INFO"
            )
    
    async def close_position(self, symbol: str):
        """Close position manually"""
        try:
            position = await self.bybit.get_position(symbol)
            if not position or float(position.get("size", 0)) == 0:
                await self.telegram.send_message(f"No open position for {symbol}")
                return
            
            side = position.get("side")
            success = await self.bybit.close_position(symbol, side)
            
            if success:
                # Cleanup
                self.risk.remove_position(symbol)
                self.trailing.disable_trailing(symbol)
                self.active_trades.pop(symbol, None)
                
                await self.telegram.send_alert(
                    "Position Closed",
                    f"{symbol} position closed manually",
                    "SUCCESS"
                )
                
                logger.info(f"Position closed: {symbol}")
            
        except Exception as e:
            logger.error(f"Close position error: {str(e)}")
            await self.telegram.send_error(f"Close error: {str(e)}")
    
    async def update_position(self, update: dict):
        """Update position SL/TP"""
        symbol = update["symbol"]
        
        try:
            # Update stop loss
            if update.get("stop_loss"):
                # Cancel old orders and place new SL
                await self.orders.cancel_all_symbol_orders(symbol)
                logger.info(f"SL updated for {symbol}: {update['stop_loss']}")
            
            # Update targets
            if update.get("targets"):
                logger.info(f"Targets updated for {symbol}: {update['targets']}")
            
            await self.telegram.send_alert(
                "Position Updated",
                f"{symbol} updated successfully",
                "SUCCESS"
            )
            
        except Exception as e:
            logger.error(f"Update error: {str(e)}")
    
    async def monitor_positions(self):
        """Monitor open positions"""
        while self.is_running:
            try:
                await asyncio.sleep(10)  # Check every 10 seconds
                
                for symbol in list(self.active_trades.keys()):
                    # Check pyramid scaling
                    if self.pyramid.is_pyramid_active(symbol):
                        await self.pyramid.check_and_scale(symbol)
                    
                    # Merge partial fills
                    await self.orders.merge_partial_fills(symbol)
                    
                    # Check for re-entry opportunities
                    ticker = await self.bybit.get_ticker(symbol)
                    if ticker:
                        price = float(ticker.get("lastPrice", 0))
                        if await self.reentry.check_reentry_opportunity(symbol, price):
                            await self.reentry.execute_reentry(symbol)
                
            except Exception as e:
                logger.error(f"Position monitor error: {str(e)}")
    
    async def handle_command(self, command: str, args: any) -> str:
        """Handle bot commands"""
        try:
            if command == "status":
                metrics = self.risk.get_risk_metrics()
                return f"""
📊 <b>Bot Status</b>

Daily PnL: ${metrics['daily_pnl']:.2f}
Trades Today: {metrics['daily_trades']}
Open Positions: {metrics['open_positions']}/{metrics['max_open_positions']}
Unrealized PnL: ${metrics['unrealized_pnl']:.2f}
"""
            
            elif command == "balance":
                balance = await self.bybit.get_balance()
                return f"💰 Balance: ${balance:.2f} USDT"
            
            elif command == "positions":
                positions_list = []
                for symbol in self.active_trades.keys():
                    pos = await self.bybit.get_position(symbol)
                    if pos:
                        positions_list.append(f"{symbol}: {pos.get('size')} @ {pos.get('avgPrice')}")
                
                if positions_list:
                    return "📋 <b>Open Positions:</b>\n\n" + "\n".join(positions_list)
                return "No open positions"
            
            elif command == "close":
                await self.close_position(args)
                return f"Closing {args}..."
            
            elif command == "stop":
                await self.stop()
                return "Bot stopped"
            
            return "Unknown command"
            
        except Exception as e:
            return f"Error: {str(e)}"

async def main():
    """Main entry point"""
    bot = TradingBot()
    
    try:
        await bot.start()
        
        # Keep running
        while bot.is_running:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Bot error: {str(e)}")
    finally:
        await bot.stop()

if __name__ == "__main__":
    asyncio.run(main())