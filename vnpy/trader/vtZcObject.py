# encoding: UTF-8

from vnpy.event import EventEngine2
from vnpy.trader.vtZcEngine import DbEngine


# 全局公用的数据库引擎
eeEE = EventEngine2()
mydb = DbEngine(eeEE)
