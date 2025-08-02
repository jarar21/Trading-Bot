import os
import time
import csv
import numpy as np
import pandas as pd
from ta.momentum import RSIIndicator
from dotenv import load_dotenv
from binance.client import Client
from binance.enums import *

# Load .env
load_dotenv()
api_key = os.getenv("BINANCE_API_KEY")
api_secret = os.getenv("BINANCE_API_SECRET")

# Client setup
client = Client(api_key, api_secret)

# Configuration
symbol = "IOTXUSDT"
interval = Client.KLINE_INTERVAL_1MINUTE
paper_mode = True  # Set False to trade real
position = None  # Track holding state

# ===== Utility Functions =====
def get_klines():
    klines = client.get_klines(symbol=symbol, interval=interval, limit=100)
    df = pd.DataFrame(klines, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_asset_volume', 'num_trades',
        'taker_buy_base_volume', 'taker_buy_quote_volume', 'ignore'
    ])
    df['close'] = df['close'].astype(float)
    return df

def get_current_price():
    ticker = client.get_symbol_ticker(symbol=symbol)
    return float(ticker["price"])

def get_usdt_balance():
    return float(client.get_asset_balance(asset="USDT")["free"])

def get_coin_balance(coin):
    return float(client.get_asset_balance(asset=coin)["free"])

def log_trade(action, qty, price):
    with open("trade_log.csv", "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([action, qty, price, time.strftime('%Y-%m-%d %H:%M:%S')])

# ===== Trade Functions =====
def place_market_buy():
    try:
        info = client.get_symbol_info(symbol)
        filters = {f['filterType']: f for f in info['filters']}
        step_size = float(filters['LOT_SIZE']['stepSize'])
        min_qty = float(filters['LOT_SIZE']['minQty'])

        usdt_balance = get_usdt_balance()
        price = get_current_price()

        if usdt_balance < 5:
            print("⏳ USDT balance too low to buy.")
            return None

        spendable = usdt_balance * 0.997
        qty = spendable / price
        precision = int(round(-1 * np.log10(step_size)))
        qty = round(qty, precision)

        if qty >= min_qty:
            if paper_mode:
                print(f"[PAPER] BUY {qty} {symbol} at {price:.5f}")
            else:
                client.create_order(
                    symbol=symbol,
                    side=SIDE_BUY,
                    type=ORDER_TYPE_MARKET,
                    quantity=qty
                )
                print(f">>> BOUGHT {qty} {symbol} at market")
            log_trade("BUY", qty, price)
            return qty
        else:
            print(f"❌ Quantity {qty} below minQty.")
    except Exception as e:
        print(f"BUY ERROR: {e}")

def place_market_sell(qty):
    try:
        price = get_current_price()
        if paper_mode:
            print(f"[PAPER] SELL {qty} {symbol} at {price:.5f}")
        else:
            client.create_order(
                symbol=symbol,
                side=SIDE_SELL,
                type=ORDER_TYPE_MARKET,
                quantity=qty
            )
            print(f">>> SOLD {qty} {symbol} at market")
        log_trade("SELL", qty, price)
    except Exception as e:
        print(f"SELL ERROR: {e}")

# ===== Main Bot Logic =====
def run_bot():
    global position
    print("▶️ Starting RSI + EMA + Support Bot...")

    # Optional manual support zone
    support_level = 0.025
    support_margin = 0.001

    while True:
        try:
            df = get_klines()
            close = df['close']
            price = get_current_price()
            rsi = RSIIndicator(close, window=14).rsi().iloc[-1]
            ema_50 = close.ewm(span=50, adjust=False).mean().iloc[-1]

            print(f"{time.strftime('%H:%M:%S')} | Price: {price:.5f} | RSI: {rsi:.2f} | EMA50: {ema_50:.5f} | Position: {position or 'NONE'}")

            # BUY Conditions
            if (
                rsi < 30 and
                price >= ema_50 and
                abs(price - support_level) <= support_margin and
                position is None
            ):
                qty = place_market_buy()
                if qty:
                    position = qty

            # SELL Condition
            elif rsi > 70 and position:
                place_market_sell(position)
                position = None

        except Exception as e:
            print(f"MAIN LOOP ERROR: {e}")

        time.sleep(1)

# Run the bot
if __name__ == "__main__":
    run_bot()
