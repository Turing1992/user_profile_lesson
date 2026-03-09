from daoding_body import *
from download_API import *
import pandas as pd
from datetime import datetime


keywords="(太原市 OR 大同市 OR 阳泉市 OR 长治市 OR 晋城市 OR 朔州市 OR 晋中市 OR 运城市 OR 忻州市 OR 临汾市 OR 吕梁市) AND (体育强市 OR 全民健身 OR 体教融合 OR 惠民工程 OR 体育产业 OR 15分钟健身圈 OR 国家中心城市 OR 世界赛事名城 OR 体育消费试点 OR 品牌赛事 OR 城市名片 OR 十四五体育规划 OR 体育名城 OR 健康中国 OR 体育旅游示范区 OR 国家体育产业基地 OR 奥运会 OR 亚运会 OR 大运会 OR 全运会 OR 省运会 OR 市运会 OR 锦标赛 OR 冠军赛 OR 公开赛 OR 挑战赛 OR 选拔赛 OR 巡回赛 OR 大奖赛 OR 邀请赛 OR 体育局 OR 文体局 OR 足协 OR 篮协 OR 奥委会 OR 组委会 OR 俱乐部 OR 体育总会 OR 足球 OR 篮球 OR 排球 OR 乒乓球 OR 羽毛球 OR 网球 OR 台球 OR 棒球 OR 垒球 OR 橄榄球 OR CBA OR 中超 OR NBA OR 五人制足球 OR 气排球 OR 斯诺克 OR 匹克球 OR 笼式网球 OR 壁球 OR 藤球 OR 曲棍球 OR 手球 OR 板球 OR 门球 OR 毽球 OR 马拉松 OR 半马 OR 越野跑 OR 夜跑 OR 骑行 OR 公路车 OR 死飞 OR 绿道 OR 破风 OR 滑板 OR 陆冲 OR 陆地冲浪 OR 飞盘 OR 极限飞盘 OR 腰旗橄榄球 OR 攀岩 OR 抱石 OR 徒步 OR 溯溪 OR 露营 OR Glamping OR 定向越野 OR 跑酷 OR BMX OR Citywalk OR 城市漫步 OR Plogging OR 泵道 OR 轮滑 OR 广场舞 OR 街舞 OR 霹雳舞 OR 游泳 OR 皮划艇 OR 赛艇 OR 龙舟 OR 桨板 OR SUP OR 冲浪 OR 尾波冲浪 OR 潜水 OR 自由潜 OR 水肺 OR 帆船 OR 帆板 OR 滑雪 OR 滑冰 OR 冰壶 OR 冰球 OR 短道速滑 OR 花样滑冰 OR 室内滑雪 OR 溯溪 OR 漂流 OR 垂钓 OR 路亚 OR 摩托艇 OR 武术 OR 太极 OR 散打 OR 拳击 OR 摔跤 OR 柔道 OR 跆拳道 OR 泰拳 OR 巴西柔术 OR MMA OR UFC OR 瑜伽 OR 普拉提 OR 尊巴 OR CrossFit OR 帕梅拉 OR 撸铁 OR 健美 OR 举重 OR 壶铃 OR 团课 OR 莱美 OR 动感单车 OR 核心训练 OR 增肌 OR 减脂 OR 围棋 OR 象棋 OR 国际象棋 OR 桥牌 OR 电子竞技 OR 电竞 OR LPL OR KPL OR DOTA2 OR 王者荣耀 OR 英雄联盟 OR 和平精英 OR 绝地求生 OR CSGO OR 无畏契约 OR 战队 OR 俱乐部 OR 线下赛 OR 观赛派对 OR 网咖 OR 剧本杀 OR 体育中心 OR 奥体中心 OR 体育场 OR 体育馆 OR 游泳馆 OR 综合馆 OR 专业足球场 OR 赛车场 OR 赛马场 OR 网球中心 OR 水上运动中心 OR 体育公园 OR 口袋公园 OR 健身步道 OR 绿道 OR 碧道 OR 登山栈道 OR 社区球场 OR 笼式足球 OR 健身房 OR 瑜伽馆 OR 拳馆 OR 滑雪场 OR 溜冰场 OR 攀岩馆 OR 射箭馆 OR 卡丁车场 OR 蹦床公园 OR 运动街区 OR 综合体) NOT (彩票 OR 体彩 OR 足彩 OR 开奖 OR 赔率 OR 股票 OR 大盘 OR 涨停 OR 上市公司 OR 车祸 OR 亡人 OR 刑事案件 OR 违章 OR 酒驾 OR 赌球 OR 兼职 OR 刷单 OR 代购 OR 拼多多 OR 外挂 OR 辅助 OR 涉黄 OR 赌博)"

# 不限制数据量，获取所有数据
MAX_DATA_COUNT = 999999999

# 设置查询时间范围
START_TIME = "2025-06-01 00:00:00"
END_TIME = "2025-07-01 00:00:00"

# 判断时间跨度
days = get_time_range_days(START_TIME, END_TIME)
print(f"查询时间跨度: {days} 天")

if days > 2:
    print("时间跨度超过2天，使用按天查询模式")
    contents, total_count = get_data_by_days(keywords, START_TIME, END_TIME, max_count=MAX_DATA_COUNT)
else:
    print("时间跨度不超过2天，使用普通查询模式")
    body = daoding_body_gen(keywords, START_TIME, END_TIME)
    contents, total_count = get_data(body, max_count=MAX_DATA_COUNT)

print(f"\n总数据量: {total_count}, 已获取: {len(contents)}")

# 限制为2万条
if len(contents) > MAX_DATA_COUNT:
    contents = contents[:MAX_DATA_COUNT]
    print(f"数据已截取至 {MAX_DATA_COUNT} 条")

# 保存为Excel
if contents:
    df = pd.DataFrame(contents)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"sport_data_{timestamp}.xlsx"
    df.to_excel(filename, index=False, engine='openpyxl')
    print(f"\n数据已保存到: {filename}")
    print(f"共保存 {len(contents)} 条数据")
else:
    print("未获取到数据")