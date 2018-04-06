# encoding: UTF-8

from pymongo import MongoClient, ASCENDING
from pymongo.errors import ConnectionFailure

from vnpy.event import Event
from vnpy.trader.vtGlobal import globalSetting
from vnpy.trader.vtEvent import *
from vnpy.trader.language import text
from vnpy.trader.vtObject import VtLogData
from vnpy.trader.vtObject import VtSingleton

from datetime import datetime
from vnpy.trader.vtConstant import  *
from vnpy.trader.vtObject import VtTickData, VtBarData
from pymongo import  ASCENDING, DESCENDING


########################################################################
# add by zhice
class DbEngine(object):
    # 单例模式
    __metaclass__ = VtSingleton

    def __init__(self, eventEngine):
        # MongoDB数据库相关
        self.dbClient = None
        self.eventEngine = eventEngine
        self.eventEngine.start()

        # 初始化数据了连接
        self.dbConnect()

    # ----------------------------------------------------------------------
    def dbConnect(self):
        """连接MongoDB数据库"""
        if not self.dbClient:
            # 读取MongoDB的设置
            try:
                print(globalSetting)
                # 设置MongoDB操作的超时时间为0.5秒
                self.dbClient = MongoClient(globalSetting['mongoHost'], globalSetting['mongoPort'],
                                            connectTimeoutMS=500)

                # 配置用户名和密码
                db = self.dbClient.admin
                db.authenticate(globalSetting['mongoUser'], globalSetting['mongoPassword'])

                # 调用server_info查询服务器状态，防止服务器异常并未连接成功
                self.dbClient.server_info()

                self.writeLog(text.DATABASE_CONNECTING_COMPLETED)

                # 如果启动日志记录，则注册日志事件监听函数

                if globalSetting['mongoLogging']:
                    self.eventEngine.register(EVENT_LOG, self.dbLogging)

            except ConnectionFailure:
                self.writeLog(text.DATABASE_CONNECTING_FAILED)

    def dbLogging(self, event):
        """向MongoDB中插入日志"""
        log = event.dict_['data']
        d = {
            'content': log.logContent,
            'time': log.logTime,
            'gateway': log.gatewayName
        }
        todayDate = self.todayDate = datetime.now().strftime('%Y%m%d')
        self.dbInsert_one(LOG_DB_NAME, todayDate, d)

    def writeLog(self, content):
        """快速发出日志事件"""
        log = VtLogData()
        log.logContent = content
        log.gatewayName = 'DB_ENGINE'
        event = Event(type_=EVENT_LOG)
        event.dict_['data'] = log
        self.eventEngine.put(event)

    # modify by zhice : add ret
    def dbQuery(self, dbName, collectionName, d, sortKey='', sortDirection=ASCENDING, ret={'_id': 0}, limit = None):
        """从MongoDB中读取数据，d是查询要求，返回的是数据库查询的指针"""

        if self.dbClient:
            db = self.dbClient[dbName]
            collection = db[collectionName]

            if sortKey:
                if limit:
                    cursor = collection.find(d, ret).limit(limit).sort(sortKey, sortDirection)  # 对查询出来的数据进行排序
                else:
                    cursor = collection.find(d, ret).sort(sortKey, sortDirection)  # 对查询出来的数据进行排序
            else:
                cursor = collection.find(d, ret)

            if cursor:
                return cursor
            else:
                return []
        else:
            self.writeLog(text.DATA_QUERY_FAILED)
            return []

    def dbInsert_one(self, dbName, collectionName, d):
        """向MongoDB中插入数据，d是具体数据"""
        if self.dbClient:
            db = self.dbClient[dbName]
            collection = db[collectionName]
            collection.insert_one(d)
        else:
            self.writeLog(text.DATA_INSERT_FAILED)

    def dbDelete_one(self, dbName, collectionName, d):
        """删除1条数据，d是具体数据"""
        if self.dbClient:
            db = self.dbClient[dbName]
            collection = db[collectionName]
            collection.delete_one(d)
        else:
            self.writeLog(text.DATA_DELETE_FAILED)


    def dbInsert_many(self, dbName, collectionName, d):
        """向MongoDB中插入数据，d是具体数据"""
        if self.dbClient:
            db = self.dbClient[dbName]
            collection = db[collectionName]
            collection.insert_many(d)
        else:
            self.writeLog(text.DATA_INSERT_MANY_FAILED)

    def dbRemove(self, dbName, collectionName, d):
        """向MongoDB中插入数据，d是具体数据"""
        if self.dbClient:
            db = self.dbClient[dbName]
            collection = db[collectionName]
            collection.remove(d)
        else:
            self.writeLog(text.DATA_INSERT_MANY_FAILED)

    def getCollectionNames(self, dbName):
        """查询指定数据库中的所有表名"""
        if self.dbClient:
            db = self.dbClient[dbName]
            cursor = db.collection_names()

            if cursor:
                return cursor
            else:
                return []
        else:
            self.writeLog(text.DATA_GACN_MANY_FAILED)

    #----------------------------------------------------------------------
    def dbUpdate(self, dbName, collectionName, d, flt, upsert=False):
        """向MongoDB中更新数据，d是具体数据，flt是过滤条件，upsert代表若无是否要插入"""
        if self.dbClient:
            db = self.dbClient[dbName]
            collection = db[collectionName]
            collection.replace_one(flt, d, upsert)
        else:
            self.writeLog(text.DATA_UPDATE_FAILED)


# cat 策略的数据库封装
class ctaDbEngine(object):

    def __init__(self, dbEngine):
        self.dbEngine = dbEngine


    def getDominantByProductID(self, productID):
        # 根据合约名称获取主力合约
        ret = self.dbEngine.dbQuery(MAIN_DB_NAME, TB_DOMINANT, {'productID': productID}, ret={"vtSymbol": 1})
        if ret.count() == 1:
            return ret[0]['vtSymbol']
        else:
            return None

            # 获取所有合约信息 add by zhice

    def getAllContract(self):
        # 查询合约表中所有的合约信息
        ret_contract = self.dbEngine.dbQuery(MAIN_DB_NAME, TB_CONTRACT, {})
        ret = {}
        for contract in ret_contract:
            ret[contract["symbol"]] = contract
        return ret


    def loadDayBar(self, vtSymbol, days):
        # 读取指定合约指定天数的日线信息
        ret_bar = self.dbEngine.dbQuery(ZQ_DAILY_DB_NAME, vtSymbol, {}, sortKey='date', sortDirection=DESCENDING, limit=days)

        if ret_bar:
            ret_bar = list(ret_bar)
            ret_bar.reverse()

            l = []
            for d in ret_bar:
                bar = VtBarData()
                bar.__dict__ = d
                l.append(bar)
            return l

        else:
            return []