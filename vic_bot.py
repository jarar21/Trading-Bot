import os
import time
import pandas as pd
import numpy as np
from ta.momentum import RSIIndicator
from binance.client import Client
from binance.enums import *
from dotenv import load_dotenv

# Load API keys
load_dotenv()
api_key = os.getenv("BINANCE_API_KEY")
api_secret = os.getenv("BINANCE_API_SECRET")

client = Client(api_key, api_secret)

symbol = "VICUSDT"
buy_at = 31
sell_at = 55
position_file = "position.txt"

# --------------------------
# Persistent Position Logic
# --------------------------
def load_position():
    if os.path.exists(position_file):
        with open(position_file, "r") as f:
            return f.read().strip()
    return None

def save_position(pos):
    with open(position_file, "w") as f:
        f.write(pos if pos else "")

position = load_position()

# --------------------------
# Binance Helpers
# --------------------------
def get_current_price():
    trades = client.get_recent_trades(symbol=symbol, limit=1)
    return float(trades[0]['price'])

def get_asset_balance(asset):
    balance = client.get_asset_balance(asset=asset)
    return float(balance['free']) if balance else 0.0

def get_usdt_balance():
    return get_asset_balance("USDT")

def get_VIC_quantity():
    return get_asset_balance("VIC")

def place_market_buy():
    try:
        info = client.get_symbol_info(symbol)
        filters = {f['filterType']: f for f in info['filters']}
        step_size = float(filters['LOT_SIZE']['stepSize'])
        min_qty = float(filters['LOT_SIZE']['minQty'])

        usdt_balance = get_usdt_balance()
        price = get_current_price()

        if usdt_balance < 5:
            print("⏳ Waiting: USDT balance too low to buy.")
            return None

        spendable = usdt_balance * 0.997
        qty = spendable / price
        precision = int(round(-1 * np.log10(step_size)))
        qty = round(qty, precision)

        if qty >= min_qty:
            order = client.create_order(
                symbol=symbol,
                side=SIDE_BUY,
                type=ORDER_TYPE_MARKET,
                quantity=qty
            )
            print(f">>> BOUGHT {qty} VIC at market")
            return qty
        else:
            print(f"Calculated quantity {qty} below minQty.")
    except Exception as e:
        if "insufficient balance" in str(e).lower():
            print("⏳ Waiting: Another bot may be using the balance.")
        else:
            print(f"BUY ERROR: {e}")

def place_market_sell():
    try:
        info = client.get_symbol_info(symbol)
        filters = {f['filterType']: f for f in info['filters']}
        step_size = float(filters['LOT_SIZE']['stepSize'])
        precision = int(round(-1 * np.log10(step_size)))

        qty = get_VIC_quantity()
        qty = round(qty, precision)

        if qty >= float(filters['LOT_SIZE']['minQty']):
            order = client.create_order(
                symbol=symbol,
                side=SIDE_SELL,
                type=ORDER_TYPE_MARKET,
                quantity=qty
            )
            print(f">>> SOLD {qty} VIC at market")
            return True
        else:
            print(f"Calculated quantity {qty} below minQty.")
    except Exception as e:
        print(f"SELL ERROR: {e}")

# --------------------------
# RSI + Trading Logic
# --------------------------
def fetch_rsi_and_trade():
    global position

    klines = client.get_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_1MINUTE, limit=500)
    df = pd.DataFrame(klines, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_asset_volume', 'num_trades',
        'taker_buy_base_volume', 'taker_buy_quote_volume', 'ignore'
    ])
    df['close'] = df['close'].astype(float)

    rsi = RSIIndicator(close=df['close'], window=14).rsi().iloc[-1]
    price = get_current_price()

    print(f"Price: {price:.5f} | RSI: {rsi:.2f} | Position: {position or 'NONE'}")

    if rsi <= buy_at and position != "LONG":
        result = place_market_buy()
        if result:
            position = "LONG"
            save_position(position)

    elif rsi >= sell_at and position == "LONG":
        success = place_market_sell()
        if success:
            position = None
            save_position("")

# --------------------------
# Main Loop
# --------------------------
while True:
    try:
        fetch_rsi_and_trade()
    except Exception as e:
        print(f"Error: {e}")
    time.sleep(1)
