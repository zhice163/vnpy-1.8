# encoding: UTF-8

"""
海龟交易法则
1、最终的成交价在onTrade里面
2、onOrder里面有sessionID 和 frontID，onTrade 里面没有

问题
1、分批成交时，onOrder ontrade是怎么样的呢

一些思路
1、增加测试是否运行健康的状态监控


# 头寸基本规则，目前只做了单方向12个头寸的限定
1、单个市场最多4个头寸
2、高度关联的多个市场6个头寸
3、松散关联的多个市场10个头寸
4、单个方向（多头或空头）12个头寸

# 夜盘属于第二天

"""

from __future__ import division

from datetime import datetime

from vnpy.trader.app.ctaStrategy.ctaTemplate import (CtaTemplate,
                                                     BarGenerator,
                                                     ArrayManager)
from vnpy.trader.vtConstant import (DIRECTION_LONG, DIRECTION_SHORT,
                                    STATUS_NOTTRADED, STATUS_PARTTRADED, STATUS_UNKNOWN,
                                    PRICETYPE_MARKETPRICE)
from vnpy.trader.vtZcEngine import hgDbEngine
from vnpy.trader.vtZcObject import mydb, Cell, LOG_IMPORTANT, LOG_ERROR, LOG_DEBUG, LOG_INFO, hgReport

try:
    import cPickle as pickle    #python 2
except ImportError as e:
    import pickle


import numpy as np
from vnpy.trader.zcFuns import genHtmls, saveImg

import os

BREAK_MIDDLEWINDOW = '20日突破'
HALF_N = '0.5N'


# 海龟策略用到的一些表名和数据库名
MAIN_DB_NAME = 'VnTrader_Main_Db'
TB_HG_MAIN = "TB_HG_MAIN"




########################################################################
# 每个实例监控一个品种，通过数据库进行一个交易实例的组合，一个交易实例包含多个品种的交易
class HgStrategy(CtaTemplate):
    """Demo"""
    className = 'haigui'
    author = u'zhice'
    priceTpye = PRICETYPE_MARKETPRICE # 设置为市价单

    
    # 参数列表，保存了参数的名称
    paramList = ['name',
                 'className',
                 'author',
                 'vtSymbol',
                 'productID',
                 'shortWindow',
                 'middleWindow',
                 'longWindow',

                 # 交易的实例名信息，一个实例包含一组策略实例
                 'instanceName',
                 'instanceId',
                 'instanceAccount']

    # 保存了要用pickle恢复的参数列表
    pickleParamList = []
    
    # 同步列表，保存了需要保存到数据库的变量名称
    syncList = ['pos']



    #----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        """Constructor"""
        super(HgStrategy, self).__init__(ctaEngine, setting)

        self.GOON = False

        # 每次启动要重建的参数
        self.bg = BarGenerator(self.onBar)
        self.cacheDays = max(self.longWindow, (2 * self.middleWindow) + 1)
        self.am = ArrayManager(self.cacheDays)
        self.myDb = mydb  # 数据库引擎
        self.hgDbEngine = hgDbEngine(mydb)  # cta 数据库操作的一些封装
        self.hgReport = hgReport(self.hgDbEngine)
        self.monitor = {}  # 合约当天的 10日线高低、20日线高低、55日线和ART信息
        self.contracts = self.hgDbEngine.getAllContract()  # 最新的合约信息
        self.sessionID = None  # 本地交易
        self.frontID = None  # 本次交易的
        self.logLevel = LOG_INFO # 设置日志输出级别
        self.bGenImg = True # 是否生成图像标志位
        # self.sessionid = uuid.uuid1() # 本次唯一id

        # 关于生成图片与展示html的两个关键变量
        self.imgHtmlRootDir = ''  # 图片和展示html的根路径
        if os.path.exists('/home/ubuntu/vnpy/vnpy-1.8/'):
            self.imgHtmlRootDir = '/home/ubuntu/'
            print('sys.path.append - /home/ubuntu/vnpy/vnpy-1.8/')
        elif os.path.exists('/srv/vnpy18'):
            self.imgHtmlRootDir = '/srv/img_html/'
            print('sys.path.append - /srv/vnpy18')

        # 【重要】所有要pickle存储的数据都要记录在变量中
        #  True 代表用pickle存储，False代表用正常方式存储
        self.pickleItemDict = {"orderList": True,
                               "tradeList": True,
                               "hgCellList": True,
                               "plan_add_price": False,
                               "atr": False,
                               "cell_num": False,
                               "s_or_b": False,
                               "offsetProfit": False,
                               "floatProfit": False,
                               "max_cell_num": False,
                               "health": False,
                               "MaxInstanceTotalCellNum": False,
                               "totalRealUnit": False,
                               "vtSymbol": False,
                               "symbolName": False}

        # 每次启动要用pickle恢复的数据
        #self.hgPosition = {} # 持仓信息
        self.orderList = [] # 报单列表
        self.tradeList = [] # 成交列表
        self.hgCellList = []  # 持仓列表，元素为HgCell
        self.plan_add_price = -1  # 加仓价格
        self.atr = -1
        self.cell_num = 0  # 持仓量
        self.s_or_b = ''  # 买卖方向
        self.offsetProfit = -1  # 平仓盈亏
        self.floatProfit = -1  # 浮动盈亏
        self.max_cell_num = 3  # 最大持仓量
        self.health = True # 交易状态是否健康
        self.MaxInstanceTotalCellNum = 12 # 相同实例下单方向的总持仓上限
        self.totalRealUnit = 0 # 真实总持仓
        self.vtSymbol = ''
        self.symbolName = '' # 合约中文名字


        fileProductID = self.productID
        # TODO通过pickle进行数据恢复
        self.hgDbEngine.recoveryFromDb(self)

        # 数据库恢复的 productID 与 配置文件中的不一致，属于异常情况，停止交易
        if fileProductID <> self.productID:
            self.stopTrading()
            self.myPrint(LOG_ERROR, '__init__', '文件与数据库中productID不一致，停止交易。')


        # 海龟交易主力合约，配置时 symbol 配置的是品种名称，进行翻译。
        ret = self.hgDbEngine.getDominantByProductID(self.productID)

        # 判断是否需要进行手工移仓
        # TODO 目前出现移仓情况需要手动处理
        if ret is not None and self.vtSymbol != "" and self.vtSymbol != ret:
            self.stopTrading() # 需要进行手工移仓
            self.myPrint(LOG_ERROR, '__init__', '需要进行手工移仓。')


        if ret is not None and self.vtSymbol == "" :
            self.vtSymbol = ret

        if ret is None:
            self.stopTrading()
            self.myPrint(LOG_ERROR, '__init__', '获取主力合约失败。')

        self.symbolName = self.contracts[self.vtSymbol]['name'] # 获取合约中文名字

        # 只在第一个实例中发送报告
        if self.instanceId.endswith('_01'):
            self.myPrint(LOG_INFO, 'onInit', '发送报告: ' + self.instanceName)
            self.hgReport.sendReport(self.instanceName, self.pickleItemDict)

        if self.health:
            self.myPrint(LOG_INFO, '__init__', '初始化完成。')
        else:
            self.myPrint(LOG_ERROR, '__init__', '初始化失败。')


    def stopTrading(self, info = ""):
        self.myPrint(LOG_ERROR, 'stopTrading', info)
        self.health = False

    #----------------------------------------------------------------------
    def onInit(self):
        """初始化策略（必须由用户继承实现）"""
        self.myPrint(LOG_INFO, 'onInit', '海龟交易法则策略开始初始化。')

        # 初始化合约信息
        #self.contracts = self.hgDbEngine.getAllContract()
        initData = self.hgDbEngine.loadDayBar(self.vtSymbol, self.cacheDays)
        if len(initData) != self.cacheDays:
            self.myPrint(LOG_ERROR, 'onInit', u'【ERROR】【hg】%s 合约初始化数据不足，需要长度为%d ,实际长度为 %d' % (self.vtSymbol, self.longWindow, len(initData)))
            self.stopTrading()
            return

        for bar in initData:
            self.am.updateBar(bar)

        shortWindowHighBreak = self.am.high[-self.shortWindow:].max()
        shortWindowLowBreak = self.am.low[-self.shortWindow:].min()

        middleWindowHighBreak = self.am.high[-self.middleWindow:].max()
        middleWindowLowBreak = self.am.low[-self.middleWindow:].min()

        longWindowHighBreak = self.am.high[-self.longWindow:].max()
        longWindowLowBreak = self.am.low[-self.longWindow:].min()


        atr = self.am.atr(20, False)
        # 如果记录过atr，则使用开仓时候的 atr
        if self.atr != -1 and self.cell_num > 0:
            atr = self.atr



        unit =  int(self.instanceAccount * 0.01 / (atr * self.contracts[self.vtSymbol]['size']))
        self.monitor = {
            'shortWindowHighBreak': shortWindowHighBreak,
            'shortWindowLowBreak': shortWindowLowBreak,
            'middleWindowHighBreak': middleWindowHighBreak,
            'middleWindowLowBreak': middleWindowLowBreak,
            'longWindowHighBreak': longWindowHighBreak,
            'longWindowLowBreak': longWindowLowBreak,
            'atr': atr,
            'unit': unit
        }

        # 增加一个校验，但凡有一个为零，认为初始化不成功，停止交易
        if 0 in [shortWindowHighBreak, shortWindowLowBreak, middleWindowHighBreak
            , middleWindowLowBreak, longWindowHighBreak, longWindowLowBreak, atr, unit]:
            self.myPrint(LOG_ERROR, 'onInit', u'%s合约初始化失败，信息为%s' % (self.vtSymbol, self.monitor))
            self.stopTrading()

        self.myPrint(LOG_INFO, 'onInit', u'%s合约初始化，信息为%s' % (self.vtSymbol,self.monitor))

        # 报单查询测试
        gateway = self.ctaEngine.mainEngine.getGateway('CTP')

        # 拿到本次交易的 sessionID 和 frontID，可以抽象到上层
        self.sessionID = gateway.tdApi.sessionID  # 本地交易
        self.frontID = gateway.tdApi.frontID  # 本次交易的

        self.myPrint(LOG_INFO, 'onInit', u'初始化，sessionID = %s; frontID = %s' % (self.sessionID, self.frontID))
        self.myPrint(LOG_INFO, 'onInit', '海龟交易法则策略初始化完成。')
        # TODO 每次重新登录如果有历史报单，对历史报单的处理


        # 前几个函数测试使用
        #self.health = False

        #self.myPrint(LOG_INFO, 'onInit', '未测试，先关闭真正的交易。')
        #self.stopTrading()
        #gateway.tdApi.qryTest()

    # ----------------------------------------------------------------------
    # 生成图像的封装函数
    def genImg(self, size, closePrice):
        # 每月的图片放在一个文件夹
        # 文件用时间命名
        strTime = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        strMonth = strTime[0:6]
        filePath = self.imgHtmlRootDir + 'img/' + strMonth
        if not os.path.exists(filePath):
            os.makedirs(filePath)
        fileNamePath = filePath + '/' + strTime + '.jpg'
        title = self.vtSymbol + " " + strTime

        s_h, s_l = self.am.donchian(self.shortWindow, array=True)
        m_h, m_l = self.am.donchian(self.middleWindow, array=True)
        l_h, l_l = self.am.donchian(self.longWindow, array=True)

        s_h = s_h[-size:]
        s_l = s_l[-size:]
        m_h = m_h[-size:]
        m_l = m_l[-size:]
        l_h = l_h[-size:]
        l_l = l_l[-size:]
        close = self.am.close[-size:]

        s_h = np.hstack((s_h, s_h[-1]))
        s_l = np.hstack((s_l, s_l[-1]))
        m_h = np.hstack((m_h, m_h[-1]))
        m_l = np.hstack((m_l, m_l[-1]))
        l_h = np.hstack((l_h, l_h[-1]))
        l_l = np.hstack((l_l, l_l[-1]))
        close = np.hstack((close, closePrice))


        saveImg(self,fileNamePath, title,s_h, s_l, m_h, m_l, l_h, l_l, close, size+1)



    # ----------------------------------------------------------------------


    #----------------------------------------------------------------------
    def onStart(self):
        """启动策略（必须由用户继承实现）"""
        self.myPrint(LOG_INFO, 'onStart', u'海龟交易法则策略启动')
        self.putEvent()
    
    #----------------------------------------------------------------------
    def onStop(self):
        """停止策略（必须由用户继承实现）"""
        self.myPrint(LOG_INFO, 'onStop', u'海龟交易法则策略启动')
        self.putEvent()
        
    #----------------------------------------------------------------------
    def onTick(self, tick):
        """收到行情TICK推送（必须由用户继承实现）"""

        self.bg.updateTick(tick)
        # TODO 将来可以添加校验，校验是否订阅的合约都有信号
    #----------------------------------------------------------------------
    def onBar(self, bar):
        """收到Bar推送（必须由用户继承实现）"""
        # TODO 对涨跌停的处理
        # TODO 异常值的处理
        # TODO 如果委托了，一直不成交怎么办
        #strategy.trading = False
        #strategy.inited = False


        print(bar.__dict__)

        self.myPrint(LOG_DEBUG, 'onBar', '进入onBar.')
        self.myPrint(LOG_DEBUG, 'onBar', bar.__dict__)



        if not self.trading :
            self.myPrint(LOG_INFO, 'onBar', 'self.trading is false')
            return

        if not self.health:
            self.myPrint(LOG_ERROR, 'onBar', 'self.health is false')
            return

        # 是否生成图像处理
        if self.bGenImg:
            # 生成图像
            self.genImg(20, bar.close)
            # 生成展示html
            genHtmls(self.imgHtmlRootDir)
            self.bGenImg = False


        #self.buy(3750, 1)

        #return
        # 测试
        #self.monitor['middleWindowHighBreak'] = 3575
        # 测试结束

        vtSymbol = bar.vtSymbol

        # 如果发现有合约初始化未完成，直接返回
        if not self.am.inited:
            self.myPrint(LOG_ERROR, 'onBar', u'【ERROR】【hg】合约未能正常初始化' % (vtSymbol))
            return

        # 账户金额有限，如果加仓单位还不到1，则直接返回
        if self.monitor['unit'] == 0:
            self.myPrint(LOG_ERROR, 'onBar', u'self.monitor[unit] == 0')
            return



        # 5、如果存在不问稳定的订单状态直接返回
        if not self.is_all_cell_stable():
            # self.printCells("not self.is_all_cell_stable()")
            self.myPrint(LOG_INFO, 'onBar', "not self.is_all_cell_stable()")
            return

        # TODO 这里可以优化， hand_cell 和 saveIntoDB 重复了。
        # 6、如果真实持仓未达到目标状态，下单，更新数据库，并返回
        if not self.is_all_cell_get_target_unit():
            self.myPrint(LOG_IMPORTANT, 'onBar', "当前订单稳定了，但是 没有达到目标仓位，则继续交易。")

            for hgcell in self.hgCellList:
                hgcell.hand_cell(self, bar.close)

            # 记录在数据库中
            self.hgDbEngine.saveIntoDB(self)
            return


        if not self.calCellNumAndTotalRealUnit() and len(self.hgCellList) > 0:
            self.myPrint(LOG_ERROR, 'onBar', 'not self.calCellNumAndTotalRealUnit() and len(self.hgCellList) > 0')
            self.stopTrading()
            return



        if self.cell_num >= 1:
            # 更新加仓价格
            cell = self.hgCellList[self.cell_num - 1]  # 取最后一个持仓
            if cell.is_all_order_stable(self) and cell.real_unit == cell.target_unit:
                # 订单都稳定了，并且达到了目标持仓，更新加仓价格
                if cell.open_direction == 'b':
                    self.plan_add_price = cell.real_in_price + (cell.N / 2)
                if cell.open_direction == 's':
                    self.plan_add_price = cell.real_in_price - (cell.N / 2)
            else:
                self.myPrint(LOG_ERROR, 'onBar', '不应该出现这种情况，存在订单不稳定或者 目标真实持仓不一致的情况')
                self.stopTrading()
                return

            # 更新退出价格信息
            self.update_plan_stop_price()

            # 进行一次数据库写入
            self.hgDbEngine.saveIntoDB(self)


        # 当前持仓大于最大持仓要求
        if self.cell_num >= self.max_cell_num:
            self.myPrint(LOG_INFO, 'onBar', u'已达到最大持仓 %d / %d' % (self.cell_num, self.max_cell_num))
            return

        # 单方向是否达到了最大值
        tmpInstanceTotalCellNum = self.hgDbEngine.getInstanceTotalCellNum(self.instanceName, self.s_or_b)
        if self.s_or_b and tmpInstanceTotalCellNum >= self.MaxInstanceTotalCellNum:
            self.myPrint(LOG_INFO, 'onBar', "tmpInstanceTotalCellNum >= self.MaxInstanceTotalCellNum ,"
                                            "the value is %d / %d " % (
                tmpInstanceTotalCellNum, self.MaxInstanceTotalCellNum))
            return


        # TODO 当前持仓是否满足 6 规则
        # TODO 撤销所有的合约

        # cell 是否发生变化，如果有发生变化，就不再进行下面的逻辑
        isCellChange = False

        # 如果未持有合约，判断是否有突破
        if self.cell_num == 0:

            if bar.close > self.monitor['middleWindowHighBreak']:
                # 有向上突破
                isCellChange = True
                self.s_or_b = 'b'
                a_cell = HgCell(vtSymbol, self.s_or_b, self.monitor['unit'],
                                self.monitor['middleWindowHighBreak'], BREAK_MIDDLEWINDOW, self.monitor['atr'])

                self.myPrint(LOG_IMPORTANT, 'onBar', "发现向上突破，开仓信息如下"
                                                     "vtSymbol = %s, "
                                                     "s_or_b = %s, "
                                                     "unit = %d, "
                                                     "middleWindowHighBreak = %d, "
                                                     "type = %s, "
                                                     "atr = %d " % (vtSymbol, self.s_or_b, self.monitor['unit'],
                                                                    self.monitor['middleWindowHighBreak'], BREAK_MIDDLEWINDOW, self.monitor['atr']))
                self.addCell(a_cell)


            elif bar.close < self.monitor['middleWindowLowBreak']:
                # 有向下突破
                isCellChange = True
                self.s_or_b = 's'
                a_cell = HgCell(vtSymbol, self.s_or_b, self.monitor['unit'],
                                self.monitor['middleWindowLowBreak'], BREAK_MIDDLEWINDOW, self.monitor['atr'])
                self.myPrint(LOG_IMPORTANT, 'onBar', "发现向下突破，开仓信息如下"
                                                     "vtSymbol = %s, "
                                                     "s_or_b = %s, "
                                                     "unit = %d, "
                                                     "middleWindowLowBreak = %d, "
                                                     "type = %s, "
                                                     "atr = %d " % (vtSymbol, self.s_or_b, self.monitor['unit'],
                                                                    self.monitor['middleWindowLowBreak'],
                                                                    BREAK_MIDDLEWINDOW, self.monitor['atr']))
                self.addCell(a_cell)

            # 初始持仓为0，并出现成交，说明开仓了，记录开仓时候的art
            if isCellChange == True:
                self.atr = self.monitor['atr']
                self.myPrint(LOG_IMPORTANT, 'onBar', "开仓atr = %d" % (self.atr))
                #  TODO 清仓完毕后需要重置一些属性，尤其是ATR

        if self.cell_num == 0:
            # 下面的操作只有有持仓时才操作
            self.myPrint(LOG_DEBUG, 'onBar', "self.cell_num == 0")
            return


        if not isCellChange:
            # 如果持有合约，判断是否触及退出
            # 10日线退出法则, 多头头寸，价格低于最近10日最低点时退出
            if self.s_or_b == 'b' and bar.close < self.monitor['shortWindowLowBreak']:
                self.myPrint(LOG_IMPORTANT, 'onBar', "10日线退出法则, 多头头寸，价格低于最近10日最低点时退出。"
                                                     "s_or_b = %s, "
                                                     "bar.close = %d,"
                                                     "shortWindowLowBreak = %d " % (self.s_or_b, bar.close, self.monitor['shortWindowLowBreak']))
                self.quitAllOrders()
                isCellChange = True
            # 10日线退出法则, 空头头寸，价格高于最近10日最高点时退出
            if self.s_or_b == 's' and bar.close > self.monitor['shortWindowHighBreak']:
                self.myPrint(LOG_IMPORTANT, 'onBar', "10日线退出法则,空头头寸，价格高于最近10日最高点时退出。"
                                                     "s_or_b = %s, "
                                                     "bar.close = %d,"
                                                     "shortWindowHighBreak = %d " % (
                             self.s_or_b, bar.close, self.monitor['shortWindowHighBreak']))
                self.quitAllOrders()
                isCellChange = True


        # 如果持有合约，判断是否触及止损
        # TODO 涨跌停的处理
        if not isCellChange:
            isCellChange = self.check_stop_condition(bar.close)
            if isCellChange:
                self.myPrint(LOG_IMPORTANT, 'onBar', "触及止损。")

        # 如果持有合约，判断是否触及加仓，同时判断仓位是否超过限制
        if not isCellChange:
            isCellChange = self.check_add_condition(bar.close)
            if isCellChange:
                self.myPrint(LOG_IMPORTANT, 'onBar', "触及加仓。")

        # 处理每个cell
        if isCellChange:
            self.myPrint(LOG_IMPORTANT, 'onBar', "处理cell变动，并记录在数据库中。")

            for hgcell in self.hgCellList:
                hgcell.hand_cell(self, bar.close)

            # 记录在数据库中
            self.hgDbEngine.saveIntoDB(self)



    # 判断是否所有cell的订单都是稳定的
    def is_all_cell_stable(self):
        ret = True
        for hgcell in self.hgCellList:
            ret = hgcell.is_all_order_stable(self) and ret
        return ret

    # 判断是否所有cell都达到目标订单了
    def is_all_cell_get_target_unit(self):
        ret = True
        for hgcell in self.hgCellList:
            ret = (hgcell.target_unit == hgcell.real_unit) and ret
        return ret


    #----------------------------------------------------------------------
    def onOrder(self, order):
        """收到委托变化推送（必须由用户继承实现）"""
        # 对于无需做细粒度委托控制的策略，可以忽略onOrder
        self.myPrint(LOG_DEBUG, 'onOrder', 'IN')
        self.myPrint(LOG_INFO, 'onOrder', str(order.__dict__).decode('unicode-escape'))
        self.printCells("*" * 20 + " in onorder")

        self.orderList.append(order)

        # onOrder  -133888101.1.CTP.4
        # 更新 cell 中 in_orderId_dict out_orderId_dict 中的订单信息

        is_update = False
        for hgcell in self.hgCellList:
            is_update = (hgcell.updateOrder(order) or is_update)

        if is_update:
            self.myPrint(LOG_IMPORTANT, 'onOrder', '成功更新 cell orders。')
        else:
            self.myPrint(LOG_ERROR, 'onOrder', '更新 cell orders 失败。')
            self.stopTrading()

        # TODO 更新持仓数量信息


        # 记录在数据库中
        self.hgDbEngine.saveIntoDB(self)
        self.printCells("*" * 20 + " out onorder")


    
    #----------------------------------------------------------------------
    def onTrade(self, trade):
        """收到成交推送（必须由用户继承实现）"""
        # 对于无需做细粒度委托控制的策略，可以忽略onOrder
        # 打印过trader信息，里面没有session信息
        self.myPrint(LOG_DEBUG, 'onTrade', '')
        self.myPrint(LOG_INFO, 'onTrade', str(trade.__dict__).decode('unicode-escape'))
        self.tradeList.append(trade)

        self.printCells("*"*20 + " in onTrade")
        is_update = False
        orderid = trade.vtOrderID
        # 如果 sessionID 和 frontID 维护了
        if self.sessionID is not None and self.frontID is not None:
            orderid = self.sessionID + '.' + self.frontID + '.' + orderid

        # 把 Trade 更新到 cell 中， 更新完之后，会自动计算当前cell持仓 和 真实价格
        for hgcell in self.hgCellList:
            is_update = (hgcell.updateTrade(orderid, trade) or is_update)

        if is_update:
            self.myPrint(LOG_IMPORTANT, 'onTrade', '成功更新 cell trades。')
        else:
            self.myPrint(LOG_ERROR, 'onTrade', '更新 cell trades 失败。')
            self.stopTrading()

        # 接收到成交之后打印一下自己
        for hgcell in self.hgCellList:
            hgcell.print_self()
        # 记录在数据库中
        self.hgDbEngine.saveIntoDB(self)

        # TODO 发送下报告，这里报告中有些字段还没更新，其实不是最佳时机
        self.myPrint(LOG_INFO, 'onTrade', '发送报告: ' + self.instanceName)
        self.hgReport.sendReport(self.instanceName, self.pickleItemDict)

        self.printCells("*" * 20 + " out onTrade")
    
    #----------------------------------------------------------------------
    def onStopOrder(self, so):
        """停止单推送"""
        self.myPrint("onStopOrder", so.__dict__)
        pass

    # ----------------------------------------------------------------------
    def myPrint(self, funName, date):
        print("%s strategyHg funName = %s ,  date = %s " % (datetime.now(), funName, date))

    # 自定义日志级别输出函数
    def myPrint(self, level, funName, data):

        info = ""
        if level == LOG_INFO:
            info = '【INFO】'
        if level == LOG_DEBUG:
            info = '【DEBUG】'
        if level == LOG_IMPORTANT:
            info = '【IMPORTANT】'
        if level == LOG_ERROR:
            info = '【ERROR】'

        # 添加策略实例标识
        info = info + self.instanceName + ' ' + self.instanceId + ' '
        if level >= self.logLevel:
            info = info + " %s strategyHg funName = %s ,  data = %s " % (datetime.now(), funName, data)
            #print(info) # 输出在文件中
            self.writeCtaLog(info) # 输出在数据库中

    # 计算真实cell持仓,和 总单位持仓，调用前提是订单已经稳定，订单列表肯定不能为空
    def calCellNumAndTotalRealUnit(self):

        self.myPrint(LOG_DEBUG, 'calCellNumAndTotalRealUnit', 'IN')
        positionCellNum = 0 # 处于已持仓的cell数量
        totalRealUnit = 0

        ret = True # 返回默认为正常
        # 倒叙遍历cell
        for cell in list(reversed(self.hgCellList)):
            real = cell.real_unit
            target = cell.target_unit
            totalRealUnit = totalRealUnit + real

            # 进入此函数，cell 一定经过了执行 hand_cell in_orderId_dict 不可能为空
            if not cell.in_orderId_dict:
                self.myPrint(LOG_ERROR, 'calRealCellAndUnitNum', 'not cell.in_orderId_dict')
                self.stopTrading()
                ret = False

            # 订单处于稳定状态，只有一种情况 target == real
            if target > 0 and target == real:
                positionCellNum = positionCellNum + 1
            elif target == 0 and target == real:
                self.myPrint(LOG_IMPORTANT, 'calRealCellAndUnitNum', 'cell 清空完毕,将cell删除。')
                self.hgCellList.remove(cell)
            else:
                # 其他情况均为不正常状态
                self.myPrint(LOG_ERROR, 'calRealCellAndUnitNum', '其他情况均为不正常状态'
                                                                 'target = %d, real = %d ' % (target, real))
                self.stopTrading()
                ret = False

        self.cell_num = len(self.hgCellList) # cell数量
        self.totalRealUnit = totalRealUnit # 真实总持仓情况

        return ret





    # ----------------------------------------------------------------------
    def addCell(self, cell):
        # 增加一个持仓单位
        # 当前持仓大于最大持仓要求
        if self.cell_num >= self.max_cell_num:
            self.myPrint(LOG_IMPORTANT, 'addCell', u'已达到最大持仓 %d / %d' % (self.cell_num, self.max_cell_num))
            return

        # 单方向是否达到了最大值
        tmpInstanceTotalCellNum = self.hgDbEngine.getInstanceTotalCellNum(self.instanceName, self.s_or_b)
        if tmpInstanceTotalCellNum >= self.MaxInstanceTotalCellNum:
            self.myPrint(LOG_IMPORTANT, 'addCell', "tmpInstanceTotalCellNum >= self.MaxInstanceTotalCellNum ,"
                                            "the value is %d / %d " % (
                tmpInstanceTotalCellNum, self.MaxInstanceTotalCellNum))
            return

        self.cell_num = self.cell_num + 1 # 持仓计数加1
        self.hgCellList.append(cell) # 添加在持仓列表中


    # ----------------------------------------------------------------------
    def quitAllOrders(self):
        # 设定所有持仓的目标仓位为0
        for cell in self.hgCellList:
            cell.target_unit = 0

    def check_stop_condition(self, price):
        """ 检验是否触发止损条件"""
        ret = False # 默认返回True

        if self.s_or_b == 'b':
            # 多头持仓
            for cell in self.hgCellList:
                if cell.plan_stop_price is not None:
                    if price <= cell.plan_stop_price:
                        # 当前价格小于等于止损价格时，设定目标仓位为0
                        cell.target_unit = 0
                        ret = True
                else:
                    self.myPrint(LOG_ERROR, 'check_stop_condition', "check_stop_condition,cell.plan_stop_price is None")
        if self.s_or_b == 's':
            # 空头持仓
            for cell in self.hgCellList:
                if cell.plan_stop_price is not None:
                    if price >= cell.plan_stop_price:
                        # 当前价格大于等于止损价格时，设定目标仓位为0
                        cell.target_unit = 0
                        ret = True
                else:
                    self.myPrint(LOG_ERROR, 'check_stop_condition', "check_stop_condition,cell.plan_stop_price is None")

        return ret

    # ----------------------------------------------------------------------
    def check_add_condition(self, price):
        """检验是否触及加仓条件"""
        # 之前已有校验，能进入这个函数说明未达到最大持仓，单方向也满足要求
        ret = False
        cell = self.hgCellList[len(self.hgCellList) - 1] # 取最后一个持仓
        if self.s_or_b == 'b':
            # 多头持仓，并且当前价格大约加仓价
            if price >= self.plan_add_price:
                a_cell = HgCell(self.vtSymbol, self.s_or_b, self.monitor['unit'],
                                self.plan_add_price, HALF_N, cell.N)

                self.myPrint(LOG_IMPORTANT, 'check_add_condition', "触发加仓，信息如下"
                                                     "vtSymbol = %s, "
                                                     "s_or_b = %s, "
                                                     "unit = %d, "
                                                     "plan_add_price = %d, "
                                                     "type = %s, "
                                                     "N = %d " % (self.vtSymbol, self.s_or_b, self.monitor['unit'],
                                                                    self.plan_add_price,
                                                                  HALF_N, cell.N))


                self.addCell(a_cell)
                ret = True

        if self.s_or_b == 's':
            # 空头持仓，并且当前价格小于加仓价
            if price <= self.plan_add_price:
                a_cell = HgCell(self.vtSymbol, self.s_or_b, self.monitor['unit'],
                                self.plan_add_price, HALF_N, cell.N)

                self.myPrint(LOG_IMPORTANT, 'check_add_condition', "触发加仓，信息如下"
                                                                   "vtSymbol = %s, "
                                                                   "s_or_b = %s, "
                                                                   "unit = %d, "
                                                                   "plan_add_price = %d, "
                                                                   "type = %s, "
                                                                   "N = %d " % (
                             self.vtSymbol, self.s_or_b, self.monitor['unit'],
                             self.plan_add_price,
                             HALF_N, cell.N))

                self.addCell(a_cell)
                ret = True

        return ret



    # ----------------------------------------------------------------------
    # 更新 self.plan_stop_price
    # 从最后一个仓位开始，计算每个仓位的退出值
    def update_plan_stop_price(self):

        last_real_in_price = None # 记录上一个价格
        last_plan_stop_price = None # 记录上一个止损价格

        for cell in list(reversed(self.hgCellList)):

            self.real_unit = 0  # 真实持仓单位
            self.real_in_price = 0  # 平均入场价格

            if cell.real_unit == 0 or cell.real_in_price == 0:
                self.myPrint(LOG_ERROR, 'update_plan_stop_price', "cell.real_unit == 0 or cell.real_in_price == 0")
                self.stopTrading()
                break


            tmp_plan_stop_price = None
            if self.s_or_b == 'b':
                tmp_plan_stop_price = cell.real_in_price - 2 * cell.N
            elif self.s_or_b == 's':
                tmp_plan_stop_price = cell.real_in_price + 2 * cell.N

            # 如果处理的是最后一个cell，直接更新
            if last_real_in_price == None:
                cell.plan_stop_price = tmp_plan_stop_price
            elif 0.8 < float(last_real_in_price)/cell.real_in_price < 1.2:
                cell.plan_stop_price = last_plan_stop_price
            else:
                cell.plan_stop_price = tmp_plan_stop_price

            last_real_in_price = cell.real_in_price
            last_plan_stop_price = cell.plan_stop_price

    # 获取当前实例s_or_b 方向的总持仓数
    """
    def getInstanceTotalCellNum(self):

        TotalCellNum = 0
        d = [
            {'$match': {"instanceName": self.instanceName ,"s_or_b" : self.s_or_b}},
            {'$group': {'_id': "$instanceName", 'total': {'$sum': "$cell_num"}}}
        ]
        ret = mydb.dbAggregateSum(MAIN_DB_NAME, TB_HG_MAIN, d)

        for tmp in ret:
            TotalCellNum = int(tmp['total'])
            break

        print("instanceName:%s %s 方向的总持仓为: %d" % (self.instanceName, self.s_or_b, TotalCellNum))
        return TotalCellNum
    """

    def printCells(self,info=""):
        print(info)
        print("start printself")
        gt200 = {key: value for key, value in self.__dict__.items() if key not in ['contracts','orderList','tradeList','hgCellList']}
        print(str(gt200).decode('unicode-escape'))
        print("end printsefl")
        print("start printcells")
        for cell in self.hgCellList:
            cell.print_self()
        print("end printcells")





                        # ----------------------------------------------------------------------



#############################################################




# 海龟类继承基本处理类，增加海龟法则比较的属性
class HgCell(Cell):

    def __init__(self, vtSymbol, direction, target_unit, plan_in_price, in_condition, N):
        """Constructor"""
        super(HgCell, self).__init__( vtSymbol, direction, target_unit, plan_in_price, in_condition)

        self.N = N # 本次交易的N
        self.plan_stop_price = None # 止损价格
        #self.plan_add_price = None  # 加仓价格



#hg = HgCell('strategy', 'vtSymbol', 'direction', 'target_unit', 'plan_in_price', 'in_condition')
#print(hg.__dict__)






