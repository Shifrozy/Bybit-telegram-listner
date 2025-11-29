"""
Order Engine
Dual limit engine with merge/replace logic
"""
from typing import Optional, Dict, List
from core.bybit_client import BybitClient
from core.risk_manager import RiskManager
from utils.logger import logger
from utils.helpers import round_price, round_quantity

class OrderEngine:
    def __init__(self, bybit_client: BybitClient, risk_manager: RiskManager):
        self.bybit = bybit_client
        self.risk = risk_manager
        
        # Track pending orders
        self.pending_orders = {}  # symbol -> [order_ids]
        self.limit_orders = {}    # symbol -> {price: order_id}
    
    async def execute_dual_limit(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        quantity: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> bool:
        """
        Execute dual limit strategy
        Places 2 limit orders: one at entry, one slightly better
        
        Args:
            symbol: Trading pair
            side: BUY/SELL
            entry_price: Primary entry price
            quantity: Total quantity (split 50/50)
            stop_loss: Stop loss price
            take_profit: Take profit price
            
        Returns:
            Success status
        """
        try:
            # Split quantity
            qty_per_order = round_quantity(quantity / 2)
            
            # Calculate second limit (better price)
            price_offset_pct = 0.002  # 0.2% better price
            if side.upper() == "BUY":
                second_price = round_price(entry_price * (1 - price_offset_pct))
            else:
                second_price = round_price(entry_price * (1 + price_offset_pct))
            
            logger.info(f"Dual Limit: {symbol} {side} | P1: {entry_price} P2: {second_price}")
            
            # Place first limit order
            order1 = await self.bybit.place_order(
                symbol=symbol,
                side=side,
                order_type="Limit",
                qty=qty_per_order,
                price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit
            )
            
            if not order1:
                logger.error("Failed to place first limit order")
                return False
            
            # Place second limit order
            order2 = await self.bybit.place_order(
                symbol=symbol,
                side=side,
                order_type="Limit",
                qty=qty_per_order,
                price=second_price,
                stop_loss=stop_loss,
                take_profit=take_profit
            )
            
            if not order2:
                logger.warning("Failed to place second limit order, cancelling first")
                await self.bybit.cancel_order(symbol, order1["orderId"])
                return False
            
            # Track orders
            self.pending_orders[symbol] = [
                order1["orderId"],
                order2["orderId"]
            ]
            
            self.limit_orders[symbol] = {
                entry_price: order1["orderId"],
                second_price: order2["orderId"]
            }
            
            logger.info(f"Dual limit orders placed for {symbol}")
            return True
            
        except Exception as e:
            logger.error(f"Dual limit error: {str(e)}")
            return False
    
    async def execute_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> bool:
        """Execute immediate market order"""
        try:
            order = await self.bybit.place_order(
                symbol=symbol,
                side=side,
                order_type="Market",
                qty=quantity,
                stop_loss=stop_loss,
                take_profit=take_profit
            )
            
            if order:
                logger.info(f"Market order executed: {symbol} {side} {quantity}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Market order error: {str(e)}")
            return False
    
    async def merge_partial_fills(self, symbol: str) -> bool:
        """
        Merge strategy: if one limit fills, cancel the other
        and use that capital for the filled position
        """
        try:
            # Check if symbol has pending orders
            if symbol not in self.pending_orders:
                return False
            
            # Get current position
            position = await self.bybit.get_position(symbol)
            if not position or float(position.get("size", 0)) == 0:
                return False
            
            # Get open orders
            open_orders = await self.bybit.get_open_orders(symbol)
            open_order_ids = [o["orderId"] for o in open_orders]
            
            # Check which orders are still pending
            pending = self.pending_orders[symbol]
            unfilled = [oid for oid in pending if oid in open_order_ids]
            
            # If one filled and one pending, cancel pending
            if len(unfilled) > 0 and len(unfilled) < len(pending):
                logger.info(f"Merge: Cancelling unfilled orders for {symbol}")
                
                for order_id in unfilled:
                    await self.bybit.cancel_order(symbol, order_id)
                
                # Clear tracking
                self.pending_orders.pop(symbol, None)
                self.limit_orders.pop(symbol, None)
                
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Merge error: {str(e)}")
            return False
    
    async def replace_limit_order(
        self,
        symbol: str,
        old_price: float,
        new_price: float,
        quantity: float,
        side: str
    ) -> bool:
        """
        Replace limit order at new price
        Cancel old -> place new
        """
        try:
            # Get order ID at old price
            if symbol not in self.limit_orders:
                return False
            
            order_id = self.limit_orders[symbol].get(old_price)
            if not order_id:
                return False
            
            # Cancel old order
            cancelled = await self.bybit.cancel_order(symbol, order_id)
            if not cancelled:
                logger.warning(f"Failed to cancel order {order_id}")
                return False
            
            # Place new order
            new_order = await self.bybit.place_order(
                symbol=symbol,
                side=side,
                order_type="Limit",
                qty=quantity,
                price=new_price
            )
            
            if new_order:
                # Update tracking
                self.limit_orders[symbol].pop(old_price, None)
                self.limit_orders[symbol][new_price] = new_order["orderId"]
                
                logger.info(f"Order replaced: {old_price} -> {new_price}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Replace order error: {str(e)}")
            return False
    
    async def cancel_all_symbol_orders(self, symbol: str) -> bool:
        """Cancel all orders for symbol"""
        try:
            success = await self.bybit.cancel_all_orders(symbol)
            
            if success:
                # Clear tracking
                self.pending_orders.pop(symbol, None)
                self.limit_orders.pop(symbol, None)
                logger.info(f"All orders cancelled for {symbol}")
            
            return success
            
        except Exception as e:
            logger.error(f"Cancel all orders error: {str(e)}")
            return False
    
    async def get_order_status(self, symbol: str) -> Dict:
        """Get order status summary"""
        open_orders = await self.bybit.get_open_orders(symbol)
        
        return {
            "symbol": symbol,
            "open_orders": len(open_orders),
            "orders": open_orders,
            "pending_tracked": len(self.pending_orders.get(symbol, []))
        }
    
    async def cleanup_filled_orders(self, symbol: str):
        """Remove filled orders from tracking"""
        if symbol not in self.pending_orders:
            return
        
        open_orders = await self.bybit.get_open_orders(symbol)
        open_order_ids = [o["orderId"] for o in open_orders]
        
        # Update pending list
        pending = self.pending_orders[symbol]
        still_pending = [oid for oid in pending if oid in open_order_ids]
        
        if len(still_pending) == 0:
            self.pending_orders.pop(symbol, None)
            self.limit_orders.pop(symbol, None)
        else:
            self.pending_orders[symbol] = still_pending