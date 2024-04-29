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

parser = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter)
parser.add_argument("-p", "--port", default=7496, type=int, choices=[7496, 7497], help='IB Port\n - Live Trading: 7496\n - Paper Trading: 7497')
parser.add_argument("-m", "--micro", action='store_true', help='Contract Type')
args = parser.parse_args()

port = args.port
micro = args.micro

ib = IB()
ib.connect(port=port, clientId=1)

# Data/Parameters
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

net_liq_limit = 0.5
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