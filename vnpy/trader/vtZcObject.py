# encoding: UTF-8

from vnpy.event import EventEngine2
from vnpy.trader.vtZcEngine import DbEngine
from vnpy.trader.vtConstant import (DIRECTION_LONG, DIRECTION_SHORT,
                                    STATUS_NOTTRADED, STATUS_PARTTRADED, STATUS_UNKNOWN,
                                    PRICETYPE_MARKETPRICE)

# 全局公用的数据库引擎
eeEE = EventEngine2()
mydb = DbEngine(eeEE)


"""
对于一个交易单位的封装，设定目标仓位后自动进行仓位管理
"""
class Cell(object):
    def __init__(self, strategy, vtSymbol, direction, target_unit, plan_in_price, in_condition):

        self.strategy = strategy  # 策略实例
        self.vtSymbol = vtSymbol  # 合约
        self.open_direction = direction  # 买卖方向
        self.target_unit = target_unit  # 目标仓位
        self.plan_in_price = plan_in_price  # 计划入场价格
        self.in_condition = in_condition  # 入场条件 1:20日突破 2:55日突破 3:0.5N 4:移仓

        self.real_unit = 0  # 真实持仓单位
        self.real_in_price = 0  # 平均入场价格
        self.fix_unit = 0 # 修正仓位，默认为0

        self.in_time = ''  # 入场时间

        self.in_orderId_dict = {}  # 记录开仓的订单ID
        self.in_trade_dict = {}  # 记录开仓的成交信息
        self.out_orderId_dict = {}  # 记录平仓的订单ID
        self.out_trade_dict = {}  # 记录平仓的成交信息



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

        # 如果目标仓位和真实仓位一致，则直接范围
        if self.target_unit == self.real_unit:
            return []
        print('hand_cell')

        orderIdList = []
        in_or_out = ''
        # 如果无订单或者所有订单都是稳定状态,根据目标仓位进行下单

        # 买开中
        if self.open_direction == 'b' and self.target_unit > self.real_unit:
            orderIdList = self.strategy.buy(price, abs(self.target_unit - self.real_unit))
            in_or_out = 'in'
        # 卖平中
        if self.open_direction == 'b' and self.target_unit < self.real_unit:
            orderIdList = self.strategy.sell(price, abs(self.target_unit - self.real_unit))
            in_or_out = 'out'
        # 卖开中
        if self.open_direction == 's' and self.target_unit > self.real_unit:
            orderIdList = self.strategy.short(price, abs(self.target_unit - self.real_unit))
            in_or_out = 'in'
        # 买平中
        if self.open_direction == 's' and self.target_unit < self.real_unit:
            orderIdList = self.strategy.cover(price, abs(self.target_unit - self.real_unit))
            in_or_out = 'out'
        print("hand_cell sendorderover ")
        for orderid in orderIdList:

            if self.strategy.sessionID is not None and self.strategy.frontID is not None:
                # 如果策略维护了 sessionID 和 frontID ，则使用组合值作为唯一id
                orderid = self.strategy.sessionID + '.' + self.strategy.frontID + '.' + orderid

            if in_or_out == 'in':
                self.in_orderId_dict[orderid] = None
                self.in_trade_dict[orderid] = None
            if in_or_out == 'out':
                self.out_orderId_dict[orderid] = None
                self.out_trade_dict[orderid] = None
        print("save order")
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
    def updateTrade(self, trade):

        orderid = trade.vtOrderID
        # 如果 sessionID 和 frontID 维护了
        if self.strategy.sessionID is not None and self.strategy.frontID is not None:
            orderid = self.strategy.sessionID + '.' + self.strategy.frontID + '.' + orderid

        is_update = False

        if orderid in self.in_orderId_dict.keys():
            # 如果在入场订单中匹配到id号
            self.in_trade_dict[orderid] = trade
            is_update = True

        if orderid in self.out_orderId_dict.keys():
            # 如果在入场订单中匹配到id号
            self.out_trade_dict[orderid] = trade
            is_update = True

        return is_update

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
