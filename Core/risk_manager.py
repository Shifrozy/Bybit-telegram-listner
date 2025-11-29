"""
Risk Manager
Manages risk limits, position sizing, and trading rules
"""
from typing import Optional, Dict
from datetime import datetime, timedelta
from utils.config import Config
from utils.logger import logger
from utils.helpers import calculate_position_size

class RiskManager:
    def __init__(self):
        self.max_daily_loss = Config.MAX_DAILY_LOSS
        self.max_open_positions = Config.MAX_OPEN_POSITIONS
        self.max_position_size = Config.MAX_POSITION_SIZE
        
        # Track daily stats
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.last_reset = datetime.now().date()
        
        # Active positions
        self.active_positions = {}
    
    def reset_daily_stats(self):
        """Reset daily statistics"""
        today = datetime.now().date()
        if today > self.last_reset:
            logger.info("Resetting daily statistics")
            self.daily_pnl = 0.0
            self.daily_trades = 0
            self.last_reset = today
    
    def update_daily_pnl(self, pnl: float):
        """Update daily PnL"""
        self.reset_daily_stats()
        self.daily_pnl += pnl
        self.daily_trades += 1
        logger.info(f"Daily PnL: ${self.daily_pnl:.2f} | Trades: {self.daily_trades}")
    
    def can_open_position(self) -> tuple[bool, str]:
        """
        Check if new position can be opened
        
        Returns:
            (can_open, reason)
        """
        self.reset_daily_stats()
        
        # Check daily loss limit
        if self.daily_pnl <= -self.max_daily_loss:
            return False, f"Daily loss limit reached: ${self.daily_pnl:.2f}"
        
        # Check max open positions
        if len(self.active_positions) >= self.max_open_positions:
            return False, f"Max open positions reached: {len(self.active_positions)}"
        
        return True, "OK"
    
    def calculate_position_size(
        self,
        balance: float,
        entry_price: float,
        stop_loss: float,
        risk_percent: Optional[float] = None,
        leverage: Optional[int] = None
    ) -> float:
        """
        Calculate safe position size
        
        Args:
            balance: Account balance
            entry_price: Entry price
            stop_loss: Stop loss price
            risk_percent: Risk percentage (default from config)
            leverage: Leverage (default from config)
            
        Returns:
            Position size in base currency
        """
        if risk_percent is None:
            risk_percent = Config.DEFAULT_RISK_PERCENT
        
        if leverage is None:
            leverage = Config.DEFAULT_LEVERAGE
        
        # Calculate base position size
        position_size = calculate_position_size(
            balance=balance,
            risk_percent=risk_percent,
            entry_price=entry_price,
            stop_loss=stop_loss,
            leverage=leverage
        )
        
        # Cap at max position size
        if position_size > self.max_position_size:
            logger.warning(f"Position size capped: {position_size} -> {self.max_position_size}")
            position_size = self.max_position_size
        
        return position_size
    
    def add_position(self, symbol: str, position_data: Dict):
        """Add active position"""
        self.active_positions[symbol] = {
            "entry_price": position_data.get("entry_price"),
            "quantity": position_data.get("quantity"),
            "side": position_data.get("side"),
            "stop_loss": position_data.get("stop_loss"),
            "take_profit": position_data.get("take_profit"),
            "opened_at": datetime.now(),
            "unrealized_pnl": 0.0
        }
        logger.info(f"Position added: {symbol} | Total: {len(self.active_positions)}")
    
    def remove_position(self, symbol: str) -> Optional[Dict]:
        """Remove active position"""
        position = self.active_positions.pop(symbol, None)
        if position:
            logger.info(f"Position removed: {symbol} | Total: {len(self.active_positions)}")
        return position
    
    def update_position_pnl(self, symbol: str, unrealized_pnl: float):
        """Update position unrealized PnL"""
        if symbol in self.active_positions:
            self.active_positions[symbol]["unrealized_pnl"] = unrealized_pnl
    
    def get_position(self, symbol: str) -> Optional[Dict]:
        """Get position data"""
        return self.active_positions.get(symbol)
    
    def get_total_unrealized_pnl(self) -> float:
        """Calculate total unrealized PnL across all positions"""
        return sum(
            pos.get("unrealized_pnl", 0.0)
            for pos in self.active_positions.values()
        )
    
    def get_risk_metrics(self) -> Dict:
        """Get current risk metrics"""
        return {
            "daily_pnl": self.daily_pnl,
            "daily_trades": self.daily_trades,
            "open_positions": len(self.active_positions),
            "unrealized_pnl": self.get_total_unrealized_pnl(),
            "max_daily_loss": self.max_daily_loss,
            "max_open_positions": self.max_open_positions,
            "remaining_loss_buffer": self.max_daily_loss + self.daily_pnl
        }
    
    def validate_order(
        self,
        symbol: str,
        quantity: float,
        price: float,
        stop_loss: Optional[float] = None
    ) -> tuple[bool, str]:
        """
        Validate order parameters
        
        Returns:
            (is_valid, reason)
        """
        # Check if position already exists
        if symbol in self.active_positions:
            return False, f"Position already exists for {symbol}"
        
        # Check quantity
        if quantity <= 0 or quantity > self.max_position_size:
            return False, f"Invalid quantity: {quantity}"
        
        # Check price
        if price <= 0:
            return False, f"Invalid price: {price}"
        
        # Check stop loss distance
        if stop_loss:
            sl_distance_pct = abs(price - stop_loss) / price * 100
            if sl_distance_pct < 0.5:
                return False, f"Stop loss too close: {sl_distance_pct:.2f}%"
            if sl_distance_pct > 20:
                return False, f"Stop loss too far: {sl_distance_pct:.2f}%"
        
        return True, "OK"
    
    def should_reduce_risk(self) -> bool:
        """Check if risk should be reduced"""
        self.reset_daily_stats()
        
        # Reduce risk after 50% of max daily loss
        if self.daily_pnl <= -(self.max_daily_loss * 0.5):
            return True
        
        return False
    
    def get_adjusted_risk_percent(self) -> float:
        """Get risk percentage adjusted for current performance"""
        if self.should_reduce_risk():
            # Reduce risk by 50%
            return Config.DEFAULT_RISK_PERCENT * 0.5
        
        return Config.DEFAULT_RISK_PERCENT