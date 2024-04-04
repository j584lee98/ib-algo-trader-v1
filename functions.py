# Functions for strategies

import numpy as np

def SMA(prices, period):
    sma = np.zeros(len(prices))
    for i in range(period-1, len(prices)):
        sma[i] = np.mean(prices[i+1-period:i+1])
    return sma

def EMA(prices, period):
    alpha = 2/(period+1)
    ema = np.zeros(len(prices))
    ema[period-1] = prices[period-1]
    for i in range(period, len(prices)):
        ema[i] = (prices[i] * alpha) + (ema[i-1] * (1-alpha))
    return ema

def RMA(prices, period):
    alpha = 1/period
    rma = np.zeros(len(prices))
    sma = np.mean(prices[:period])
    rma[period-1] = sma
    for i in range(period, len(prices)):
        rma[i] = (prices[i] * alpha) + (rma[i-1] * (1-alpha))
    return rma

def STDEV(prices, period):
    stdev = np.zeros(len(prices))
    for i in range (period-1, len(prices)):
        stdev[i] = np.std(prices[i+1-period:i+1])
    return stdev