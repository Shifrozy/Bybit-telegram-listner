"""
Signal Parser Tests
Test signal parsing from various formats
"""
import sys
sys.path.append('..')

from core.signal_parser import SignalParser

def test_basic_signal():
    """Test basic signal format"""
    text = """
    SYMBOL: BTCUSDT
    SIDE: LONG
    ENTRY: 50000
    SL: 49000
    TP: 52000, 54000
    LEVERAGE: 10X
    """
    
    signal = SignalParser.parse_signal(text)
    
    assert signal is not None
    assert signal["symbol"] == "BTCUSDT"
    assert signal["side"] == "BUY"
    assert signal["entry"] == 50000.0
    assert signal["stop_loss"] == 49000.0
    assert signal["targets"] == [52000.0, 54000.0]
    assert signal["leverage"] == 10
    
    print("✅ Basic signal test passed")

def test_short_signal():
    """Test short signal"""
    text = """
    COIN: ETH
    DIRECTION: SHORT
    PRICE: 3000
    STOP: 3100
    TARGET: 2800
    """
    
    signal = SignalParser.parse_signal(text)
    
    assert signal is not None
    assert signal["symbol"] == "ETHUSDT"
    assert signal["side"] == "SELL"
    assert signal["entry"] == 3000.0
    assert signal["stop_loss"] == 3100.0
    
    print("✅ Short signal test passed")

def test_multiple_entries():
    """Test multiple entry prices"""
    text = """
    SYMBOL: ADAUSDT
    SIDE: BUY
    ENTRIES: 0.50, 0.48, 0.46
    SL: 0.44
    TP: 0.55, 0.60
    """
    
    signal = SignalParser.parse_signal(text)
    
    assert signal is not None
    assert len(signal["entries"]) == 3
    assert signal["entries"][0] == 0.50
    assert signal["entry"] == 0.50  # First entry
    
    print("✅ Multiple entries test passed")

def test_range_format():
    """Test range format entries"""
    text = """
    SYMBOL: SOLUSDT
    SIDE: LONG
    ENTRY: 100-105
    STOP LOSS: 95
    """
    
    signal = SignalParser.parse_signal(text)
    
    assert signal is not None
    assert 100.0 in signal["entries"]
    assert 105.0 in signal["entries"]
    
    print("✅ Range format test passed")

def test_close_signal():
    """Test close signal parsing"""
    text = "CLOSE BTCUSDT"
    
    symbol = SignalParser.parse_close_signal(text)
    
    assert symbol == "BTCUSDT"
    
    print("✅ Close signal test passed")

def test_update_signal():
    """Test update signal parsing"""
    text = """
    UPDATE ETHUSDT
    NEW SL: 2900
    NEW TP: 3200, 3400
    """
    
    update = SignalParser.parse_update_signal(text)
    
    assert update is not None
    assert update["symbol"] == "ETHUSDT"
    assert update["stop_loss"] == 2900.0
    assert update["targets"] == [3200.0, 3400.0]
    
    print("✅ Update signal test passed")

def test_invalid_signal():
    """Test invalid signal handling"""
    text = "This is not a valid signal"
    
    signal = SignalParser.parse_signal(text)
    
    assert signal is None
    
    print("✅ Invalid signal test passed")

def test_signal_summary():
    """Test signal summary formatting"""
    signal = {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "entry": 50000.0,
        "entries": [50000.0, 49500.0],
        "stop_loss": 48000.0,
        "targets": [52000.0, 54000.0],
        "leverage": 10
    }
    
    summary = SignalParser.format_signal_summary(signal)
    
    assert "BTCUSDT" in summary
    assert "BUY" in summary
    assert "50000" in summary
    
    print("✅ Signal summary test passed")

if __name__ == "__main__":
    print("🧪 Running Signal Parser Tests...\n")
    
    test_basic_signal()
    test_short_signal()
    test_multiple_entries()
    test_range_format()
    test_close_signal()
    test_update_signal()
    test_invalid_signal()
    test_signal_summary()
    
    print("\n✅ All tests passed!")