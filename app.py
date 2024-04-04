import json
import time
from datetime import datetime

import numpy as np
import pandas as pd
import schedule
from ib_insync import *

from strategy import strategy

ib = IB()

# 7496 - Real trading account
# 7497 - Paper trading account
ib.connect(port=7497, clientId=1)

# Data/Parameters
contracts = json.load(open('contracts.json'))
timeframes = json.load(open('timeframes.json'))

ohlcv_bars = np.array([[None] * len(contracts)] * len(timeframes))

contract_details = []
for con in contracts.values():
    contract = Contract(
        secType=con['secType'],
        symbol=con['symbol'],
        localSymbol=con['localSymbol'],
        lastTradeDateOrContractMonth=con['lastTradeDateOrContractMonth'],
        exchange=con['exchange']
    )
    contract = ib.qualifyContracts(contract)[0]
    contract_details.append(contract)

net_liq_limit = 0.7
order_timeout = 10
open_order_datetime = datetime.now()

# Order placing - 3 bracket setup
def place_order(contract, direction, amount, price, stop):
    mod = amount % 3
    amount1 = int(amount/3) + (1 if mod >= 1 else 0)
    amount2 = int(amount/3) + (1 if mod == 2 else 0)
    amount3 = int(amount/3)
    takeProfit1 = price + stop * 2 if direction == 'BUY' else price - stop * 2
    takeProfit2 = price + stop * 4 if direction == 'BUY' else price - stop * 4
    takeProfit3 = price + stop * 6 if direction == 'BUY' else price - stop * 6
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
    for b1 in order1:
        ib.placeOrder(contract, b1)
    for b2 in order2:
        ib.placeOrder(contract, b2)
    for b3 in order3:
        ib.placeOrder(contract, b3)

# Calculate maximum number of contracts available for order
def calc_max_contracts(contract):
    netLiquidation = float([x for x in ib.accountSummary() if x.tag == 'NetLiquidation'][0].value)
    fullInitMarginReq = float([x for x in ib.accountSummary() if x.tag == 'FullInitMarginReq'][0].value)
    marginAvailable = netLiquidation * net_liq_limit - fullInitMarginReq
    marginRequirement = float(ib.whatIfOrder(contract, Order(action='BUY', totalQuantity=1, orderType='MKT')).initMarginChange)
    return int(marginAvailable/marginRequirement)

# Cancel any orders that have been open for longer than the order timeout
def cancel_stale_parent_orders():
    timediff = (datetime.now() - open_order_datetime).total_seconds() / 60.0
    if timediff > order_timeout:
        parentOrders = [x for x in ib.openOrders() if x.parentId == 0]
        for order in parentOrders:
            ib.cancelOrder(order)

# Run for each contract after bar update
def on_bars_update(bars, contract, desc):
    cancel_stale_parent_orders()
    parentOrders = [x for x in ib.openOrders() if x.parentId == 0]
    # if not parentOrders:
    if len(ib.openOrders()) == 0 and len(ib.positions()) == 0:
        max_contracts = calc_max_contracts(contract)
        if max_contracts >= 3:
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
                    open_order_datetime = bars[-1].date.replace(tzinfo=None)
                else:
                    # Short order
                    place_order(contract, 'SELL', max_contracts, df['close'].iloc[-1], stop)
                    open_order_datetime = bars[-1].date.replace(tzinfo=None)

# Periodic data fetch from IB
def fetch_bars():
    updated = np.array([[False] * len(contracts)] * len(timeframes))
    while not all([all(row) for row in updated]):
        for i, (tf, dur) in enumerate(timeframes.items()):
            for j, desc in enumerate(contracts.values()):
                if updated[i][j] == False:
                    ohlcv_bars[i][j] = ib.reqHistoricalData(
                        contract_details[j],
                        endDateTime='',
                        durationStr=dur,
                        barSizeSetting=tf,
                        whatToShow='TRADES',
                        useRTH=False
                    )
                    if ohlcv_bars[i][j][-1].date.minute == datetime.now().minute:
                        on_bars_update(ohlcv_bars[i][j], contract_details[j], desc)
                        updated[i][j] = True
        time.sleep(1)

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

# ib.disconnect()