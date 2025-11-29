"""
Re-entry Engine
Smart position re-entry after stops or exits
"""
from typing import Optional, Dict
from datetime import datetime, timedelta
from core.bybit_client import BybitClient
from core.order_engine import OrderEngine
from utils.logger import logger
from utils.helpers import round_price

class ReentryEngine:
    def __init__(self, bybit_client: BybitClient, order_engine: OrderEngine):
        self.bybit = bybit_client
        self.orders = order_engine
        
        # Track closed positions for re-entry
        self.reentry_candidates = {}  # symbol -> reentry_data
        
        # Re-entry settings
        self.max_reentry_attempts = 3
        self.reentry_cooldown_minutes = 5
        self.reentry_price_improvement = 0.005  # 0.5% better price
    
    def register_exit(
        self,
        symbol: str,
        side: str,
        exit_price: float,
        exit_reason: str,
        quantity: float
    ):
        """
        Register position exit for potential re-entry
        
        Args:
            symbol: Trading pair
            side: Position side (BUY/SELL)
            exit_price: Exit price
            exit_reason: Reason for exit (SL/TP/Manual)
            quantity: Position quantity
        """
        # Only track stop loss exits
        if "STOP" not in exit_reason.upper() and "SL" not in exit_reason.upper():
            logger.info(f"Exit reason '{exit_reason}' not eligible for re-entry")
            return
        
        self.reentry_candidates[symbol] = {
            "side": side,
            "exit_price": exit_price,
            "exit_reason": exit_reason,
            "quantity": quantity,
            "exit_time": datetime.now(),
            "reentry_attempts": 0,
            "last_attempt": None,
            "target_reentry_price": self._calculate_reentry_price(exit_price, side),
            "is_active": True
        }
        
        logger.info(f"Re-entry candidate registered: {symbol} @ {exit_price}")
    
    def _calculate_reentry_price(self, exit_price: float, side: str) -> float:
        """Calculate better re-entry price"""
        if side.upper() == "BUY":
            # For long, re-enter lower
            reentry = exit_price * (1 - self.reentry_price_improvement)
        else:
            # For short, re-enter higher
            reentry = exit_price * (1 + self.reentry_price_improvement)
        
        return round_price(reentry)
    
    async def check_reentry_opportunity(self, symbol: str, current_price: float) -> bool:
        """
        Check if re-entry conditions are met
        
        Args:
            symbol: Trading pair
            current_price: Current market price
            
        Returns:
            True if should attempt re-entry
        """
        if symbol not in self.reentry_candidates:
            return False
        
        candidate = self.reentry_candidates[symbol]
        
        if not candidate["is_active"]:
            return False
        
        # Check max attempts
        if candidate["reentry_attempts"] >= self.max_reentry_attempts:
            logger.info(f"Max re-entry attempts reached for {symbol}")
            candidate["is_active"] = False
            return False
        
        # Check cooldown
        if candidate["last_attempt"]:
            time_since_attempt = datetime.now() - candidate["last_attempt"]
            if time_since_attempt < timedelta(minutes=self.reentry_cooldown_minutes):
                return False
        
        # Check if price is favorable
        side = candidate["side"]
        target_price = candidate["target_reentry_price"]
        
        if side.upper() == "BUY":
            # For long, wait for price to drop below target
            if current_price <= target_price:
                logger.info(f"Re-entry opportunity: {symbol} @ {current_price} (target: {target_price})")
                return True
        else:
            # For short, wait for price to rise above target
            if current_price >= target_price:
                logger.info(f"Re-entry opportunity: {symbol} @ {current_price} (target: {target_price})")
                return True
        
        return False
    
    async def execute_reentry(
        self,
        symbol: str,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> bool:
        """
        Execute re-entry trade
        
        Args:
            symbol: Trading pair
            stop_loss: New stop loss
            take_profit: New take profit
            
        Returns:
            Success status
        """
        if symbol not in self.reentry_candidates:
            return False
        
        candidate = self.reentry_candidates[symbol]
        
        try:
            # Get current price
            ticker = await self.bybit.get_ticker(symbol)
            if not ticker:
                return False
            
            current_price = float(ticker.get("lastPrice", 0))
            
            # Check if still favorable
            is_favorable = await self.check_reentry_opportunity(symbol, current_price)
            if not is_favorable:
                logger.info(f"Price no longer favorable for re-entry: {symbol}")
                return False
            
            # Update attempt tracking
            candidate["reentry_attempts"] += 1
            candidate["last_attempt"] = datetime.now()
            
            # Calculate adjusted quantity (reduce by 20% for safety)
            reentry_qty = candidate["quantity"] * 0.8
            
            logger.info(f"Executing re-entry {candidate['reentry_attempts']}/{self.max_reentry_attempts}: {symbol}")
            
            # Place limit order at target price
            success = await self.orders.execute_dual_limit(
                symbol=symbol,
                side=candidate["side"],
                entry_price=candidate["target_reentry_price"],
                quantity=reentry_qty,
                stop_loss=stop_loss,
                take_profit=take_profit
            )
            
            if success:
                logger.info(f"Re-entry successful: {symbol}")
                # Keep candidate active for potential additional re-entries
                return True
            else:
                logger.warning(f"Re-entry failed: {symbol}")
                return False
            
        except Exception as e:
            logger.error(f"Re-entry execution error: {str(e)}")
            return False
    
    async def execute_aggressive_reentry(self, symbol: str) -> bool:
        """
        Execute immediate market re-entry
        Use when price reverses quickly
        """
        if symbol not in self.reentry_candidates:
            return False
        
        candidate = self.reentry_candidates[symbol]
        
        try:
            # Update attempt
            candidate["reentry_attempts"] += 1
            candidate["last_attempt"] = datetime.now()
            
            # Reduced quantity
            reentry_qty = candidate["quantity"] * 0.8
            
            logger.info(f"Aggressive re-entry: {symbol} @ MARKET")
            
            # Market order
            success = await self.orders.execute_market_order(
                symbol=symbol,
                side=candidate["side"],
                quantity=reentry_qty
            )
            
            if success:
                logger.info(f"Aggressive re-entry successful: {symbol}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Aggressive re-entry error: {str(e)}")
            return False
    
    def cancel_reentry(self, symbol: str):
        """Cancel re-entry tracking for symbol"""
        if symbol in self.reentry_candidates:
            self.reentry_candidates[symbol]["is_active"] = False
            logger.info(f"Re-entry cancelled for {symbol}")
    
    def clear_old_candidates(self, max_age_hours: int = 24):
        """Remove old re-entry candidates"""
        current_time = datetime.now()
        to_remove = []
        
        for symbol, candidate in self.reentry_candidates.items():
            age = current_time - candidate["exit_time"]
            if age > timedelta(hours=max_age_hours):
                to_remove.append(symbol)
        
        for symbol in to_remove:
            self.reentry_candidates.pop(symbol)
            logger.info(f"Old re-entry candidate removed: {symbol}")
    
    def get_reentry_status(self, symbol: str) -> Optional[Dict]:
        """Get re-entry status for symbol"""
        if symbol not in self.reentry_candidates:
            return None
        
        candidate = self.reentry_candidates[symbol]
        
        return {
            "symbol": symbol,
            "side": candidate["side"],
            "exit_price": candidate["exit_price"],
            "target_reentry_price": candidate["target_reentry_price"],
            "reentry_attempts": candidate["reentry_attempts"],
            "max_attempts": self.max_reentry_attempts,
            "is_active": candidate["is_active"],
            "exit_time": candidate["exit_time"].strftime("%Y-%m-%d %H:%M:%S"),
            "last_attempt": candidate["last_attempt"].strftime("%Y-%m-%d %H:%M:%S") if candidate["last_attempt"] else None
        }
    
    def adjust_reentry_settings(
        self,
        max_attempts: Optional[int] = None,
        cooldown_minutes: Optional[int] = None,
        price_improvement: Optional[float] = None
    ):
        """Adjust re-entry settings"""
        if max_attempts:
            self.max_reentry_attempts = max_attempts
            logger.info(f"Max re-entry attempts set to {max_attempts}")
        
        if cooldown_minutes:
            self.reentry_cooldown_minutes = cooldown_minutes
            logger.info(f"Re-entry cooldown set to {cooldown_minutes} minutes")
        
        if price_improvement:
            self.reentry_price_improvement = price_improvement
            logger.info(f"Re-entry price improvement set to {price_improvement * 100}%")