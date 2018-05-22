# encoding: UTF-8

"""
定时服务，可无人值守运行，实现每日自动下载更新历史行情数据到数据库中。
"""

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


#from dataService import *
from zcDataService import *
from vnpy.trader.vtSendMail import SendEmail



if __name__ == '__main__':
    taskCompletedDate = None
    
    # 生成一个随机的任务下载时间，用于避免所有用户在同一时间访问数据服务器
    taskTime = datetime.time(hour=17, minute=random.randint(1,59))
    _i = 0
    # 进入主循环
    while True:
        _i = _i + 1
        t = datetime.datetime.now()
        
        # 每天到达任务下载时间后，执行数据下载的操作
        if t.time() > taskTime and (taskCompletedDate is None or t.date() != taskCompletedDate):

            print u'当前时间%s，任务定时%s，定时任务开始****' % (t, taskTime)
            # 下载1000根分钟线数据，足以覆盖过去两天的行情
            #downloadAllMinuteBar(1000)
            info = ''
            info = info + downloadAllDayBar(5) + '\n'
            info = info + '\n'*5
            info = info + update_dominant_contract() + '\n'
            # 更新任务完成的日期
            taskCompletedDate = t.date()

            mailto_list = ['guosiwei627@163.com', 'zhice163@163.com']
            mail = SendEmail('smtp.163.com', 'guosiwei627@163.com', '163zc163')
            if mail.sendTxtMail(mailto_list, "数据下载报告", info, 'plain'):
                print("数据下载报告 发送成功")
            else:
                print("数据下载报告 发送失败")
            del mail


            print u'********定时任务结束'
        else:
            if _i % 60 == 0:
                print u'当前时间%s，任务定时%s' %(t, taskTime)
    
        time.sleep(60)