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

symbol = "IOTXUSDT"
buy_at = 35
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

def get_IOTX_quantity():
    return get_asset_balance("IOTX")

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
            print(f">>> BOUGHT {qty} IOTX at market")
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

        qty = get_IOTX_quantity()
        qty = round(qty, precision)

        if qty >= float(filters['LOT_SIZE']['minQty']):
            order = client.create_order(
                symbol=symbol,
                side=SIDE_SELL,
                type=ORDER_TYPE_MARKET,
                quantity=qty
            )
            print(f">>> SOLD {qty} IOTX at market")
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

    # Fetch klines
    klines = client.get_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_1MINUTE, limit=50)
    df = pd.DataFrame(klines, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_asset_volume', 'num_trades',
        'taker_buy_base_volume', 'taker_buy_quote_volume', 'ignore'
    ])
    df['close'] = df['close'].astype(float)

    # EMA calculations
    df['ema_9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()

    # EMA crossover detection
    prev_ema_9 = df['ema_9'].iloc[-2]
    prev_ema_20 = df['ema_20'].iloc[-2]
    curr_ema_9 = df['ema_9'].iloc[-1]
    curr_ema_20 = df['ema_20'].iloc[-1]

    golden_cross = prev_ema_9 < prev_ema_20 and curr_ema_9 > curr_ema_20
    death_cross = prev_ema_9 > prev_ema_20 and curr_ema_9 < curr_ema_20

    # RSI calculation
    rsi_series = RSIIndicator(close=df['close'], window=14).rsi()
    rsi = rsi_series.iloc[-1]
    prev_rsi = rsi_series.iloc[-2]

    # RSI crossing detection
    rsi_cross_up = prev_rsi < 35 and rsi >= 35
    rsi_cross_down = prev_rsi > 70 and rsi <= 70

    # Current price
    price = get_current_price()

    print(f"Price: {price:.5f} | RSI: {rsi:.2f} | RSI↑30: {rsi_cross_up} | RSI↓70: {rsi_cross_down} | EMA9: {curr_ema_9:.5f} | EMA20: {curr_ema_20:.5f} | Cross↑: {golden_cross} | Cross↓: {death_cross} | Pos: {position or 'NONE'}")

    # Buy condition
    if golden_cross and rsi_cross_up and position != "LONG":
        result = place_market_buy()
        if result:
            position = "LONG"
            save_position(position)

    # Fast RSI rise detection
    rsi_fast_rise = (rsi - rsi_series.iloc[-3]) >= 40 and rsi >= 60

    if rsi_fast_rise and position == "LONG":
        print("⚠️ RSI rising rapidly — taking early profit.")
        success = place_market_sell()
        if success:
            position = None
            save_position("")
            return  # Exit to prevent multiple actions in the same loop

    # Sell condition
    elif death_cross and rsi_cross_down and position == "LONG":
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
