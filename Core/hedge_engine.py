"""
Hedge Engine
Hedging strategies for risk protection
"""
from typing import Optional, Dict
from core.bybit_client import BybitClient
from core.order_engine import OrderEngine
from utils.logger import logger
from utils.helpers import round_quantity

class HedgeEngine:
    def __init__(self, bybit_client: BybitClient, order_engine: OrderEngine):
        self.bybit = bybit_client
        self.orders = order_engine
        
        # Track hedged positions
        self.hedges = {}  # symbol -> hedge_data
    
    async def create_full_hedge(
        self,
        symbol: str,
        main_side: str,
        main_quantity: float,
        main_entry: float
    ) -> bool:
        """
        Create full hedge (100% opposite position)
        
        Args:
            symbol: Trading pair
            main_side: Main position side (BUY/SELL)
            main_quantity: Main position quantity
            main_entry: Main position entry price
            
        Returns:
            Success status
        """
        try:
            # Opposite side for hedge
            hedge_side = "SELL" if main_side.upper() == "BUY" else "BUY"
            
            logger.info(f"Creating full hedge for {symbol} | {main_side} position")
            
            # Place hedge order at market
            success = await self.orders.execute_market_order(
                symbol=symbol,
                side=hedge_side,
                quantity=main_quantity
            )
            
            if success:
                self.hedges[symbol] = {
                    "type": "full",
                    "main_side": main_side,
                    "main_quantity": main_quantity,
                    "main_entry": main_entry,
                    "hedge_side": hedge_side,
                    "hedge_quantity": main_quantity,
                    "is_active": True
                }
                
                logger.info(f"Full hedge created for {symbol}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Full hedge error: {str(e)}")
            return False
    
    async def create_partial_hedge(
        self,
        symbol: str,
        main_side: str,
        main_quantity: float,
        hedge_percent: float = 50.0
    ) -> bool:
        """
        Create partial hedge (e.g., 50% opposite position)
        
        Args:
            symbol: Trading pair
            main_side: Main position side
            main_quantity: Main position quantity
            hedge_percent: Hedge percentage (0-100)
            
        Returns:
            Success status
        """
        try:
            if hedge_percent <= 0 or hedge_percent > 100:
                logger.error(f"Invalid hedge percent: {hedge_percent}")
                return False
            
            # Calculate hedge quantity
            hedge_qty = round_quantity(main_quantity * (hedge_percent / 100))
            
            # Opposite side
            hedge_side = "SELL" if main_side.upper() == "BUY" else "BUY"
            
            logger.info(f"Creating {hedge_percent}% hedge for {symbol}")
            
            # Place hedge order
            success = await self.orders.execute_market_order(
                symbol=symbol,
                side=hedge_side,
                quantity=hedge_qty
            )
            
            if success:
                self.hedges[symbol] = {
                    "type": "partial",
                    "main_side": main_side,
                    "main_quantity": main_quantity,
                    "hedge_side": hedge_side,
                    "hedge_quantity": hedge_qty,
                    "hedge_percent": hedge_percent,
                    "is_active": True
                }
                
                logger.info(f"Partial hedge created: {hedge_percent}% for {symbol}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Partial hedge error: {str(e)}")
            return False
    
    async def create_stop_hedge(
        self,
        symbol: str,
        main_side: str,
        trigger_price: float,
        hedge_quantity: float
    ) -> bool:
        """
        Create stop-triggered hedge
        Hedge activates when price hits trigger
        
        Args:
            symbol: Trading pair
            main_side: Main position side
            trigger_price: Price to trigger hedge
            hedge_quantity: Hedge quantity
            
        Returns:
            Success status
        """
        try:
            hedge_side = "SELL" if main_side.upper() == "BUY" else "BUY"
            
            # Place stop order for hedge
            # Note: This uses stop-market order
            order = await self.bybit.place_order(
                symbol=symbol,
                side=hedge_side,
                order_type="Market",
                qty=hedge_quantity,
                price=trigger_price,  # Stop trigger price
                close_on_trigger=False
            )
            
            if order:
                self.hedges[symbol] = {
                    "type": "stop",
                    "main_side": main_side,
                    "hedge_side": hedge_side,
                    "trigger_price": trigger_price,
                    "hedge_quantity": hedge_quantity,
                    "is_active": False,  # Not active until triggered
                    "order_id": order.get("orderId")
                }
                
                logger.info(f"Stop hedge created @ {trigger_price} for {symbol}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Stop hedge error: {str(e)}")
            return False
    
    async def remove_hedge(self, symbol: str) -> bool:
        """
        Remove hedge position
        Close opposite position
        """
        if symbol not in self.hedges:
            logger.warning(f"No hedge found for {symbol}")
            return False
        
        try:
            hedge = self.hedges[symbol]
            
            if not hedge["is_active"]:
                logger.info(f"Hedge not active for {symbol}, removing tracking")
                self.hedges.pop(symbol)
                return True
            
            # Close hedge position
            success = await self.bybit.close_position(
                symbol=symbol,
                side=hedge["hedge_side"]
            )
            
            if success:
                self.hedges.pop(symbol)
                logger.info(f"Hedge removed for {symbol}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Remove hedge error: {str(e)}")
            return False
    
    async def adjust_hedge(
        self,
        symbol: str,
        new_quantity: float
    ) -> bool:
        """
        Adjust hedge position size
        
        Args:
            symbol: Trading pair
            new_quantity: New hedge quantity
            
        Returns:
            Success status
        """
        if symbol not in self.hedges:
            return False
        
        try:
            hedge = self.hedges[symbol]
            current_qty = hedge["hedge_quantity"]
            
            if new_quantity == current_qty:
                return True
            
            # Calculate difference
            qty_diff = abs(new_quantity - current_qty)
            
            if new_quantity > current_qty:
                # Increase hedge
                side = hedge["hedge_side"]
                success = await self.orders.execute_market_order(
                    symbol=symbol,
                    side=side,
                    quantity=qty_diff
                )
            else:
                # Decrease hedge
                opposite_side = "BUY" if hedge["hedge_side"] == "SELL" else "SELL"
                success = await self.orders.execute_market_order(
                    symbol=symbol,
                    side=opposite_side,
                    quantity=qty_diff,
                )
            
            if success:
                hedge["hedge_quantity"] = new_quantity
                logger.info(f"Hedge adjusted: {current_qty} -> {new_quantity} for {symbol}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Adjust hedge error: {str(e)}")
            return False
    
    def get_hedge_status(self, symbol: str) -> Optional[Dict]:
        """Get hedge status"""
        if symbol not in self.hedges:
            return None
        
        hedge = self.hedges[symbol]
        
        return {
            "symbol": symbol,
            "type": hedge["type"],
            "main_side": hedge["main_side"],
            "hedge_side": hedge["hedge_side"],
            "hedge_quantity": hedge["hedge_quantity"],
            "is_active": hedge["is_active"],
            "hedge_percent": hedge.get("hedge_percent"),
            "trigger_price": hedge.get("trigger_price")
        }
    
    def is_hedged(self, symbol: str) -> bool:
        """Check if symbol is hedged"""
        return symbol in self.hedges and self.hedges[symbol]["is_active"]
    
    async def auto_hedge_on_loss(
        self,
        symbol: str,
        main_side: str,
        current_pnl_percent: float,
        loss_threshold: float = -5.0
    ) -> bool:
        """
        Automatically create hedge if loss exceeds threshold
        
        Args:
            symbol: Trading pair
            main_side: Main position side
            current_pnl_percent: Current PnL percentage
            loss_threshold: Loss threshold to trigger hedge (negative)
            
        Returns:
            True if hedge created
        """
        if current_pnl_percent > loss_threshold:
            return False
        
        if self.is_hedged(symbol):
            logger.info(f"Already hedged: {symbol}")
            return False
        
        logger.warning(f"Auto-hedge triggered: {symbol} PnL: {current_pnl_percent:.2f}%")
        
        # Get position
        position = await self.bybit.get_position(symbol)
        if not position:
            return False
        
        quantity = float(position.get("size", 0))
        
        # Create 100% hedge
        return await self.create_full_hedge(
            symbol=symbol,
            main_side=main_side,
            main_quantity=quantity,
            main_entry=float(position.get("avgPrice", 0))
        )