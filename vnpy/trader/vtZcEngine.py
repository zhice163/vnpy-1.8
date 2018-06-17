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

try:
    import cPickle as pickle  # python 2
except ImportError as e:
    import pickle

# 海龟策略用到的一些表名和数据库名
MAIN_DB_NAME = 'VnTrader_Main_Db'
TB_HG_MAIN = "TB_HG_MAIN"


# 自定义日志级别
LOG_DEBUG = 10
LOG_INFO = 20
LOG_IMPORTANT = 30
LOG_ERROR = 40


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

    def dbAggregateSum(self, dbName, collectionName, d):

        ret = []
        if self.dbClient:
            db = self.dbClient[dbName]
            collection = db[collectionName]

            if collection:
                cursor = collection.aggregate(d)

                if cursor:
                    return cursor
        return []


                #----------------------------------------------------------------------
    def dbUpdate(self, dbName, collectionName, d, flt, upsert=False):
        """向MongoDB中更新数据，d是具体数据，flt是过滤条件，upsert代表若无是否要插入"""
        if self.dbClient:
            db = self.dbClient[dbName]
            collection = db[collectionName]
            collection.replace_one(flt, d, upsert)
        else:
            self.writeLog(text.DATA_UPDATE_FAILED)

    def dbClose(self):

        if self.dbClient:
            self.dbClient.close()
        self.eventEngine.stop()


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

# 海龟 策略的数据库封装
class hgDbEngine(ctaDbEngine):

    # 将海龟一些数据保存在数据库中
    # 目前在三个地方调用： 每次 onbar onOrder onTrading
    def saveIntoDB(self, hgStrategy):
        hgStrategy.myPrint(LOG_DEBUG, 'saveIntoDB', '进入saveIntoDB。')
        ret_data = {}
        d = hgStrategy.__dict__

        ret_data['instanceName'] = hgStrategy.instanceName
        ret_data['instanceId'] = hgStrategy.instanceId

        for key in hgStrategy.pickleItemList:
            # 对于字典和列表类型的变量，使用pickle进行存储
            """
            if isinstance(d[key], dict) or isinstance(d[key], list):
                pickleData = pickle.dumps(d[key])
                ret_data[key] = pickleData
            else:
                ret_data[key] = d[key]
            """
            # 换成全用pick存储的
            pickleData = pickle.dumps(d[key])
            ret_data[key] = pickleData

        # 写入数据库
        flt = {'instanceName': hgStrategy.instanceName, 'instanceId': hgStrategy.instanceId}
        hgStrategy.myPrint(LOG_DEBUG, 'saveIntoDB', ret_data)
        self.dbEngine.dbUpdate(MAIN_DB_NAME, TB_HG_MAIN, ret_data, flt, upsert=True)

    # 根据数据库记录恢复数据
    def recoveryFromDb(self, hgStrategy):

        hgStrategy.myPrint(LOG_DEBUG, 'recoveryFromDb', '进入recoveryFromDb.')
        flt = {'instanceName': hgStrategy.instanceName, 'instanceId': hgStrategy.instanceId}
        ret = self.dbEngine.dbQuery(MAIN_DB_NAME, TB_HG_MAIN, flt)

        # 数据库没有查到记录，正常返回
        if ret is None or ret.count() == 0:
            hgStrategy.myPrint(LOG_INFO, 'recoveryFromDb', '数据库没有查到记录，正常返回。')
            return

        if ret.count() == 1:

            theData = ret[0]
            # TODO 处理key值不存在的异常

            # 进行数据恢复
            d = hgStrategy.__dict__
            for key in hgStrategy.pickleItemList:
                # 对于字典和列表类型的变量，使用pickle进行存储
                """
                if isinstance(d[key], dict) or isinstance(d[key], list):
                    pickleData = pickle.loads(str(theData[key]))
                    d[key] = pickleData
                else:
                    d[key] = theData[key]
                """
                pickleData = pickle.loads(str(theData[key]))
                d[key] = pickleData

            hgStrategy.myPrint(LOG_IMPORTANT, 'recoveryFromDb', '从数据库载入完成。')
            hgStrategy.printCells("*" * 20 + " in recoveryFromDb")
        else:
            hgStrategy.stopTrading()
            hgStrategy.myPrint(LOG_ERROR, 'recoveryFromDb', '返回多条记录，flt = %s' % (str(flt)))


    # 获取一个海龟实例的全部信息
    def getHgInstanceInfo(self, instanceName, pickleItemList):

        flt = {'instanceName': instanceName}
        ret = self.dbEngine.dbQuery(MAIN_DB_NAME, TB_HG_MAIN, flt)

        # 数据库没有查到记录，正常返回
        if ret is None or ret.count() == 0:
            print('hgDbEngine 数据库中无记录。')
            return

        for theData in ret:

            # 进行数据恢复
            d = []
            for key in pickleItemList:
                # 对于字典和列表类型的变量，使用pickle进行存储
                if isinstance(d[key], dict) or isinstance(d[key], list):
                    pickleData = pickle.loads(str(theData[key]))
                    d[key] = pickleData
                else:
                    d[key] = theData[key]





