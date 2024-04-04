# IB Algo Trader

Algorithmic trading application for Interactive Brokers

## Description

This application includes a complete framework for algorithmic trading using Interactive Brokers and Python. The wrapper library ib-insync is used to allow Python to communicate with the local TWS application. Features include:
* Connecting to TWS from the client
* Fetching data for various contract types (examples below)
    * Contract(conId=270639)
    * Stock('AMD', 'SMART', 'USD')
    * Stock('INTC', 'SMART', 'USD', primaryExchange='NASDAQ')
    * Forex('EURUSD')
    * CFD('IBUS30')
    * Future('ES', '20180921', 'GLOBEX')
    * Option('SPY', '20170721', 240, 'C', 'SMART')
    * Bond(secIdType='ISIN', secId='US03076KAA60')
    * Crypto('BTC', 'PAXOS', 'USD')
* Order management (Placing orders, modifying orders, cancelling orders)
* Reading account information such as net liquidity, available funds, margin cushion, etc.

## Getting Started

### Dependencies

* Python 3
* IB Trader Workstation (TWS)
* [ib-insync](https://pypi.org/project/ib-insync/)
```
pip install -r requirements.txt
```

### Installing

* In TWS,
    * File > Global Configuration > API > Settings > Enable ActiveX and Socket Clients
    * File > Global Configuration > API > Settings > Disable Read-Only API
    * Socket port
        * 7496: Live trading account
        * 7497: Paper trading account
* Create strategy.py file in main directory
    * Define function strategy
        * Function input: Pandas Dataframe
        * Function output: 1 (Long signal), -1 (Short signal), 0 (No signal)
```
def strategy(df):
    ...
    if long_condition:
        return 1
    elif short_condition:
        return -1
    else:
        return 0
```
* Modify contracts.json file to set specific contracts to trade using the application
* Modify tf-dur.json file to set the OHLCV timeframe and how much data to read fetch for each contract
### Executing program

```
python app.py
```
