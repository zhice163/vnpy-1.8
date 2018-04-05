# encoding: UTF-8

import json
import time
import datetime
import random

from vnpy.trader.vtZcObject import mydb
from vnpy.data.shcifco.vnshcifco import ShcifcoApi, PERIOD_1MIN,PERIOD_1DAY
from vnpy.trader.vtObject import VtBarData
from vnpy.trader.vtConstant import *


# 加载配置
config = open('config.json')
setting = json.load(config)

SHCIFCO_IP = setting['SHCIFCO_IP']
SHCIFCO_PORT  = setting['SHCIFCO_PORT']
SHCIFCO_TOKEN = setting['SHCIFCO_TOKEN']
SYMBOLS = setting['SYMBOLS']

api = ShcifcoApi(SHCIFCO_IP, SHCIFCO_PORT, SHCIFCO_TOKEN)       # 历史行情服务API对象


# 注意：中期的日线函数还是非正式函数

# ----------------------------------------------------------------------
def generateVtBar(d):
    """生成K线"""
    bar = VtBarData()

    bar.symbol = d['symbol']
    bar.vtSymbol = d['symbol']
    bar.date = d['date']
    bar.time = ':'.join([d['time'][:2], d['time'][2:]])
    bar.open = d['open']
    bar.high = d['high']
    bar.low = d['low']
    bar.close = d['close']
    bar.volume = d['volume']
    bar.openInterest = d['openInterest']
    bar.datetime = datetime.datetime.strptime(' '.join([bar.date, bar.time]), '%Y%m%d %H:%M')

    return bar

# ----------------------------------------------------------------------
def downDayBarBySymbol(symbol, num):
    """下载某一合约的日线线数据"""
    start = time.time()
    l = api.getHisDayBar(symbol, num)

    if not l:
        info = u'%s日线数据下载失败' % symbol
        print info
        mydb.writeLog(info)
        return
    i= 0
    for d in l:
        bar = generateVtBar(d)
        d = bar.__dict__
        flt = {'datetime': bar.datetime}
        print(d)
        # cl.replace_one(flt, d, True)
        mydb.dbUpdate(ZQ_DAILY_DB_NAME, symbol, d, flt, upsert=True)

        i = i + 1

    end = time.time()
    cost = (end - start) * 1000

    info = u'合约%s数据下载完成%s - %s，耗时%s毫秒，应下载%d，实下载%d' % (symbol, generateVtBar(l[0]).datetime,
                                         generateVtBar(l[-1]).datetime, cost, num, i)

    if i < num:
        print(u'合约%s未下载足够的数据，计划下载%d，实际下载%d' % (symbol, num, i))
    print info



# ----------------------------------------------------------------------
def downloadAllDayBar(num):
    """下载所有配置中的合约的分钟线数据"""
    print '-' * 50
    print u'开始下载合约分钟线数据'
    print '-' * 50

    for symbol in SYMBOLS:
        downDayBarBySymbol(symbol, num)
        time.sleep(1)

    print '-' * 50
    print u'合约分钟线数据下载完成'
    print '-' * 50

downloadAllDayBar(60)