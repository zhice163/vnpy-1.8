# encoding: UTF-8


import sys
reload(sys)
sys.setdefaultencoding('utf8')

import os
if os.path.exists('/home/ubuntu/vnpy/vnpy-1.8/'):
    sys.path.append("/home/ubuntu/vnpy/vnpy-1.8/")
    print('sys.path.append - /home/ubuntu/vnpy/vnpy-1.8/')
elif os.path.exists('/srv/vnpy18'):
    sys.path.append("/srv/vnpy18")
    print('sys.path.append - /srv/vnpy18')


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
        return info
    i= 0
    for d in l:
        bar = generateVtBar(d)
        d = bar.__dict__
        flt = {'datetime': bar.datetime}
        # cl.replace_one(flt, d, True)
        mydb.dbUpdate(ZQ_DAILY_DB_NAME, symbol, d, flt, upsert=True)

        i = i + 1

    end = time.time()
    cost = (end - start) * 1000

    info = u'合约%s数据下载完成，耗时%s毫秒，应下载%d，实下载%d' % (symbol, cost, num, i)

    if i < num:
        info = u'【异常】合约%s未下载足够的数据，计划下载%d，实际下载%d' % (symbol, num, i)
    print info

    return info




# 计算主力合约
def update_dominant_contract():
    mydb.writeLog(u'【计算主力合约】开始计算主力合约。')
    # 查询合约表中所有的合约信息
    ret_contract = mydb.dbQuery(MAIN_DB_NAME, TB_CONTRACT, {}, ret={"vtSymbol": 1, "productID": 1, "expiryDate": 1})
    # 查询现在主力表中的数据
    ret_dominant = mydb.dbQuery(MAIN_DB_NAME, TB_DOMINANT, {},
                                ret={"productID": 1, "vtSymbol": 1, "updateTime": 1, "expiryDate": 1,
                                     "openInterest": 1})

    updateTime = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))  # 当时的时间
    updateMonth = time.strftime('%Y%m', time.localtime(time.time()))  # 当前月
    updateDay = time.strftime('%Y%m%d', time.localtime(time.time()))  # 当前日期
    contractDict = {}  # 记录productid 和 最大的持仓量,且记录的合约都是有效的


    for tmp in ret_contract:
        vtSymbol = tmp["vtSymbol"]
        productID = tmp["productID"]
        expiryDate = tmp["expiryDate"]

        # 如果合约在有效期内(交割月之前），查询合约在当天的持仓量
        if updateMonth < expiryDate[:6]:
            # 查询合约当天的持仓信息
            ret_tick = mydb.dbQuery(ZQ_DAILY_DB_NAME, vtSymbol, {'date': updateDay},
                                   ret={"vtSymbol": 1, "updateTime": 1, "openInterest": 1})
            if ret_tick.count() == 1 :
                openInterest = ret_tick[0]["openInterest"]
                info = contractDict.get(productID,None)
                if info == None or openInterest > info["openInterest"]:
                    contractDict[productID] = {"vtSymbol":vtSymbol,"expiryDate":expiryDate,"openInterest":openInterest}
            else:
                mydb.writeLog(u'【ERROR】【update_dominant_contract】查询%s合约在%s日期的信息有误，条目数为%d。' % (vtSymbol,updateDay,ret_tick.count()))
                info = contractDict.get(productID, None)
                if info == None:
                    contractDict[productID] = {"vtSymbol": vtSymbol, "expiryDate": expiryDate,
                                               "openInterest": 0}
    l = []
    for key, value in contractDict.items():
        productID = key
        for tmp_info in ret_dominant:
            if tmp_info["productID"] == productID:
                # 只有主力表中的合约没到交割月，且 当天持仓量小于主力表中的1.1倍时，拿主力表中的数据进行覆盖
                if updateMonth < tmp_info["expiryDate"][:6] and value["openInterest"] < 1.1*tmp_info["openInterest"]:
                    contractDict[productID] = {"vtSymbol": tmp_info["vtSymbol"], "expiryDate": tmp_info["expiryDate"],
                                               "openInterest": tmp_info["openInterest"]}

        l.append({"productID":productID,
              "vtSymbol":contractDict[productID]["vtSymbol"],
              "expiryDate":contractDict[productID]["expiryDate"],
              "openInterest": contractDict[productID]["openInterest"],
                "date":updateDay, # 对应日线表中的date
              "updateTime": updateTime})

    if len(l) > 0:
        # 写入历史表中
        mydb.dbInsert_many(MAIN_DB_NAME, TB_DOMINANT_HIS, l)
        mydb.writeLog(u'【数据清洗】主力历史表更新完成。')
        # 写入主力表中
        # 如果主力表不为空，先删除
        if ret_dominant.count() != 0:
            mydb.dbRemove(MAIN_DB_NAME, TB_DOMINANT, {})
        # 写入主力表
        mydb.dbInsert_many(MAIN_DB_NAME, TB_DOMINANT, l)
        mydb.writeLog(u'【数据清洗】主力表更新完成。')
    else:
        mydb.writeLog(u'【ERROR】【数据清洗】发现 l 为空。')

    # 返回要在邮件中发送的信息
    info = '*'*10 + ' 主力合约如下 ' + '*'*10 + '\n'
    for _info in l:
        info = info + _info['productID'] + ' ' + '-'*(10-len(_info['productID'])) + ' '+ _info['vtSymbol'] + '\n'
    print info
    return info



#
# 获取库中所有的合约信息
def getAllContract():
    # 在合约表中，查询 产品id 合约名 和 合约终止日期
    ret_contract = mydb.dbQuery(MAIN_DB_NAME, TB_CONTRACT, {}, ret={"vtSymbol": 1, "productID": 1, "expiryDate": 1})
    now_date = time.strftime('%Y%m%d', time.localtime(time.time()))
    return [ret['vtSymbol'] for ret in ret_contract if now_date < ret['expiryDate']]

# ----------------------------------------------------------------------
def downloadAllDayBar(num):
    """下载所有配置中的合约的分钟线数据"""
    print '-' * 50
    print u'开始下载合约分钟线数据'
    print '-' * 50
    vtSymbolList = getAllContract()

    info = '*' * 20 + ' 日线下载数据如下 ' + '*' * 20 + '\n'
    for symbol in vtSymbolList:
        retInfo = downDayBarBySymbol(symbol, num)
        info = info + str(retInfo) + '\n'
        time.sleep(1)


    print '-' * 50
    print u'合约分钟线数据下载完成'
    print '-' * 50
    print info
    return info
#downloadAllDayBar(5)
#update_dominant_contract()
