"""
Signal Parser
Parse trading signals from Telegram messages
"""
import re
from typing import Optional, Dict, List
from utils.logger import logger

class SignalParser:
    """Parse various signal formats from Telegram"""
    
    PATTERNS = {
        "symbol": r"(?:SYMBOL|COIN|PAIR)[:\s]*([A-Z]+(?:USDT|USD|BUSD)?)",
        "side": r"(?:SIDE|DIRECTION|TYPE)[:\s]*(LONG|SHORT|BUY|SELL)",
        "entry": r"(?:ENTRY|BUY|PRICE)[:\s]*([0-9.]+)",
        "entries": r"(?:ENTRY|ENTRIES)[:\s]*([0-9.,\s-]+)",
        "stop_loss": r"(?:SL|STOP.?LOSS|STOP)[:\s]*([0-9.]+)",
        "targets": r"(?:TP|TARGET|TAKE.?PROFIT)[:\s]*([0-9.,\s-]+)",
        "leverage": r"(?:LEVERAGE|LEV)[:\s]*([0-9]+)X?",
    }
    
    @staticmethod
    def parse_signal(text: str) -> Optional[Dict]:
        """
        Parse signal from text
        
        Returns:
            Dict with signal data or None if invalid
        """
        text = text.upper()
        signal = {}
        
        try:
            # Parse Symbol
            symbol_match = re.search(SignalParser.PATTERNS["symbol"], text, re.IGNORECASE)
            if symbol_match:
                symbol = symbol_match.group(1)
                # Ensure USDT suffix
                if not symbol.endswith(("USDT", "USD", "BUSD")):
                    symbol += "USDT"
                signal["symbol"] = symbol
            
            # Parse Side
            side_match = re.search(SignalParser.PATTERNS["side"], text, re.IGNORECASE)
            if side_match:
                side = side_match.group(1).upper()
                signal["side"] = "BUY" if side in ["LONG", "BUY"] else "SELL"
            
            # Parse Entry Price(s)
            entry_match = re.search(SignalParser.PATTERNS["entries"], text, re.IGNORECASE)
            if not entry_match:
                entry_match = re.search(SignalParser.PATTERNS["entry"], text, re.IGNORECASE)
            
            if entry_match:
                entry_str = entry_match.group(1)
                entries = SignalParser._parse_price_list(entry_str)
                signal["entries"] = entries
                signal["entry"] = entries[0] if entries else None
            
            # Parse Stop Loss
            sl_match = re.search(SignalParser.PATTERNS["stop_loss"], text, re.IGNORECASE)
            if sl_match:
                signal["stop_loss"] = float(sl_match.group(1))
            
            # Parse Targets
            tp_match = re.search(SignalParser.PATTERNS["targets"], text, re.IGNORECASE)
            if tp_match:
                tp_str = tp_match.group(1)
                signal["targets"] = SignalParser._parse_price_list(tp_str)
            
            # Parse Leverage
            lev_match = re.search(SignalParser.PATTERNS["leverage"], text, re.IGNORECASE)
            if lev_match:
                signal["leverage"] = int(lev_match.group(1))
            
            # Validate required fields
            if not all(k in signal for k in ["symbol", "side", "entry"]):
                logger.warning("Signal missing required fields")
                return None
            
            logger.info(f"Parsed signal: {signal['symbol']} {signal['side']}")
            return signal
            
        except Exception as e:
            logger.error(f"Signal parse error: {str(e)}")
            return None
    
    @staticmethod
    def _parse_price_list(price_str: str) -> List[float]:
        """Parse comma/dash separated price list"""
        prices = []
        
        # Remove spaces and split by comma or newline
        price_str = re.sub(r'\s+', '', price_str)
        parts = re.split(r'[,\n]', price_str)
        
        for part in parts:
            # Handle range like "100-105"
            if '-' in part and not part.startswith('-'):
                range_parts = part.split('-')
                if len(range_parts) == 2:
                    try:
                        start = float(range_parts[0])
                        end = float(range_parts[1])
                        prices.extend([start, end])
                    except ValueError:
                        pass
            else:
                try:
                    prices.append(float(part))
                except ValueError:
                    pass
        
        return sorted(set(prices), reverse=False)
    
    @staticmethod
    def parse_close_signal(text: str) -> Optional[str]:
        """
        Parse close/exit signal
        
        Returns:
            Symbol to close or None
        """
        text = text.upper()
        
        # Check for close keywords
        close_keywords = ["CLOSE", "EXIT", "CANCEL", "STOP"]
        if not any(keyword in text for keyword in close_keywords):
            return None
        
        # Extract symbol
        symbol_match = re.search(SignalParser.PATTERNS["symbol"], text, re.IGNORECASE)
        if symbol_match:
            symbol = symbol_match.group(1)
            if not symbol.endswith(("USDT", "USD", "BUSD")):
                symbol += "USDT"
            return symbol
        
        return None
    
    @staticmethod
    def parse_update_signal(text: str) -> Optional[Dict]:
        """
        Parse signal update (new SL/TP)
        
        Returns:
            Dict with update data or None
        """
        text = text.upper()
        
        # Check for update keywords
        update_keywords = ["UPDATE", "MODIFY", "CHANGE", "MOVE"]
        if not any(keyword in text for keyword in update_keywords):
            return None
        
        update = {}
        
        # Parse symbol
        symbol_match = re.search(SignalParser.PATTERNS["symbol"], text, re.IGNORECASE)
        if symbol_match:
            symbol = symbol_match.group(1)
            if not symbol.endswith(("USDT", "USD", "BUSD")):
                symbol += "USDT"
            update["symbol"] = symbol
        
        # Parse new stop loss
        sl_match = re.search(SignalParser.PATTERNS["stop_loss"], text, re.IGNORECASE)
        if sl_match:
            update["stop_loss"] = float(sl_match.group(1))
        
        # Parse new targets
        tp_match = re.search(SignalParser.PATTERNS["targets"], text, re.IGNORECASE)
        if tp_match:
            tp_str = tp_match.group(1)
            update["targets"] = SignalParser._parse_price_list(tp_str)
        
        if "symbol" in update and (update.get("stop_loss") or update.get("targets")):
            return update
        
        return None
    
    @staticmethod
    def format_signal_summary(signal: Dict) -> str:
        """Format signal for display"""
        lines = [
            f"📊 SIGNAL DETECTED",
            f"Symbol: {signal.get('symbol')}",
            f"Side: {signal.get('side')}",
            f"Entry: {signal.get('entry')}",
        ]
        
        if signal.get("entries") and len(signal["entries"]) > 1:
            lines.append(f"All Entries: {', '.join(map(str, signal['entries']))}")
        
        if signal.get("stop_loss"):
            lines.append(f"Stop Loss: {signal['stop_loss']}")
        
        if signal.get("targets"):
            lines.append(f"Targets: {', '.join(map(str, signal['targets']))}")
        
        if signal.get("leverage"):
            lines.append(f"Leverage: {signal['leverage']}x")
        
        return "\n".join(lines)