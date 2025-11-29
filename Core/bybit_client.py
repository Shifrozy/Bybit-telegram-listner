"""
Bybit API Client
Async HTTP client for Bybit API interactions
"""
import httpx
import json
from typing import Optional, Dict, Any
from utils.config import Config
from utils.logger import logger
from utils.helpers import generate_signature, get_timestamp

class BybitClient:
    def __init__(self):
        self.base_url = Config.BYBIT_BASE_URL
        self.api_key = Config.BYBIT_API_KEY
        self.api_secret = Config.BYBIT_API_SECRET
        self.client = httpx.AsyncClient(timeout=30.0)
        
    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()
    
    def _generate_signature(self, timestamp: str, params: str) -> str:
        """Generate request signature"""
        payload = timestamp + self.api_key + "5000" + params
        return generate_signature(self.api_secret, payload)
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Make authenticated request to Bybit
        
        Args:
            method: HTTP method (GET, POST)
            endpoint: API endpoint
            params: Request parameters
            
        Returns:
            Response JSON
        """
        timestamp = get_timestamp()
        
        if params is None:
            params = {}
        
        # Prepare request
        url = f"{self.base_url}{endpoint}"
        param_str = json.dumps(params) if method == "POST" else "&".join(
            f"{k}={v}" for k, v in sorted(params.items())
        )
        
        signature = self._generate_signature(timestamp, param_str)
        headers = Config.get_bybit_headers(timestamp, signature)
        
        try:
            if method == "POST":
                response = await self.client.post(url, json=params, headers=headers)
            else:
                response = await self.client.get(url, params=params, headers=headers)
            
            response.raise_for_status()
            data = response.json()
            
            if data.get("retCode") != 0:
                logger.error(f"Bybit API Error: {data.get('retMsg')}")
                return {"success": False, "error": data.get("retMsg")}
            
            return {"success": True, "data": data.get("result", {})}
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP Error: {str(e)}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"Request Error: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def get_balance(self, coin: str = "USDT") -> Optional[float]:
        """Get wallet balance"""
        response = await self._request(
            "GET",
            "/v5/account/wallet-balance",
            {"accountType": "UNIFIED", "coin": coin}
        )
        
        if response["success"]:
            try:
                coins = response["data"]["list"][0]["coin"]
                for c in coins:
                    if c["coin"] == coin:
                        return float(c["walletBalance"])
            except (KeyError, IndexError):
                pass
        
        return None
    
    async def get_position(self, symbol: str) -> Optional[Dict]:
        """Get current position for symbol"""
        response = await self._request(
            "GET",
            "/v5/position/list",
            {"category": "linear", "symbol": symbol}
        )
        
        if response["success"]:
            try:
                positions = response["data"]["list"]
                if positions:
                    return positions[0]
            except (KeyError, IndexError):
                pass
        
        return None
    
    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        """Set leverage for symbol"""
        response = await self._request(
            "POST",
            "/v5/position/set-leverage",
            {
                "category": "linear",
                "symbol": symbol,
                "buyLeverage": str(leverage),
                "sellLeverage": str(leverage)
            }
        )
        
        return response["success"]
    
    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        qty: float,
        price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        reduce_only: bool = False,
        close_on_trigger: bool = False
    ) -> Optional[Dict]:
        """
        Place order on Bybit
        
        Args:
            symbol: Trading pair
            side: Buy/Sell
            order_type: Market/Limit
            qty: Quantity
            price: Limit price (for limit orders)
            stop_loss: Stop loss price
            take_profit: Take profit price
            reduce_only: Reduce only flag
            close_on_trigger: Close on trigger flag
            
        Returns:
            Order response
        """
        params = {
            "category": "linear",
            "symbol": symbol,
            "side": side.capitalize(),
            "orderType": order_type.capitalize(),
            "qty": str(qty),
            "reduceOnly": reduce_only,
            "closeOnTrigger": close_on_trigger
        }
        
        if price:
            params["price"] = str(price)
        
        if stop_loss:
            params["stopLoss"] = str(stop_loss)
        
        if take_profit:
            params["takeProfit"] = str(take_profit)
        
        response = await self._request("POST", "/v5/order/create", params)
        
        if response["success"]:
            logger.info(f"Order placed: {side} {qty} {symbol} @ {price or 'MARKET'}")
            return response["data"]
        
        return None
    
    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """Cancel order by ID"""
        response = await self._request(
            "POST",
            "/v5/order/cancel",
            {
                "category": "linear",
                "symbol": symbol,
                "orderId": order_id
            }
        )
        
        if response["success"]:
            logger.info(f"Order cancelled: {order_id}")
            return True
        
        return False
    
    async def cancel_all_orders(self, symbol: str) -> bool:
        """Cancel all orders for symbol"""
        response = await self._request(
            "POST",
            "/v5/order/cancel-all",
            {
                "category": "linear",
                "symbol": symbol
            }
        )
        
        return response["success"]
    
    async def get_open_orders(self, symbol: str) -> list:
        """Get all open orders"""
        response = await self._request(
            "GET",
            "/v5/order/realtime",
            {
                "category": "linear",
                "symbol": symbol
            }
        )
        
        if response["success"]:
            return response["data"].get("list", [])
        
        return []
    
    async def get_ticker(self, symbol: str) -> Optional[Dict]:
        """Get ticker price"""
        response = await self._request(
            "GET",
            "/v5/market/tickers",
            {
                "category": "linear",
                "symbol": symbol
            }
        )
        
        if response["success"]:
            try:
                return response["data"]["list"][0]
            except (KeyError, IndexError):
                pass
        
        return None
    
    async def close_position(self, symbol: str, side: str) -> bool:
        """Close position at market price"""
        position = await self.get_position(symbol)
        
        if not position:
            return False
        
        qty = float(position.get("size", 0))
        if qty == 0:
            return True
        
        # Opposite side to close
        close_side = "Sell" if side.upper() == "BUY" else "Buy"
        
        response = await self.place_order(
            symbol=symbol,
            side=close_side,
            order_type="Market",
            qty=qty,
            reduce_only=True
        )
        
        return response is not None