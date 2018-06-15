# encoding: UTF-8

from vnpy.event import EventEngine2
from vnpy.trader.vtZcEngine import DbEngine
from vnpy.trader.vtConstant import (DIRECTION_LONG, DIRECTION_SHORT,
                                    STATUS_NOTTRADED, STATUS_PARTTRADED, STATUS_UNKNOWN,
                                    PRICETYPE_MARKETPRICE)
from vnpy.trader.vtSendMail import SendEmail

# 自定义日志级别
LOG_DEBUG = 10
LOG_INFO = 20
LOG_IMPORTANT = 30
LOG_ERROR = 40

# 全局公用的数据库引擎
eeEE = EventEngine2()
mydb = DbEngine(eeEE)


"""
对于一个交易单位的封装，设定目标仓位后自动进行仓位管理
"""
class Cell(object):
    def __init__(self, vtSymbol, direction, target_unit, plan_in_price, in_condition):

        self.vtSymbol = vtSymbol  # 合约
        self.open_direction = direction  # 买卖方向
        self.target_unit = target_unit  # 目标仓位
        self.plan_in_price = plan_in_price  # 计划入场价格
        self.in_condition = in_condition  # 入场条件 1:20日突破 2:55日突破 3:0.5N 4:移仓

        self.real_unit = 0  # 真实持仓单位
        self.real_in_price = 0  # 平均入场价格
        self.real_out_price = 0  # 平均出场价格
        self.fix_unit = 0 # 修正仓位，默认为0

        self.in_time = ''  # 入场时间

        self.in_orderId_dict = {}  # 记录开仓的订单ID
        self.in_trade_dict = {}  # 记录开仓的成交信息
        self.out_orderId_dict = {}  # 记录平仓的订单ID
        self.out_trade_dict = {}  # 记录平仓的成交信息

    # 自定义日志级别输出函数
    def myPrint(self, strategy, level, funName, data):

        if hasattr(strategy, 'myPrint'):
            # 如果有自定义日志函数
            strategy.myPrint(level, funName, data)
        else:
            strategy.writeCtaLog(data)


    # 确认订单是否都已更新并且都已经是稳定订单,
    def is_all_order_stable(self, strategy):

        ret = True
        NOT_FINISHED_STATUS = [STATUS_NOTTRADED, STATUS_PARTTRADED, STATUS_UNKNOWN]

        # 检查开仓订单是否已全部成交
        for orderid, order in self.in_orderId_dict.items():
            if order is None:
                ret = False
            elif order.status in NOT_FINISHED_STATUS:
                ret = False

        # 检查平仓订单是否已全部成交
        for orderid, order in self.out_orderId_dict.items():
            if order is None:
                ret = False
            elif order.status in NOT_FINISHED_STATUS:
                ret = False

        return ret

    def hand_cell(self, strategy, price):
        # 查看订单是否都是稳定状态，如果不是稳定状态则直接返回

        logInfo = "进入hand_cell。"
        self.myPrint(strategy,LOG_DEBUG, 'cell:hand_cell', logInfo)

        is_stable = self.is_all_order_stable(strategy)


        if not is_stable:
            logInfo = "订单处于非稳定状态。"
            self.myPrint(strategy, LOG_INFO, 'cell:hand_cell', logInfo)
            return []

        # 如果目标仓位和真实仓位一致，则直接返回
        if self.target_unit == self.real_unit:
            logInfo = "目标仓位和真实仓位一致"
            self.myPrint(strategy, LOG_INFO, 'cell:hand_cell', logInfo)
            return []


        orderIdList = []
        in_or_out = ''
        # 如果无订单或者所有订单都是稳定状态,根据目标仓位进行下单

        # 买开中
        if self.open_direction == 'b' and self.target_unit > self.real_unit:
            orderIdList = strategy.buy(price, abs(self.target_unit - self.real_unit))
            in_or_out = 'in'
            logInfo = ('hand_cell 买开, price = %d, mount = %d' % (price, abs(self.target_unit - self.real_unit)))
        # 卖平中
        if self.open_direction == 'b' and self.target_unit < self.real_unit:
            orderIdList = strategy.sell(price, abs(self.target_unit - self.real_unit))
            in_or_out = 'out'
            logInfo = ('hand_cell 卖平, price = %d, mount = %d' % (price, abs(self.target_unit - self.real_unit)))
        # 卖开中
        if self.open_direction == 's' and self.target_unit > self.real_unit:
            orderIdList = strategy.short(price, abs(self.target_unit - self.real_unit))
            in_or_out = 'in'
            logInfo = ('hand_cell 卖开, price = %d, mount = %d' % (price, abs(self.target_unit - self.real_unit)))
        # 买平中
        if self.open_direction == 's' and self.target_unit < self.real_unit:
            orderIdList = strategy.cover(price, abs(self.target_unit - self.real_unit))
            in_or_out = 'out'
            logInfo = ('hand_cell 买平, price = %d, mount = %d' % (price, abs(self.target_unit - self.real_unit)))

        self.myPrint(strategy, LOG_IMPORTANT, 'cell:hand_cell', logInfo)

        self.sendmails(strategy.instanceName + '_' + strategy.instanceId + '_' + self.vtSymbol + ' ' + logInfo)


        for orderid in orderIdList:

            if strategy.sessionID is not None and strategy.frontID is not None:
                # 如果策略维护了 sessionID 和 frontID ，则使用组合值作为唯一id
                orderid = strategy.sessionID + '.' + strategy.frontID + '.' + orderid

            if in_or_out == 'in':
                self.in_orderId_dict[orderid] = None
                self.in_trade_dict[orderid] = None
            if in_or_out == 'out':
                self.out_orderId_dict[orderid] = None
                self.out_trade_dict[orderid] = None

        return orderIdList

    # 更新 in_orderId_dict 和 out_orderId_dict
    def updateOrder(self, order):

        onOrderID = str(order.sessionID) + '.' + str(order.frontID) + '.' + order.vtOrderID
        is_update = False

        if onOrderID in self.in_orderId_dict.keys():
            # 如果在入场订单中匹配到id号
            self.in_orderId_dict[onOrderID] = order
            is_update = True

        if onOrderID in self.out_orderId_dict.keys():
            # 如果在入场订单中匹配到id号
            self.out_orderId_dict[onOrderID] = order
            is_update = True

        return is_update

    # 更新 in_trade_dict 和 out_trade_dict
    def updateTrade(self, orderid, trade):

        is_update = False

        if orderid in self.in_trade_dict.keys():
            # 如果在入场订单中匹配到id号
            self.in_trade_dict[orderid] = trade
            is_update = True

        if orderid in self.out_trade_dict.keys():
            # 如果在入场订单中匹配到id号
            self.out_trade_dict[orderid] = trade
            is_update = True

        # 每次有成交时更新一下cell
        self.update_real_unit_and_price()

        return is_update


    def update_real_unit_and_price(self):

        in_volume = 0
        out_volume = 0
        in_price = 0
        out_price = 0


        for id, trade in self.in_trade_dict.items():
            if trade is not None:
                in_volume = in_volume + trade.volume
                in_price = in_price + trade.volume * trade.price

        for id, trade in self.out_trade_dict.items():
            if trade is not None:
                out_volume = out_volume + trade.volume
                out_price = out_price + trade.volume * trade.price

        self.real_unit = in_volume - out_volume

        if in_volume == 0:
            self.real_in_price = 0
        else:
            self.real_in_price = in_price/in_volume

        if out_volume == 0:
            self.real_out_price = 0
        else:
            self.real_out_price = out_price/out_volume


    def sendmails(self,info):

        mailto_list = ['zhice163@163.com']
        mail = SendEmail('smtp.163.com', 'guosiwei627@163.com', '163zc163')
        if mail.sendTxtMail(mailto_list, "成交日志", info, 'plain'):
            print("邮件 发送成功")
        else:
            print("邮件 发送失败")
        del mail


    def print_self(self):
        print(" ****************** cell 详情开始 *******************")
        print(" 1、基础信息：")
        print(self.__dict__)
        print(" 2、in_orderId_dict：")
        for _key, _value in self.in_orderId_dict.items():
            info = "空"
            if _value is not None:
                info = str(_value.__dict__).decode('unicode-escape')
            print("     " + str(_key) + " : " + info)
        print(" 3、in_trade_dict：")
        for _key, _value in self.in_trade_dict.items():
            info = "空"
            if _value is not None:
                info = str(_value.__dict__).decode('unicode-escape')
            print("     " + str(_key) + " : " + info)
        print(" 4、out_orderId_dict：")
        for _key, _value in self.out_orderId_dict.items():
            info = "空"
            if _value is not None:
                info = str(_value.__dict__).decode('unicode-escape')
            print("     " + str(_key) + " : " + info)
        print(" 5、out_trade_dict：")
        for _key, _value in self.out_trade_dict.items():
            info = "空"
            if _value is not None:
                info = str(_value.__dict__).decode('unicode-escape')
            print("     " + str(_key) + " : " + info)
        print(" ****************** cell 详情结束 *******************")



"""
d = [
    { '$match' : { "instanceName" : "hg01" , "s_or_b" : 's'}},
    { '$group' : { '_id' : "$instanceName", 'total' : {'$sum' : "$cell_num"} }}
]
num = 0
ret = mydb.dbAggregateSum('VnTrader_Main_Db','TB_HG_MAIN',d)



for tmp in ret:
    print(int(tmp['total']))

print(num)
mydb.dbClose()
"""