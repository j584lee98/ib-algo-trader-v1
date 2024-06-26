import json
import time
from datetime import datetime
import argparse
from contextlib import suppress

import numpy as np
import pandas as pd
import schedule
from ib_insync import *

from strategy import strategy

# Settings/Parameters
day_h = 9
day_m = 30
ovn_h = 16
ovn_m = 15

margin_day_mult = 1.43
margin_ovn_mult = 1.00

curr_conv = 1.37
max_trade_risk = 0.02

order_timeout = 10

# Script param tags
parser = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter)
parser.add_argument("-p", "--paper", action='store_true', help='Paper Trading Account')
parser.add_argument("-m", "--micro", action='store_true', help='Micro Contracts')
args = parser.parse_args()

port = 7497 if args.paper else 7496
micro = args.micro

# IB client object
ib = IB()
ib.connect(port=port, clientId=0)

# Contracts + Data Resolution
contracts = json.load(open('contracts.json'))
timeframes = json.load(open('timeframes.json'))

ohlcv_bars = np.array([[None] * len(contracts)] * len(timeframes))

contract_details = []
micro_contract_details = []

for con in contracts.values():
    contract = Contract(
        secType=con['secType'],
        symbol=con['symbol'],
        localSymbol=con['localSymbol'],
        lastTradeDateOrContractMonth=con['lastTradeDateOrContractMonth'],
        exchange=con['exchange']
    )
    micro_contract = Contract(
        secType=con['secType'],
        symbol=con['microSymbol'],
        localSymbol=con['localSymbol'],
        lastTradeDateOrContractMonth=con['lastTradeDateOrContractMonth'],
        exchange=con['exchange']
    )
    contract = ib.qualifyContracts(contract)[0]
    micro_contract = ib.qualifyContracts(micro_contract)[0]
    contract_details.append(contract)
    micro_contract_details.append(micro_contract)

open_order_datetime = datetime.now()
algo_live = False

# Order placing - bracket setup
def place_order(contract, direction, amount, price, stop):
    mod = amount % 4
    amount1 = int(amount/4) + (1 if mod >= 1 else 0)
    amount2 = int(amount/4) + (1 if mod >= 2 else 0)
    amount3 = int(amount/4) + (1 if mod == 3 else 0)
    amount4 = int(amount/4)

    takeProfit1 = price + stop * 2 if direction == 'BUY' else price - stop * 2
    takeProfit2 = price + stop * 4 if direction == 'BUY' else price - stop * 4
    takeProfit3 = price + stop * 6 if direction == 'BUY' else price - stop * 6
    takeProfit4 = price + stop * 12 if direction == 'BUY' else price - stop * 12

    stopLoss = price - stop if direction == 'BUY' else price + stop
    trigger = price + stop if direction == 'BUY' else price - stop
    adjustedStop = price

    order1 = ib.bracketOrder(
        action=direction,
        quantity=amount1,
        limitPrice=price,
        takeProfitPrice=takeProfit1,
        stopLossPrice=stopLoss,
        adjustedOrderType='STP',
        triggerPrice=trigger,
        adjustedStopPrice=adjustedStop,
        tif='GTC',
        outsideRth=True
    )
    order2 = ib.bracketOrder(
        action=direction,
        quantity=amount2,
        limitPrice=price,
        takeProfitPrice=takeProfit2,
        stopLossPrice=stopLoss,
        adjustedOrderType='STP',
        triggerPrice=trigger,
        adjustedStopPrice=adjustedStop,
        tif='GTC',
        outsideRth=True
    )
    order3 = ib.bracketOrder(
        action=direction,
        quantity=amount3,
        limitPrice=price,
        takeProfitPrice=takeProfit3,
        stopLossPrice=stopLoss,
        adjustedOrderType='STP',
        triggerPrice=trigger,
        adjustedStopPrice=adjustedStop,
        tif='GTC',
        outsideRth=True
    )
    order4 = ib.bracketOrder(
        action=direction,
        quantity=amount4,
        limitPrice=price,
        takeProfitPrice=takeProfit4,
        stopLossPrice=stopLoss,
        adjustedOrderType='STP',
        triggerPrice=trigger,
        adjustedStopPrice=adjustedStop,
        tif='GTC',
        outsideRth=True
    )
    for b1 in order1:
        ib.placeOrder(contract, b1)
    for b2 in order2:
        ib.placeOrder(contract, b2)
    for b3 in order3:
        ib.placeOrder(contract, b3)
    for b4 in order4:
        ib.placeOrder(contract, b4)
    ib.sleep(3)

# Check if intraday hours
def is_intraday(intra_start_hour, intra_start_minute, intra_end_hour, intra_end_minute):
    dt_now = datetime.now()
    now_hour = dt_now.hour
    now_minute = dt_now.minute
    if now_hour < intra_start_hour:
        return False
    elif now_hour == intra_start_hour:
        if now_minute < intra_start_minute:
            return False
        else:
            return True
    elif now_hour < intra_end_hour:
        return True
    elif now_hour == intra_end_hour:
        if now_minute < intra_end_minute:
            return True
        else:
            return False
    else:
        return False

# Calculate maximum number of contracts available for order
def calc_max_contracts(contract, tick_value, tick_stop):
    net_liquidation = float([x for x in ib.accountSummary() if x.tag == 'NetLiquidation'][0].value)
    full_init_margin_req = float([x for x in ib.accountSummary() if x.tag == 'FullInitMarginReq'][0].value)
    margin_available = net_liquidation - full_init_margin_req
    contract_init_margin_req = float(ib.whatIfOrder(contract, Order(action='BUY', totalQuantity=1, orderType='MKT')).initMarginChange)
    margin_multiplier = margin_day_mult if is_intraday(day_h, day_m, ovn_h, ovn_m) else margin_ovn_mult
    adj_init_margin_req = contract_init_margin_req * margin_multiplier
    tick_value = tick_value * 0.1 if micro else tick_value
    adj_tick_value = tick_value * curr_conv
    contract_risk = adj_tick_value * tick_stop

    max_risk = margin_available * max_trade_risk

    return min(int(margin_available/adj_init_margin_req), int(max_risk/contract_risk))

# Cancel any orders that have been open for longer than the order timeout
def cancel_stale_parent_orders(last_bar):
    timediff = (last_bar - open_order_datetime).total_seconds() / 60.0
    if timediff >= order_timeout:
        parentOrders = [x for x in ib.openOrders() if x.parentId == 0]
        for order in parentOrders:
            ib.cancelOrder(order)

# Run for each contract after bar update
def on_bars_update(bars, contract, desc):
    global algo_live
    last_bar = bars[-1].date.replace(tzinfo=None)
    if algo_live:
        cancel_stale_parent_orders(last_bar)
    if len(ib.openOrders()) == 0 and len(ib.positions()) == 0:
        max_contracts = calc_max_contracts(contract, desc['tickNotional'], desc['tickStop'])
        if max_contracts >= 4:
            # Check strategy
            df = pd.DataFrame(bars)[['date', 'open', 'high', 'low', 'close']].iloc[:-1]
            ret = strategy(df)
            if ret == 0:
                pass
            else:
                stop = desc['tickStop'] * desc['tickSize']
                global open_order_datetime
                if ret == 1:
                    # Long order
                    place_order(contract, 'BUY', max_contracts, df['close'].iloc[-1], stop)
                else:
                    # Short order
                    place_order(contract, 'SELL', max_contracts, df['close'].iloc[-1], stop)
                open_order_datetime = last_bar
                algo_live = True

# Periodic data fetch from IB
def fetch_bars():
    updated = np.array([[False] * len(contracts)] * len(timeframes))
    while not all([all(row) for row in updated]):
        for i, (tf, dur) in enumerate(timeframes.items()):
            for j, desc in enumerate(contracts.values()):
                if updated[i][j] == False:
                    with suppress(IndexError):
                        ohlcv_bars[i][j] = ib.reqHistoricalData(
                            contract_details[j],
                            endDateTime='',
                            durationStr=dur,
                            barSizeSetting=tf,
                            whatToShow='TRADES',
                            useRTH=False
                        )
                        if ohlcv_bars[i][j][-1].date.minute == datetime.now().minute:
                            contract = micro_contract_details[j] if micro else contract_details[j]
                            on_bars_update(ohlcv_bars[i][j], contract, desc)
                            updated[i][j] = True
        time.sleep(1)

def main():
    # Run every 10 minutes
    schedule.every().hour.at(":00").do(fetch_bars)
    schedule.every().hour.at(":10").do(fetch_bars)
    schedule.every().hour.at(":20").do(fetch_bars)
    schedule.every().hour.at(":30").do(fetch_bars)
    schedule.every().hour.at(":40").do(fetch_bars)
    schedule.every().hour.at(":50").do(fetch_bars)

    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    main()