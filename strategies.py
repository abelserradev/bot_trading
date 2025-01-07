import websocket
import json
import numpy as np
import time
import certifi
from datetime import datetime

# Variables globales
app_id = 'tu_app'
token = 'tu_token'
symbol = 'R_100'
amount = 10
ticks_data = []  # Almacena los ticks recibidos
candles = []  # Lista para almacenar las velas generadas
contract_open = False  # Controla si hay un contrato abierto

rsi_period = 14
macd_short = 12
macd_long = 26
macd_signal = 9
ema_period = 50
sma_period = 100
adx_period = 14
atr_period = 14
bollinger_period = 20
bollinger_std_dev = 2
stochastic_period = 14

def on_open(ws):
    print("Conexión abierta.")
    authorize_message = {
        "authorize": token
    }
    ws.send(json.dumps(authorize_message))

def on_message(ws, message):
    global contract_open, ticks_data , amount
    data = json.loads(message)

    if 'error' in data.keys():
        print('Error:', data['error']['message'])

    elif data.get("msg_type") == "authorize":
        subscribe_to_candles(ws)

    elif data.get("msg_type") == "candles":
        process_candles(ws, data['candles'])

    elif data.get("msg_type") == "tick":
        tick = data['tick']
        ticks_data.append(tick)
        process_ticks(ws)

    elif data.get("msg_type") == "buy":
        contract_id = data['buy']['contract_id']
        contract_open = True  # Marcar contrato como abierto
        print(f"Operación ejecutada. ID del contrato: {contract_id}")
        subscribe_to_contract(ws, contract_id)

    elif data.get("msg_type") == "proposal_open_contract":
        if data['proposal_open_contract']['is_sold']:
            profit = data['proposal_open_contract']['profit']
            if profit > 0:
                print(f"El contrato ha sido vendido. Ganancia:{data['proposal_open_contract']['profit']}")
                amount = 10
            elif profit < 0:
                print("El contrato perdió.")
                amount = amount * 2
            else:
                print("El contrato terminó en empate.")
            print("El contrato ha finalizado. Buscando una nueva señal...")
            contract_open = False  # Contrato finalizado, se puede abrir otro
            process_ticks(ws)

def subscribe_to_candles(ws):
    candles_message = {
        "ticks_history": symbol,
        "end": "latest",
        "style": "candles",
        "count": 90,
        "granularity": 300  # 1 vela cada 5 minutos
    }
    ws.send(json.dumps(candles_message))

def process_candles(ws, received_candles):
    global candles
    for candle in received_candles:
        timestamp = datetime.utcfromtimestamp(candle['epoch'])
        new_candle = {
            'timestamp': timestamp,
            'open': candle['open'],
            'high': candle['high'],
            'low': candle['low'],
            'close': candle['close']
        }
        candles.append(new_candle)
    # Ahora puedes comenzar la suscripción a los ticks en tiempo real
    subscribe_to_ticks(ws)

def subscribe_to_ticks(ws):
    ticks_message = {
        "ticks": symbol,
        "subscribe": 1
    }
    ws.send(json.dumps(ticks_message))
    print("Suscripción a ticks enviada.")

def process_ticks(ws):
    global candles

    # Crear velas manualmente a partir de los ticks recibidos
    if len(ticks_data) > 0:
        tick_time = datetime.utcfromtimestamp(ticks_data[-1]['epoch'])
        tick_close = ticks_data[-1]['quote']

        # Si ya existe una vela y la estamos actualizando
        if len(candles) > 0 and candles[-1]['timestamp'].minute == tick_time.minute:
            candles[-1]['close'] = tick_close
            candles[-1]['high'] = max(candles[-1]['high'], tick_close)
            candles[-1]['low'] = min(candles[-1]['low'], tick_close)
        else:
            # Nueva vela
            new_candle = {
                'timestamp': tick_time,
                'open': tick_close,
                'high': tick_close,
                'low': tick_close,
                'close': tick_close
            }
            candles.append(new_candle)
            print(f"Vela creada: {new_candle}")

        # Solo mantén las últimas 50 velas para el análisis
        if len(candles) > 90:
            candles = candles[-90:]

        analyze_market(ws)

def calculate_rsi(prices, period=14):
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    rsi = [100 - (100 / (1 + (avg_gain / avg_loss))) if avg_loss != 0 else 100]
    for i in range(period, len(prices) - 1):
        current_gain = gains[i]
        current_loss = losses[i]
        avg_gain = (avg_gain * (period - 1) + current_gain) / period
        avg_loss = (avg_loss * (period - 1) + current_loss) / period
        rs = avg_gain / avg_loss if avg_loss != 0 else 0
        rsi_value = 100 - (100 / (1 + rs))
        rsi.append(rsi_value)
    return rsi[-1]

def calculate_macd(prices, short_period=12, long_period=26, signal_period=9):
    short_ema = calculate_ema(prices, short_period)
    long_ema = calculate_ema(prices, long_period)
    min_length = min(len(short_ema), len(long_ema))
    short_ema = short_ema[-min_length:]
    long_ema = long_ema[-min_length:]
    macd_line = [short - long for short, long in zip(short_ema, long_ema)]
    signal_line = calculate_ema(macd_line, signal_period)
    return macd_line, signal_line

def calculate_ema(prices, period):
    if len(prices) < period:
        return np.nan
    multiplier = 2 / (period + 1)
    ema = [np.mean(prices[:period])]
    for price in prices[period:]:
        ema.append((price - ema[-1]) * multiplier + ema[-1])
    return np.array(ema)

def calculate_sma(prices, period):
    if len(prices) < period:
        return np.nan
    return np.mean(prices[-period:])

def calculate_adx(highs, lows, closes, period=14):
    highs = np.array(highs)
    lows = np.array(lows)
    closes = np.array(closes)

    tr = np.maximum.reduce([
        highs[1:] - lows[1:],
        np.abs(highs[1:] - closes[:-1]),
        np.abs(lows[1:] - closes[:-1])
    ])
    atr = calculate_ema(tr, period)
    up_move = highs[1:] - highs[:-1]
    down_move = lows[:-1] - lows[1:]
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
    plus_di = 100 * calculate_ema(plus_dm, period) / atr
    minus_di = 100 * calculate_ema(minus_dm, period) / atr
    dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
    return calculate_ema(dx, period)[-1]

def calculate_bollinger_bands(prices, period=20, std_dev=2):
    sma = calculate_sma(prices, period)
    std = np.std(prices[-period:])
    upper_band = sma + (std_dev * std)
    lower_band = sma - (std_dev * std)
    return upper_band, lower_band

def calculate_stochastic(highs, lows, closes, period=14):
    highest_high = np.max(highs[-period:])
    lowest_low = np.min(lows[-period:])
    current_close = closes[-1]
    k = 100 * (current_close - lowest_low) / (highest_high - lowest_low)
    return k

def fibonacci_levels(min_price, max_price):
    return {
        "23.6%": max_price - (max_price - min_price) * 0.236,
        "38.2%": max_price - (max_price - min_price) * 0.382,
        "50%": (max_price + min_price) / 2,
        "61.8%": max_price - (max_price - min_price) * 0.618,
        "100%": min_price
    }

def analyze_market(ws):
    global candles, contract_open, amount
    print("Analizando velas...")

    if len(candles) < 50:
        print("No hay suficientes velas para realizar el análisis.")
        return

    closes = np.array([candle['close'] for candle in candles])
    highs = np.array([candle['high'] for candle in candles])
    lows = np.array([candle['low'] for candle in candles])

    # Indicadores
    rsi = calculate_rsi(closes, rsi_period)
    macd_line, signal_line = calculate_macd(closes, macd_short, macd_long, macd_signal)
    ema = calculate_ema(closes, ema_period)[-1]
    sma = calculate_sma(closes, sma_period)
    adx = calculate_adx(highs, lows, closes, adx_period)
    upper_band, lower_band = calculate_bollinger_bands(closes, bollinger_period, bollinger_std_dev)
    stochastic = calculate_stochastic(highs, lows, closes, stochastic_period)

    # Lógica para tomar decisiones basadas en los indicadores
    if not contract_open:
        # Estrategia 1: Compra (CALL) basada en RSI, Estocástico y Bandas de Bollinger
        if (rsi < 30 and stochastic < 20 and closes[-1] < lower_band and
            macd_line[-1] > signal_line[-1] and adx > 25 and closes[-1] > ema):
            print("Estrategia 1: Señal de compra detectada. Ejecutando operación CALL.")
            execute_rise_trade(ws, amount)
        elif (rsi > 70 and stochastic > 80 and closes[-1] > upper_band and
              macd_line[-1] < signal_line[-1] and adx > 25 and closes[-1] < ema):
            print("Estrategia 1: Señal de venta detectada. Ejecutando operación PUT.")
            execute_fall_trade(ws, amount)

        # Estrategia 2: Compra (CALL) basada en cruce de MACD y EMA
        elif (macd_line[-1] > signal_line[-1] and closes[-1] > ema and adx > 20):
            print("Estrategia 2: Señal de compra detectada. Ejecutando operación CALL.")
            execute_rise_trade(ws, amount)
        elif (macd_line[-1] < signal_line[-1] and closes[-1] < ema and adx > 20):
            print("Estrategia 2: Señal de venta detectada. Ejecutando operación PUT.")
            execute_fall_trade(ws, amount)

        # Estrategia 3: Compra (CALL) basada en cruce de SMA y Bandas de Bollinger
        elif (closes[-1] > sma and closes[-1] < lower_band and adx > 25):
            print("Estrategia 3: Señal de compra detectada. Ejecutando operación CALL.")
            execute_rise_trade(ws, amount)
        elif (closes[-1] < sma and closes[-1] > upper_band and adx > 25):
            print("Estrategia 3: Señal de venta detectada. Ejecutando operación PUT.")
            execute_fall_trade(ws, amount)

def execute_rise_trade(ws, amount):
    rise_trade_message = {
        "buy": 1,
        "subscribe": 1,
        "price": 2000000,
        "parameters": {
            "amount": amount,
            "basis": "stake",
            "contract_type": "CALL",
            "currency": "USD",
            "duration": 5,
            "duration_unit": "m",
            "symbol": symbol
        }
    }
    ws.send(json.dumps(rise_trade_message))
    print("Operación Rise enviada. Esperando confirmación...")

def execute_fall_trade(ws, amount):
    fall_trade_message = {
        "buy": 1,
        "subscribe": 1,
        "price": 20000000,
        "parameters": {
            "amount": amount,
            "basis": "stake",
            "contract_type": "PUT",
            "currency": "USD",
            "duration": 5,
            "duration_unit": "m",
            "symbol": symbol
        }
    }
    ws.send(json.dumps(fall_trade_message))
    print("Operación Fall enviada. Esperando confirmación...")

def subscribe_to_contract(ws, contract_id):
    contract_message = {
        "proposal_open_contract": 1,
        "contract_id": contract_id
    }
    ws.send(json.dumps(contract_message))

def on_error(ws, error):
    print("Error en WebSocket:", error)

def on_close(ws, close_status_code, close_msg):
    print("Conexión cerrada. Intentando reconectar...")
    time.sleep(10)
    ws.run_forever()

ws = websocket.WebSocketApp(
    "wss://ws.binaryws.com/websockets/v3?app_id=" + app_id,
    on_open=on_open,
    on_message=on_message,
    on_error=on_error,
    on_close=on_close)
ws.run_forever(sslopt={"ca_certs": certifi.where()})
