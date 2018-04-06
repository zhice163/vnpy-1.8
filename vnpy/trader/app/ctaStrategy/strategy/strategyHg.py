# encoding: UTF-8

"""
海龟交易法则
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
from vnpy.trader.vtZcObject import mydb

BREAK_MIDDLEWINDOW = '20日突破'


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
                 'shortWindow',
                 'middleWindow',
                 'longWindow',

                 # 交易的实例名信息，一个实例包含一组策略实例
                 'instanceName',
                 'instanceAccount']

    
    # 同步列表，保存了需要保存到数据库的变量名称
    syncList = ['pos']



    #----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        """Constructor"""
        super(HgStrategy, self).__init__(ctaEngine, setting)

        self.bg = BarGenerator(self.onBar)
        self.cacheDays = max(self.longWindow, (2*self.middleWindow) + 1)
        self.am = ArrayManager(self.cacheDays)
        self.myDb = mydb # 数据库引擎
        self.ctadbEngine = ctaDbEngine(mydb) # cta 数据库操作的一些封装

        self.hgPosition = {} # 持仓信息
        self.monitor = {} # 合约当天的 10日线高低、20日线高低、55日线和ART信息
        self.contracts = {} # 最新的合约信息
        self.test = True

        self.orderList = [] # 报单列表
        self.tradeList = [] # 成交列表

        self.sessionID = None # 本地交易
        self.frontID = None # 本次交易的

        #self.sessionid = uuid.uuid1() # 本次唯一id

        self.productID = ''  # 品种

        self.hgCellList = []  # 持仓列表，元素为HgCell
        self.cell_num = 0  # 持仓量
        self.s_or_b = ''  # 买卖方向
        self.offsetProfit = ''  # 平仓盈亏
        self.floatProfit = ''  # 浮动盈亏
        self.max_cell_num = 3  # 最大持仓量


        # 海龟交易主力合约，配置时 symbol 配置的是品种名称，进行翻译。
        ret = self.ctadbEngine.getDominantByProductID(self.vtSymbol)

        if ret is not None:
            self.vtSymbol = ret
        #TODO 对 self.vtSymbo 进行校验

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
        self.myPrint("onBar", bar.__dict__)
        #self.buy(3750, 1)
        return
        vtSymbol = bar.vtSymbol

        # 如果发现有合约初始化未完成，直接返回
        if not self.am.inited:
            self.writeCtaLog(u'【ERROR】【hg】合约未能正常初始化' % (vtSymbol))
            return

        # 账户金额有限，如果加仓单位还不到1，则直接返回
        if self.monitor['unit'] == 0:
            return

        # TODO 撤销所有的合约

        # TODO 如果未持有合约，判断是否有突破
        if self.cell_num == 0:
            isBreak = False
            if bar.close > self.monitor['middleWindowHighBreak']:
                # 有向上突破
                isBreak = True
                self.s_or_b = 'b'
                a_cell = HgCell(self, vtSymbol, self.s_or_b, self.monitor['unit'],
                                self.monitor['middleWindowHighBreak'], BREAK_MIDDLEWINDOW)
                self.addCell(a_cell)

            elif bar.close < self.monitor['middleWindowLowBreak']:
                # 有向下突破
                isBreak = True
                self.s_or_b = 's'
                a_cell = HgCell(self, vtSymbol, self.s_or_b, self.monitor['unit'],
                                self.monitor['middleWindowLowBreak'], BREAK_MIDDLEWINDOW)
                self.addCell(a_cell)

        if self.cell_num == 0:
            # 下面的操作只有有持仓时才操作
            return
        # TODO 如果持有合约，判断是否触及退出
        # 10日线退出法则, 多头头寸，价格低于最近10日最低点时退出
        if self.s_or_b == 'b' and bar.close < self.monitor['shortWindowLowBreak']:
            self.quitAllOrders()
        # 10日线退出法则, 空头头寸，价格高于最近10日最高点时退出
        if self.s_or_b == 's' and bar.close > self.monitor['shortWindowHighBreak']:
            self.quitAllOrders()


        # TODO 如果持有合约，判断是否触及止损


        # TODO 如果持有合约，判断是否触及加仓，同时判断仓位是否超过限制


    #----------------------------------------------------------------------
    def onOrder(self, order):
        """收到委托变化推送（必须由用户继承实现）"""
        # 对于无需做细粒度委托控制的策略，可以忽略onOrder
        print("onorder")
        self.myPrint("onOrder", str(order.__dict__).decode('unicode-escape'))
        #TODO

        self.orderList.append(order)

        # 更新 in_orderId_dict 中的订单信息
        for hgcell in self.hgPosition:
            pass
        pass
    
    #----------------------------------------------------------------------
    def onTrade(self, trade):
        """收到成交推送（必须由用户继承实现）"""
        # 对于无需做细粒度委托控制的策略，可以忽略onOrder
        # 打印过trader信息，里面没有session信息
        self.myPrint("onTrade", str(trade.__dict__).decode('unicode-escape'))
        self.tradeList.append(trade)
        pass
    
    #----------------------------------------------------------------------
    def onStopOrder(self, so):
        """停止单推送"""
        self.myPrint("onStopOrder", so.__dict__)
        pass    

    def myPrint(self, funName, date):
        print("%s funName = %s ,  date = %s " % (datetime.now(), funName, date))


    def addCell(self, cell):
        # 增加一个持仓单位
        if self.cell_num >= self.max_cell_num:
            # 已达到最大持仓，直接返回
            return
        # TODO 判断同一策略实例的最大持仓条件，最多不能超过12 ，6 的限制

        self.cell_num = self.cell_num + 1 # 持仓计数加1
        self.hgCellList.append(cell) # 添加在持仓列表中


    def quitAllOrders(self):
        # 设定所有持仓的目标仓位为0
        for cell in self.hgCellList:
            cell.target_unit = 0
    # ----------------------------------------------------------------------







    # ----------------------------------------------------------------------



#############################################################

# 一个品种仓位的信息
class HgCell:

    def __init__(self, strategy, vtSymbol, direction, target_unit, plan_in_price, in_condition):

        self.strategy = strategy  # 策略实例
        self.vtSymbol = vtSymbol # 合约
        self.open_direction = direction # 买卖方向
        self.target_unit = target_unit  # 目标仓位
        self.plan_in_price = plan_in_price  # 计划入场价格
        self.in_condition = in_condition  # 入场条件 1:20日突破 2:55日突破 3:0.5N 4:移仓

        self.real_unit = 0  # 真实持仓单位
        self.real_in_price = 0  # 平均入场价格
        self.in_time = ''  # 入场时间

        self.in_orderId_dict = {}  # 记录开仓的订单ID
        self.in_trade_dict = {}  # 记录开仓的成交信息
        self.out_orderId_dict = {}  # 记录平仓的订单ID
        self.out_trade_dict = {}  # 记录平仓的成交信息


        # self.add_price = 0 # 加仓价格
        self.plan_out_price = 0  # 出场价格
        self.real_out_price = 0  # 出场价格
        self.out_time = 0  # 出场时间
        self.out_condition = '' # 出厂条件


    # 确认订单是否都已经是稳定订单
    def is_all_order_stable(self):

        ret = True
        NOT_FINISHED_STATUS = [STATUS_NOTTRADED, STATUS_PARTTRADED, STATUS_UNKNOWN]

        # 检查开仓订单是否已全部成交
        for orderid, order in self.in_orderId_dict.items():
            if order.status in NOT_FINISHED_STATUS:
                ret = False

        # 检查平仓订单是否已全部成交
        for orderid, order in self.out_orderId_dict.items():
            if order.status in NOT_FINISHED_STATUS:
                ret = False

        return ret


    def hand_cell(self, price):
        # 查看订单是否都是稳定状态，如果不是稳定状态则直接返回
        is_stable = self.is_all_order_stable()
        if not is_stable:
            return []
        #TODO 如果是稳定状态，更新持仓信息

        print('hand_cell')

        orderIdList = []
        in_or_out = ''
        # 如果无订单或者所有订单都是稳定状态,根据目标仓位进行下单
        # 买开中
        if self.open_direction == DIRECTION_LONG and self.target_unit > self.real_unit:
            orderIdList = self.strategy.buy(price, abs(self.target_unit - self.real_unit))
            in_or_out = 'in'
        # 卖平中
        if self.open_direction == DIRECTION_LONG and self.target_unit < self.real_unit:
            orderIdList = self.strategy.sell(price, abs(self.target_unit - self.real_unit))
            in_or_out = 'out'
        # 卖开中
        if self.open_direction == DIRECTION_SHORT and self.target_unit > self.real_unit:
            orderIdList = self.strategy.short(price, abs(self.target_unit - self.real_unit))
            in_or_out = 'in'
        # 买平中
        if self.open_direction == DIRECTION_SHORT and self.target_unit < self.real_unit:
            orderIdList = self.strategy.cover(price, abs(self.target_unit - self.real_unit))
            in_or_out = 'out'
        print("hand_cell sendorderover ")
        for orderid in orderIdList:
            if in_or_out == 'in':
                self.in_orderId_dict[orderid] = None
                self.in_trade_dict[orderid] = None
            if in_or_out == 'out':
                self.out_orderId_dict[orderid] = None
                self.out_trade_dict[orderid] = None
        print("save order")
        return orderIdList









