# encoding: UTF-8
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

"""
一些基本操作函数
1、图像的生成
2、图像的展示
"""

# 自定义日志级别
LOG_DEBUG = 10
LOG_INFO = 20
LOG_IMPORTANT = 30
LOG_ERROR = 40

"""
第二部分：生成图像的展示html

目录结构如下
path/img/201806/20180630-094254_985594.png
path/img/201807/20180630-094254_985595.png

path/html/index.html

path/html/monthHtml/201806.html
path/html/monthHtml/201807.html

path/html/dayHtml/20180601.html
path/html/dayHtml/20180602.html

"""

# 获取指定文件夹下所有的png文件
def getAllPngFiles(path):
    retList = []
    for fpathe, dirs, fs in os.walk(path):
        for f in fs:
            filePath = str(f)
            if filePath.endswith(".jpg"):
                retList.append(filePath)
    return  retList


# 返回日月两个map
def getDayAndMonthMap(filePath):

    dayMap = {}     # key：日期 value：文件名
    monthMap = {}   # key：月份 value：日期

    for tmp in filePath:
        dayInfo = tmp[:8]
        monthInfo = tmp[0:6]
        _l = dayMap.get(dayInfo,[])
        _l.append(tmp)
        dayMap[dayInfo] = _l

        _m = monthMap.get(monthInfo, [])
        if dayInfo not in _m:
            _m.append(dayInfo)
        monthMap[monthInfo] = _m

    return dayMap, monthMap


def writeFile(filePaht, info):

    file_object = open(filePaht, 'w')
    file_object.write(info)
    file_object.close()

# 生成每天的html
def genDayHtml(dayHtmlPath, dayMap):

    for key, value in dayMap.items():

        filePath = dayHtmlPath + key + '.html'
        htmlInfo = '<html>'
        htmlInfo = htmlInfo + '\r\n' + ' <body>'

        pngInfo = '  <p align="center">'
        pngInfo = pngInfo + '\r\n' + '   <img src="../../img/month/file"/>'
        pngInfo = pngInfo + '\r\n' + '  </p>'

        for pngFile in  value:
            dayHtmlInfo = pngInfo.replace('month', key[0:6])
            dayHtmlInfo = dayHtmlInfo.replace('file', pngFile)

            htmlInfo = htmlInfo + '\r\n' + dayHtmlInfo

        htmlInfo = htmlInfo + '\r\n' + ' </body>'
        htmlInfo = htmlInfo + '\r\n' + '</html>'


        writeFile(filePath,htmlInfo)

# 生成月html
def genMonthHtml(monthHtmlPath, monthMap):

    for key, value in monthMap.items():

        filePath = monthHtmlPath + key + '.html'
        htmlInfo = '<html>'
        htmlInfo = htmlInfo + '\r\n' + ' <body>'

        dayInfo = '  <p align="center">'
        dayInfo = dayInfo + '\r\n' + '   <a href="../dayHtml/file">file</a>'
        dayInfo = dayInfo + '\r\n' + '  </p>'

        # 按日期排下序
        value.sort(reverse=True)

        for dayFile in  value:
            monthHtmlInfo = dayInfo.replace('file', dayFile + '.html')
            htmlInfo = htmlInfo + '\r\n' + monthHtmlInfo

        htmlInfo = htmlInfo + '\r\n' + ' </body>'
        htmlInfo = htmlInfo + '\r\n' + '</html>'

        writeFile(filePath,htmlInfo)

# 生成首页面
def genIndexHtml(rootDir,monthMap):
    indexFilePath = rootDir + 'html/index.html'

    monthInfo = monthMap.keys()
    monthInfo.sort(reverse=True)

    htmlInfo = '<html>'
    htmlInfo = htmlInfo + '\r\n' + ' <body>'

    pInfo = '  <p align="center">'
    pInfo = pInfo + '\r\n' + '   <a href="./monthHtml/file">file</a>'
    pInfo = pInfo + '\r\n' + '  </p>'

    for _tmp in monthInfo:
        monthPInfo = pInfo.replace('file', _tmp + '.html')
        htmlInfo = htmlInfo + '\r\n' + monthPInfo

    htmlInfo = htmlInfo + '\r\n' + ' </body>'
    htmlInfo = htmlInfo + '\r\n' + '</html>'

    writeFile(indexFilePath, htmlInfo)

# 主函数
def genHtmls(rootDir):
    #rootDir = '/Users/zhice/Desktop/zhice/'
    pngPath = rootDir + 'img/'
    dayHtmlPath = rootDir + 'html/dayHtml/'
    monthHtmlPath = rootDir + 'html/monthHtml/'

    if not os.path.exists(dayHtmlPath):
        os.makedirs(dayHtmlPath)

    if not os.path.exists(monthHtmlPath):
        os.makedirs(monthHtmlPath)

    pngFileList = getAllPngFiles(pngPath)
    dayMap, monthMap = getDayAndMonthMap(pngFileList)
    genDayHtml(dayHtmlPath, dayMap)
    genMonthHtml(monthHtmlPath, monthMap)
    genIndexHtml(rootDir, monthMap)


"""
生成图像
"""
# 生成图像的基本函数
def saveImg(strategy, imgPath, titel, s_h, s_l, m_h, m_l, l_h, l_l, close, size):

    strategy.myPrint(LOG_INFO, 'saveImg', '生成图像。')
    if len(s_h) <> size or len(s_l) <> size or len(m_h) <> size or \
                    len(m_l) <> size or len(l_h) <> size or len(l_l) <> size or len(close) <> size:
        strategy.myPrint(LOG_ERROR, 'saveImg', '数组长度错误 len(s_h) = %d, '
                                               'len(s_l) = %d, '
                                               'len(m_h) = %d, '
                                               'len(m_l) = %d, '
                                               'len(l_h) = %d, '
                                               'len(l_l) = %d, '
                                               'len(close) = %d, '
                                               'size = %d' % (len(s_h), len(s_l), len(m_h), \
                                                              len(m_l), len(l_h), len(l_l), len(close), size))
        return

    # 使用figure()函数重新申请一个figure对象
    plt.figure()
    # 第一个参数表示的是编号，第二个表示的是图表的长宽
    fig = plt.figure()  # num=3, figsize=(8, 5)
    ax = fig.add_subplot(1, 1, 1)
    ax.set_title(titel)

    x = np.linspace(1, size, size)

    plt.plot(x, s_h,
             color='green',  # 线颜色
             linewidth=1.0,  # 线宽
             linestyle='--',  # 线样式
             label=u's_h',
             marker='o',
             markersize=3

             )
    plt.plot(x, s_l,
             color='green',  # 线颜色
             linewidth=1.0,  # 线宽
             linestyle=':',  # 线样式
             label=u's_l',
             marker='o',
             markersize=3
             )

    plt.plot(x, m_h,
             color='red',  # 线颜色
             linewidth=1.0,  # 线宽
             linestyle='--',  # 线样式
             label=u'm_h',
             marker='o',
             markersize=3
             )
    plt.plot(x, m_l,
             color='red',  # 线颜色
             linewidth=1.0,  # 线宽
             linestyle=':',  # 线样式
             label=u'm_l',
             marker='o',
             markersize=3
             )
    plt.plot(x, l_h,
             color='blue',  # 线颜色
             linewidth=1.0,  # 线宽
             linestyle='--',  # 线样式
             label=u'l_h',
             marker='o',
             markersize=3
             )
    plt.plot(x, l_l,
             color='blue',  # 线颜色
             linewidth=1.0,  # 线宽
             linestyle=':',  # 线样式
             label=u'l_l',
             marker='o',
             markersize=3
             )
    plt.plot(x, close,
             color='black',  # 线颜色
             linewidth=1.0,  # 线宽
             linestyle='-',  # 线样式
             label=u'close',
             marker='o',
             markersize=3
             )
    plt.text(x[-1], s_h[-1], s_h[-1], ha='left', va='bottom', fontsize=8)
    plt.text(x[-1], s_l[-1], s_l[-1], ha='left', va='bottom', fontsize=8)
    plt.text(x[-1], m_h[-1], m_h[-1], ha='left', va='bottom', fontsize=8)
    plt.text(x[-1], m_l[-1], m_l[-1], ha='left', va='bottom', fontsize=8)
    plt.text(x[-1], l_h[-1], l_h[-1], ha='left', va='bottom', fontsize=8)
    plt.text(x[-1], l_l[-1], l_l[-1], ha='left', va='bottom', fontsize=8)
    plt.text(x[-2], close[-2], close[-2], ha='left', va='bottom', fontsize=8)
    plt.text(x[-1], close[-1], close[-1], ha='left', va='bottom', fontsize=8)

    ax.legend(loc=2)
    plt.savefig(imgPath)













