"""
Trailing Stop Engine
Dynamic trailing stop management
"""
import asyncio
from typing import Optional, Dict
from core.bybit_client import BybitClient
from utils.logger import logger
from utils.helpers import calculate_trailing_stop, round_price
from utils.config import Config

class TrailingEngine:
    def __init__(self, bybit_client: BybitClient):
        self.bybit = bybit_client
        
        # Track trailing stops
        self.trailing_positions = {}  # symbol -> trailing_data
        self.is_running = False
    
    def enable_trailing(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        trail_percent: Optional[float] = None
    ):
        """
        Enable trailing stop for position
        
        Args:
            symbol: Trading pair
            side: BUY/SELL
            entry_price: Entry price
            trail_percent: Trailing percentage (default from config)
        """
        if trail_percent is None:
            trail_percent = Config.TRAILING_STOP_PERCENT
        
        self.trailing_positions[symbol] = {
            "side": side.upper(),
            "entry_price": entry_price,
            "trail_percent": trail_percent,
            "highest_price": entry_price if side.upper() == "BUY" else entry_price,
            "lowest_price": entry_price if side.upper() == "SELL" else entry_price,
            "current_stop": entry_price,
            "trailing_active": False,
            "profit_locked": 0.0
        }
        
        logger.info(f"Trailing enabled for {symbol} | {trail_percent}%")
    
    def disable_trailing(self, symbol: str):
        """Disable trailing for symbol"""
        if symbol in self.trailing_positions:
            self.trailing_positions.pop(symbol)
            logger.info(f"Trailing disabled for {symbol}")
    
    async def update_trailing_stop(self, symbol: str, current_price: float) -> Optional[float]:
        """
        Update trailing stop based on current price
        
        Args:
            symbol: Trading pair
            current_price: Current market price
            
        Returns:
            New stop price if updated, None otherwise
        """
        if symbol not in self.trailing_positions:
            return None
        
        trail = self.trailing_positions[symbol]
        side = trail["side"]
        entry = trail["entry_price"]
        trail_pct = trail["trail_percent"]
        
        # Update price extremes
        if side == "BUY":
            if current_price > trail["highest_price"]:
                trail["highest_price"] = current_price
                
                # Calculate new trailing stop
                new_stop = calculate_trailing_stop(
                    entry_price=entry,
                    current_price=current_price,
                    side=side,
                    trail_percent=trail_pct
                )
                
                # Only update if stop moves up
                if new_stop > trail["current_stop"]:
                    old_stop = trail["current_stop"]
                    trail["current_stop"] = new_stop
                    trail["trailing_active"] = True
                    
                    # Calculate locked profit
                    trail["profit_locked"] = ((new_stop - entry) / entry) * 100
                    
                    logger.info(
                        f"Trailing updated {symbol}: {old_stop:.4f} -> {new_stop:.4f} "
                        f"(Locked: {trail['profit_locked']:.2f}%)"
                    )
                    
                    return new_stop
        
        else:  # SELL
            if current_price < trail["lowest_price"]:
                trail["lowest_price"] = current_price
                
                # Calculate new trailing stop
                new_stop = calculate_trailing_stop(
                    entry_price=entry,
                    current_price=current_price,
                    side=side,
                    trail_percent=trail_pct
                )
                
                # Only update if stop moves down
                if new_stop < trail["current_stop"]:
                    old_stop = trail["current_stop"]
                    trail["current_stop"] = new_stop
                    trail["trailing_active"] = True
                    
                    # Calculate locked profit
                    trail["profit_locked"] = ((entry - new_stop) / entry) * 100
                    
                    logger.info(
                        f"Trailing updated {symbol}: {old_stop:.4f} -> {new_stop:.4f} "
                        f"(Locked: {trail['profit_locked']:.2f}%)"
                    )
                    
                    return new_stop
        
        return None
    
    async def check_trailing_trigger(self, symbol: str, current_price: float) -> bool:
        """
        Check if trailing stop has been triggered
        
        Returns:
            True if should close position
        """
        if symbol not in self.trailing_positions:
            return False
        
        trail = self.trailing_positions[symbol]
        
        if not trail["trailing_active"]:
            return False
        
        side = trail["side"]
        stop_price = trail["current_stop"]
        
        # Check if price hit trailing stop
        if side == "BUY" and current_price <= stop_price:
            logger.warning(f"Trailing stop triggered for {symbol} @ {current_price}")
            return True
        
        if side == "SELL" and current_price >= stop_price:
            logger.warning(f"Trailing stop triggered for {symbol} @ {current_price}")
            return True
        
        return False
    
    async def start_monitoring(self, check_interval: int = 5):
        """
        Start monitoring loop for trailing stops
        
        Args:
            check_interval: Check interval in seconds
        """
        self.is_running = True
        logger.info("Trailing monitor started")
        
        while self.is_running:
            try:
                # Check each trailing position
                for symbol in list(self.trailing_positions.keys()):
                    # Get current price
                    ticker = await self.bybit.get_ticker(symbol)
                    if not ticker:
                        continue
                    
                    current_price = float(ticker.get("lastPrice", 0))
                    if current_price <= 0:
                        continue
                    
                    # Update trailing stop
                    await self.update_trailing_stop(symbol, current_price)
                    
                    # Check if triggered
                    triggered = await self.check_trailing_trigger(symbol, current_price)
                    if triggered:
                        # Close position
                        trail = self.trailing_positions[symbol]
                        await self.bybit.close_position(symbol, trail["side"])
                        self.disable_trailing(symbol)
                
                await asyncio.sleep(check_interval)
                
            except Exception as e:
                logger.error(f"Trailing monitor error: {str(e)}")
                await asyncio.sleep(check_interval)
    
    def stop_monitoring(self):
        """Stop monitoring loop"""
        self.is_running = False
        logger.info("Trailing monitor stopped")
    
    def get_trailing_status(self, symbol: str) -> Optional[Dict]:
        """Get trailing stop status"""
        if symbol not in self.trailing_positions:
            return None
        
        trail = self.trailing_positions[symbol]
        
        return {
            "symbol": symbol,
            "side": trail["side"],
            "entry_price": trail["entry_price"],
            "current_stop": trail["current_stop"],
            "trail_percent": trail["trail_percent"],
            "highest_price": trail["highest_price"] if trail["side"] == "BUY" else None,
            "lowest_price": trail["lowest_price"] if trail["side"] == "SELL" else None,
            "trailing_active": trail["trailing_active"],
            "profit_locked": trail["profit_locked"]
        }
    
    def adjust_trail_percent(self, symbol: str, new_percent: float):
        """Adjust trailing percentage"""
        if symbol in self.trailing_positions:
            old_percent = self.trailing_positions[symbol]["trail_percent"]
            self.trailing_positions[symbol]["trail_percent"] = new_percent
            logger.info(f"Trail % adjusted for {symbol}: {old_percent}% -> {new_percent}%")