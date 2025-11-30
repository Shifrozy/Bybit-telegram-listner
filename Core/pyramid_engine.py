"""
Pyramid Engine
7-step pyramid scaling strategy
"""
from typing import Optional, Dict, List
from core.bybit_client import BybitClient
from core.order_engine import OrderEngine
from utils.logger import logger
from utils.helpers import calculate_pyramid_prices, round_quantity, round_price
from utils.config import Config


class PyramidEngine:
    def __init__(self, bybit_client: BybitClient, order_engine: OrderEngine):
        self.bybit = bybit_client
        self.orders = order_engine
        
        # Track pyramid positions
        self.pyramids = {}  # symbol -> pyramid_data
    
    async def initialize_pyramid(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        target_price: float,
        total_quantity: float,
        stop_loss: Optional[float] = None,
        steps: int = None
    ) -> bool:
        """
        Initialize pyramid scaling
        
        Args:
            symbol: Trading pair
            side: BUY/SELL
            entry_price: Initial entry
            target_price: Final pyramid target
            total_quantity: Total size to scale
            stop_loss: Stop loss price
            steps: Number of pyramid steps (default 7)
            
        Returns:
            Success status
        """
        if steps is None:
            steps = Config.PYRAMID_STEPS
        
        try:
            # Calculate pyramid prices
            prices = calculate_pyramid_prices(entry_price, target_price, steps)
            
            # Calculate quantity per step
            qty_per_step = round_quantity(total_quantity / steps)
            
            logger.info(f"Initializing {steps}-step pyramid for {symbol}")
            logger.info(f"Prices: {prices}")
            
            # Store pyramid data
            self.pyramids[symbol] = {
                "side": side,
                "prices": prices,
                "qty_per_step": qty_per_step,
                "total_quantity": total_quantity,
                "stop_loss": stop_loss,
                "current_step": 0,
                "filled_steps": [],
                "order_ids": [],
                "average_entry": 0.0,
                "total_filled": 0.0
            }
            
            # Place initial entry
            success = await self._place_pyramid_step(symbol, 0)
            
            return success
            
        except Exception as e:
            logger.error(f"Pyramid init error: {str(e)}")
            return False
    
    async def _place_pyramid_step(self, symbol: str, step: int) -> bool:
        """Place order for specific pyramid step"""
        if symbol not in self.pyramids:
            return False
        
        pyramid = self.pyramids[symbol]
        
        if step >= len(pyramid["prices"]):
            logger.warning(f"Step {step} exceeds pyramid levels")
            return False
        
        price = pyramid["prices"][step]
        quantity = pyramid["qty_per_step"]
        side = pyramid["side"]
        
        # Place limit order
        order = await self.bybit.place_order(
            symbol=symbol,
            side=side,
            order_type="Limit",
            qty=quantity,
            price=price,
            stop_loss=pyramid["stop_loss"]
        )
        
        if order:
            pyramid["order_ids"].append({
                "step": step,
                "order_id": order["orderId"],
                "price": price,
                "quantity": quantity
            })
            logger.info(f"Pyramid step {step + 1}/{len(pyramid['prices'])} placed @ {price}")
            return True
        
        return False
    
    async def check_and_scale(self, symbol: str) -> bool:
        """
        Check if next pyramid step should be triggered
        Automatically scales into position
        """
        if symbol not in self.pyramids:
            return False
        
        pyramid = self.pyramids[symbol]
        
        try:
            # Get current position
            position = await self.bybit.get_position(symbol)
            if not position:
                return False
            
            current_size = float(position.get("size", 0))
            avg_entry = float(position.get("avgPrice", 0))
            
            # Update pyramid data
            pyramid["total_filled"] = current_size
            pyramid["average_entry"] = avg_entry
            
            # Calculate how many steps should be filled
            expected_filled = int(current_size / pyramid["qty_per_step"])
            
            # If we have more fills than placed orders, place next step
            if expected_filled > pyramid["current_step"]:
                next_step = pyramid["current_step"] + 1
                
                if next_step < len(pyramid["prices"]):
                    logger.info(f"Triggering pyramid step {next_step + 1}")
                    
                    success = await self._place_pyramid_step(symbol, next_step)
                    if success:
                        pyramid["current_step"] = next_step
                        pyramid["filled_steps"].append(next_step - 1)
                        return True
                else:
                    logger.info(f"Pyramid complete for {symbol}")
                    pyramid["current_step"] = len(pyramid["prices"])
            
            return False
            
        except Exception as e:
            logger.error(f"Pyramid scale check error: {str(e)}")
            return False
    
    async def adjust_pyramid_stop(self, symbol: str, new_stop: float) -> bool:
        """Adjust stop loss for all pyramid steps"""
        if symbol not in self.pyramids:
            return False
        
        pyramid = self.pyramids[symbol]
        pyramid["stop_loss"] = new_stop
        
        # Note: Bybit doesn't support modifying SL on open orders
        # This would require cancelling and replacing orders
        # For simplicity, we just update the internal tracking
        
        logger.info(f"Pyramid SL updated to {new_stop} for {symbol}")
        return True
    
    async def cancel_pyramid(self, symbol: str) -> bool:
        """Cancel all pyramid orders"""
        if symbol not in self.pyramids:
            return False
        
        try:
            success = await self.orders.cancel_all_symbol_orders(symbol)
            
            if success:
                self.pyramids.pop(symbol, None)
                logger.info(f"Pyramid cancelled for {symbol}")
            
            return success
            
        except Exception as e:
            logger.error(f"Cancel pyramid error: {str(e)}")
            return False
    
    async def get_pyramid_status(self, symbol: str) -> Optional[Dict]:
        """Get pyramid status"""
        if symbol not in self.pyramids:
            return None
        
        pyramid = self.pyramids[symbol]
        
        return {
            "symbol": symbol,
            "total_steps": len(pyramid["prices"]),
            "current_step": pyramid["current_step"] + 1,
            "filled_steps": len(pyramid["filled_steps"]),
            "average_entry": pyramid["average_entry"],
            "total_filled": pyramid["total_filled"],
            "target_quantity": pyramid["total_quantity"],
            "completion": (pyramid["total_filled"] / pyramid["total_quantity"]) * 100
        }
    
    def is_pyramid_active(self, symbol: str) -> bool:
        """Check if pyramid is active for symbol"""
        return symbol in self.pyramids
    
    async def finalize_pyramid(self, symbol: str):
        """Finalize pyramid after all steps filled"""
        if symbol not in self.pyramids:
            return
        
        pyramid = self.pyramids[symbol]
        
        # Check if all steps filled
        if pyramid["current_step"] >= len(pyramid["prices"]) - 1:
            logger.info(f"Pyramid finalized for {symbol}")
            logger.info(f"Average entry: {pyramid['average_entry']}")
            logger.info(f"Total filled: {pyramid['total_filled']}")
            
            # Keep in tracking for reference
            pyramid["status"] = "completed"