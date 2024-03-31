from ib_insync import *
ib = IB()

# 7496 - real trading account
# 7497 - paper trading account
ib.connect(port=7497, clientId=1)

con = Future('ES', lastTradeDateOrContractMonth='202406',exchange='CME')
data = ib.reqMktData(con)
ib.sleep(3)
print(data.bid)

ib.disconnect()