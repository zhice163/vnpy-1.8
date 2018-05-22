# encoding: UTF-8

"""
海龟交易法则
1、最终的成交价在onTrade里面
2、onOrder里面有sessionID 和 frontID，onTrade 里面没有

问题
1、分批成交时，onOrder ontrade是怎么样的呢

一些思路
1、为了保证数据的准确性


# 头寸基本规则
1、单个市场最多4个头寸
2、高度关联的多个市场6个头寸
3、松散关联的多个市场10个头寸
4、单个方向（多头或空头）12个头寸

"""

from __future__ import division

from datetime import datetime

from vnpy.trader.app.ctaStrategy.ctaTemplate import (CtaTemplate,
                                                     BarGenerator,
                                                     ArrayManager)
from vnpy.trader.vtConstant import (DIRECTION_LONG, DIRECTION_SHORT,
                                    STATUS_NOTTRADED, STATUS_PARTTRADED, STATUS_UNKNOWN,
                                    PRICETYPE_MARKETPRICE)
from vnpy.trader.vtZcEngine import ctaDbEngine
from vnpy.trader.vtZcObject import mydb, Cell

try:
    import cPickle as pickle    #python 2
except ImportError as e:
    import pickle


BREAK_MIDDLEWINDOW = '20日突破'
HALF_N = '0.5N'


# 海龟策略用到的一些表名和数据库名
MAIN_DB_NAME = 'VnTrader_Main_Db'
TB_HG_MAIN = "TB_HG_MAIN"


########################################################################
# 每个实例监控一个品种，通过数据库进行一个交易实例的组合，一个交易实例包含多个品种的交易
class HgStrategy(CtaTemplate):
    """双指数均线策略Demo"""
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

        # 每次启动要重建的参数
        self.bg = BarGenerator(self.onBar)
        self.cacheDays = max(self.longWindow, (2 * self.middleWindow) + 1)
        self.am = ArrayManager(self.cacheDays)
        self.myDb = mydb  # 数据库引擎
        self.ctadbEngine = ctaDbEngine(mydb)  # cta 数据库操作的一些封装
        self.monitor = {}  # 合约当天的 10日线高低、20日线高低、55日线和ART信息
        self.contracts = {}  # 最新的合约信息
        self.sessionID = None  # 本地交易
        self.frontID = None  # 本次交易的
        # self.sessionid = uuid.uuid1() # 本次唯一id


        # 【重要】所有要pickle存储的数据都要记录在变量中
        self.pickleItemList = ["orderList",
                               "tradeList",
                               "hgCellList",
                               "plan_add_price",
                               "atr",
                               "cell_num",
                               "s_or_b",
                               "offsetProfit",
                               "floatProfit",
                               "max_cell_num"]

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



        # TODO通过pickle进行数据恢复
        self.recoveryFromDb()

        # 更新hgCellList 每个cell的策略引用
        # 原因是：hgCellList 是从数据库中恢复的，里面的引用有可能已经失效，所以更新为最新的

        for hgcell in self.hgCellList:
            hgcell.strategy = self


        # 海龟交易主力合约，配置时 symbol 配置的是品种名称，进行翻译。
        ret = self.ctadbEngine.getDominantByProductID(self.productID)

        if ret is not None and self.vtSymbol != "" and self.vtSymbol != ret:
            self.setStop("【重要】，需要手工移仓")
            self.myPrint("__init__","ret is not None and self.vtSymbol != ret, vtSymbol = %s, ret = %s", (self.vtSymbol,ret))
            # TODO 目前出现移仓情况需要手动处理

        if ret is not None and self.vtSymbol == "" :
            self.vtSymbol = ret


    # 将一些数据保存在数据库中
    # 目前在三个地方调用： 每次 onbar onOrder onTrading
    def saveIntoDB(self):

        ret_data = {}
        d = self.__dict__

        ret_data['instanceName'] = self.instanceName
        ret_data['instanceId'] = self.instanceId

        for key in self.pickleItemList:
            # 对于字典和列表类型的变量，使用pickle进行存储
            if isinstance(d[key], dict) or isinstance(d[key], list):
                pickleData = pickle.dumps(d[key])
                ret_data[key] = pickleData
            else:
                ret_data[key] = d[key]
        # 写入数据库
        flt = {'instanceName':self.instanceName, 'instanceId':self.instanceId}
        mydb.dbUpdate(MAIN_DB_NAME, TB_HG_MAIN, ret_data, flt, upsert=True)

    # 根据数据库记录恢复数据
    def recoveryFromDb(self):

        flt = {'instanceName': self.instanceName, 'instanceId': self.instanceId}
        ret = mydb.dbQuery(MAIN_DB_NAME, TB_HG_MAIN, flt)

        # 数据库没有查到记录，正常返回
        if ret is None or ret.count() == 0:
            return

        if ret.count() == 1:

            theData = ret[0]
            # 进行数据恢复
            d = self.__dict__
            for key in self.pickleItemList:
                # 对于字典和列表类型的变量，使用pickle进行存储
                if isinstance(d[key], dict) or isinstance(d[key], list):
                    pickleData = pickle.loads(str(theData[key]))
                    d[key] = pickleData
                else:
                    d[key] = theData[key]

        else:
            self.stopTrading()
            self.myPrint("recoveryFromDb",'【ERROR】返回多条记录，instanceName = %s, instanceId = %s' , (self.instanceName, self.instanceId))

    def stopTrading(self, info = ""):
        self.myPrint("stopTrading", info)
        self.trading = False

    #----------------------------------------------------------------------
    def onInit(self):
        """初始化策略（必须由用户继承实现）"""
        self.writeCtaLog(u'海龟交易法则策略初始化')

        # 初始化合约信息
        self.contracts = self.ctadbEngine.getAllContract()
        initData = self.ctadbEngine.loadDayBar(self.vtSymbol, self.cacheDays)
        if len(initData) != self.cacheDays:
            self.writeCtaLog(u'【ERROR】【hg】%s 合约初始化数据不足，需要长度为%d ,实际长度为 %d' % (self.vtSymbol, self.longWindow, len(initData)))
            # TODO 增加对未正常初始化数据的整理

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
        if self.atr != -1:
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

        self.writeCtaLog(u'【hg】%s合约初始化，信息为%s' % (self.vtSymbol,self.monitor))

        # 报单查询测试
        gateway = self.ctaEngine.mainEngine.getGateway('CTP')

        # 拿到本次交易的 sessionID 和 frontID，可以抽象到上层
        self.sessionID = gateway.tdApi.sessionID  # 本地交易
        self.frontID = gateway.tdApi.frontID  # 本次交易的

        self.writeCtaLog(u'【INFO】初始化，sessionID = %s; frontID = %s' % (self.sessionID, self.frontID))

        # TODO 每次重新登录如果有历史报单，对历史报单的处理
        #gateway.tdApi.qryTest()

        
    #----------------------------------------------------------------------
    def onStart(self):
        """启动策略（必须由用户继承实现）"""
        self.writeCtaLog(u'海龟交易法则策略启动')
        self.putEvent()
    
    #----------------------------------------------------------------------
    def onStop(self):
        """停止策略（必须由用户继承实现）"""
        self.writeCtaLog(u'海龟交易法则策略停止')
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
        #strategy.trading = False
        #strategy.inited = False

        self.myPrint("onBar", bar.__dict__)
        self.printCells("*" * 20 + " in onbar")

        if not self.trading:
            self.myPrint("onBar", 'self.trading is false')
            return

        #self.buy(3750, 1)

        #return
        # 测试
        #self.monitor['middleWindowHighBreak'] = 3575
        # 测试结束

        vtSymbol = bar.vtSymbol

        # 如果发现有合约初始化未完成，直接返回
        if not self.am.inited:
            self.writeCtaLog(u'【ERROR】【hg】合约未能正常初始化' % (vtSymbol))
            return

        # 账户金额有限，如果加仓单位还不到1，则直接返回
        if self.monitor['unit'] == 0:
            return

        # 当前持仓大于最大持仓要求
        if self.cell_num >= self.max_cell_num:
            print("已达到最大持仓")
            return

        # 只有所有订单文档才继续
        if not self.is_all_cell_stable():
            self.printCells("not self.is_all_cell_stable()")
            return

        # TODO 当前持仓是否满足 6 12 规则

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
                self.addCell(a_cell)

            elif bar.close < self.monitor['middleWindowLowBreak']:
                # 有向下突破
                isCellChange = True
                self.s_or_b = 's'
                a_cell = HgCell(vtSymbol, self.s_or_b, self.monitor['unit'],
                                self.monitor['middleWindowLowBreak'], BREAK_MIDDLEWINDOW, self.monitor['atr'])
                self.addCell(a_cell)

            # 初始持仓为0，并出现成交，说明开仓了，记录开仓时候的art
            if isCellChange == True:
                self.atr = self.monitor['atr']
                #  TODO 清仓完毕后需要重置一些属性，尤其是ATR

        if self.cell_num == 0:
            # 下面的操作只有有持仓时才操作
            print("on bar self.cell_num == 0")
            return

        # TODO 判断订单稳定后再继续操作
        # TODO 判断是否达到目标持仓再操作

        if not isCellChange:
            # 如果持有合约，判断是否触及退出
            # 10日线退出法则, 多头头寸，价格低于最近10日最低点时退出
            if self.s_or_b == 'b' and bar.close < self.monitor['shortWindowLowBreak']:
                self.quitAllOrders()
                isCellChange = True
            # 10日线退出法则, 空头头寸，价格高于最近10日最高点时退出
            if self.s_or_b == 's' and bar.close > self.monitor['shortWindowHighBreak']:
                self.quitAllOrders()
                isCellChange = True


        # 如果持有合约，判断是否触及止损
        # TODO 涨跌停的处理
        if not isCellChange:
            isCellChange = self.check_stop_condition(bar.close)

        # 如果持有合约，判断是否触及加仓，同时判断仓位是否超过限制
        if not isCellChange:
            isCellChange = self.check_add_condition(bar.close)

        # 处理每个cell
        if isCellChange:
            for hgcell in self.hgCellList:
                hgcell.hand_cell(self, bar.close)

            # 记录在数据库中
            self.saveIntoDB()

        #TODO 增加离场条件的记录？

        self.printCells("*" * 20 + " out onbar")


    # 判断是否所有cell的订单都是稳定的
    def is_all_cell_stable(self):
        ret = True
        for hgcell in self.hgCellList:
            ret = hgcell.is_all_order_stable() and ret
        return ret


    #----------------------------------------------------------------------
    def onOrder(self, order):
        """收到委托变化推送（必须由用户继承实现）"""
        # 对于无需做细粒度委托控制的策略，可以忽略onOrder
        self.myPrint("onOrder", str(order.__dict__).decode('unicode-escape'))
        self.printCells("*" * 20 + " in onorder")

        self.orderList.append(order)

        # onOrder  -133888101.1.CTP.4
        # 更新 cell 中 in_orderId_dict out_orderId_dict 中的订单信息

        is_update = False
        for hgcell in self.hgCellList:
            is_update = (hgcell.updateOrder(order) or is_update)

        if is_update:
            self.myPrint("onOrder", 'order 更新成功')
        else:
            self.myPrint("onOrder", 'order 更新失败')

        # 记录在数据库中
        self.saveIntoDB()
        self.printCells("*" * 20 + " out onorder")
        # TODO

    
    #----------------------------------------------------------------------
    def onTrade(self, trade):
        """收到成交推送（必须由用户继承实现）"""
        # 对于无需做细粒度委托控制的策略，可以忽略onOrder
        # 打印过trader信息，里面没有session信息
        self.myPrint("onTrade", str(trade.__dict__).decode('unicode-escape'))
        self.tradeList.append(trade)

        self.printCells("*"*20 + " in onTrade")
        is_update = False
        orderid = trade.vtOrderID
        # 如果 sessionID 和 frontID 维护了
        if self.sessionID is not None and self.frontID is not None:
            orderid = self.sessionID + '.' + self.frontID + '.' + orderid

        # 把 Trade 更新到 cell 中
        for hgcell in self.hgCellList:
            is_update = (hgcell.updateTrade(orderid, trade) or is_update)

        if is_update:
            self.myPrint("onTrade", 'trade 更新成功')
        else:
            self.myPrint("onTrade", 'trade 更新失败')

        # 更新加仓价格
        if is_update and self.cell_num >= 1 :
            cell = self.hgCellList[self.cell_num - 1]  # 取最后一个持仓
            if cell.is_all_order_stable() and cell.real_unit == cell.target_unit:
                # 订单都稳定了，并且达到了目标持仓，更新加仓价格
                if cell.open_direction == 'b':
                    self.plan_add_price = cell.real_in_price + (cell.N/2)
                if cell.open_direction == 's':
                    self.plan_add_price = cell.real_in_price - (cell.N/2)


        # 更新退出价格信息
        self.update_plan_stop_price()

        # 接收到成交之后打印一下自己
        for hgcell in self.hgCellList:
            hgcell.print_self()

        # 记录在数据库中
        self.saveIntoDB()

        self.printCells("*" * 20 + " out onTrade")
    
    #----------------------------------------------------------------------
    def onStopOrder(self, so):
        """停止单推送"""
        self.myPrint("onStopOrder", so.__dict__)
        pass

    # ----------------------------------------------------------------------
    def myPrint(self, funName, date):
        print("%s strategyHg funName = %s ,  date = %s " % (datetime.now(), funName, date))

    # ----------------------------------------------------------------------
    def addCell(self, cell):
        # 增加一个持仓单位
        # TODO 增加同一关联实例的最大仓位处理
        if self.cell_num >= self.max_cell_num:
            # 已达到最大持仓，直接返回
            return
        # TODO 判断同一策略实例的最大持仓条件，最多不能超过12 ，6 的限制

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
                    self.printCells("【ERROR】check_stop_condition,cell.plan_stop_price is None")
        if self.s_or_b == 's':
            # 空头持仓
            for cell in self.hgCellList:
                if cell.plan_stop_price is not None:
                    if price >= cell.plan_stop_price:
                        # 当前价格大于等于止损价格时，设定目标仓位为0
                        cell.target_unit = 0
                        ret = True
                else:
                    self.printCells("【ERROR】check_stop_condition,cell.plan_stop_price is None")

        return ret

    # ----------------------------------------------------------------------
    def check_add_condition(self, price):
        """检验是否触及加仓条件"""

        ret = False
        if len(self.hgCellList) >= self.max_cell_num:
            # 如果已达到最大仓位，直接返回
            # TODO 增加关联策略实例的仓位控制
            return ret

        cell = self.hgCellList[len(self.hgCellList) - 1] # 取最后一个持仓
        if self.s_or_b == 'b':
            # 多头持仓，并且当前价格大约加仓价
            if price >= self.plan_add_price:
                a_cell = HgCell(self.vtSymbol, self.s_or_b, self.monitor['unit'],
                                self.plan_add_price, HALF_N, cell.N)
                self.addCell(a_cell)
                ret = True

        if self.s_or_b == 's':
            # 空头持仓，并且当前价格小于加仓价
            if price <= self.plan_add_price:
                a_cell = HgCell(self.vtSymbol, self.s_or_b, self.monitor['unit'],
                                self.plan_add_price, HALF_N, cell.N)
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
                continue

            real_in_price = cell.real_in_price # 当前cell的平均买入价格

            # 如果处理的是最后一个cell，直接更新
            if last_real_in_price == None:
                cell.plan_stop_price = cell.real_in_price - 2*cell.N
            else:
                if cell.real_in_price != 0:
                    if 0.8 < float(last_real_in_price)/cell.real_in_price < 1.2:
                        # 差距不大，直接用上一个退出值
                        cell.plan_stop_price = last_plan_stop_price
                    else:
                        # 两次买入价格差距大，使用当次买入值计算
                        cell.plan_stop_price = cell.real_in_price - 2 * cell.N
                else:
                    self.myPrint('update_plan_stop_price','【error】cell.real_in_price == 0')
                    self.myPrint('update_plan_stop_price', '【error】cell info is' + str(cell.__dict__).decode('unicode-escape'))

                    self.trading = False


            last_real_in_price = cell.real_in_price
            last_plan_stop_price = cell.plan_stop_price


    def printCells(self,info=""):
        print(info)
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






