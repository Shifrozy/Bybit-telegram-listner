"""
Helper Functions
Utility functions for calculations and formatting
"""
from decimal import Decimal, ROUND_DOWN
from typing import Optional, Union
import hmac
import hashlib
import time

def round_price(price: float, tick_size: float = 0.01) -> float:
    """Round price to valid tick size"""
    return float(Decimal(str(price)).quantize(Decimal(str(tick_size)), rounding=ROUND_DOWN))

def round_quantity(quantity: float, step_size: float = 0.001) -> float:
    """Round quantity to valid step size"""
    return float(Decimal(str(quantity)).quantize(Decimal(str(step_size)), rounding=ROUND_DOWN))

def calculate_position_size(
    balance: float,
    risk_percent: float,
    entry_price: float,
    stop_loss: float,
    leverage: int = 1
) -> float:
    """
    Calculate position size based on risk
    
    Args:
        balance: Account balance
        risk_percent: Risk percentage (1.0 = 1%)
        entry_price: Entry price
        stop_loss: Stop loss price
        leverage: Leverage multiplier
        
    Returns:
        Position size in base currency
    """
    risk_amount = balance * (risk_percent / 100)
    price_difference = abs(entry_price - stop_loss)
    
    if price_difference == 0:
        return 0.0
    
    position_size = (risk_amount * entry_price) / price_difference
    leveraged_size = position_size * leverage
    
    return round_quantity(leveraged_size)

def calculate_pnl(
    entry_price: float,
    current_price: float,
    quantity: float,
    side: str
) -> float:
    """Calculate unrealized PnL"""
    if side.upper() == "BUY":
        pnl = (current_price - entry_price) * quantity
    else:
        pnl = (entry_price - current_price) * quantity
    
    return round(pnl, 2)

def calculate_pnl_percent(
    entry_price: float,
    current_price: float,
    side: str
) -> float:
    """Calculate PnL percentage"""
    if side.upper() == "BUY":
        pnl_pct = ((current_price - entry_price) / entry_price) * 100
    else:
        pnl_pct = ((entry_price - current_price) / entry_price) * 100
    
    return round(pnl_pct, 2)

def generate_signature(secret: str, params: str) -> str:
    """Generate HMAC SHA256 signature for Bybit"""
    return hmac.new(
        secret.encode('utf-8'),
        params.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

def get_timestamp() -> str:
    """Get current timestamp in milliseconds"""
    return str(int(time.time() * 1000))

def parse_float(value: Union[str, float, int, None], default: float = 0.0) -> float:
    """Safely parse float from various types"""
    try:
        return float(value) if value is not None else default
    except (ValueError, TypeError):
        return default

def format_number(value: float, decimals: int = 2) -> str:
    """Format number for display"""
    return f"{value:,.{decimals}f}"

def calculate_pyramid_prices(
    entry_price: float,
    target_price: float,
    steps: int = 7
) -> list:
    """
    Calculate pyramid entry prices
    
    Args:
        entry_price: Initial entry price
        target_price: Final target/stop price
        steps: Number of pyramid steps
        
    Returns:
        List of prices for each step
    """
    if steps <= 1:
        return [entry_price]
    
    price_difference = abs(target_price - entry_price)
    step_size = price_difference / (steps - 1)
    
    prices = []
    for i in range(steps):
        if entry_price < target_price:
            price = entry_price + (step_size * i)
        else:
            price = entry_price - (step_size * i)
        prices.append(round_price(price))
    
    return prices

def calculate_trailing_stop(
    entry_price: float,
    current_price: float,
    side: str,
    trail_percent: float
) -> float:
    """Calculate trailing stop price"""
    trail_amount = current_price * (trail_percent / 100)
    
    if side.upper() == "BUY":
        stop_price = current_price - trail_amount
        # Only trail up, never down
        if stop_price > entry_price:
            return round_price(stop_price)
    else:
        stop_price = current_price + trail_amount
        # Only trail down, never up
        if stop_price < entry_price:
            return round_price(stop_price)
    
    return round_price(entry_price)

def validate_price(price: float) -> bool:
    """Validate if price is valid"""
    return price > 0 and price != float('inf')

def validate_quantity(quantity: float) -> bool:
    """Validate if quantity is valid"""
    return quantity > 0 and quantity != float('inf')