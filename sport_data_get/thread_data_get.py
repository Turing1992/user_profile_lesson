from daoding_body import *
from download_API import *
import json
import traceback
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import os


# 体育相关关键词（固定部分）
SPORT_KEYWORDS = "(体育强市 OR 全民健身 OR 体教融合 OR 惠民工程 OR 体育产业 OR 15分钟健身圈 OR 国家中心城市 OR 世界赛事名城 OR 体育消费试点 OR 品牌赛事 OR 城市名片 OR 十四五体育规划 OR 体育名城 OR 健康中国 OR 体育旅游示范区 OR 国家体育产业基地 OR 体育局 OR 文体局 OR 体育总会 OR 奥委会 OR 全民健身日 OR 社区运动会 OR 体育中心 OR 奥体中心 OR 体育场 OR 体育馆 OR 游泳馆 OR 专业足球场 OR 体育公园 OR 健身步道 OR 绿道 OR 碧道 OR 登山栈道 OR 社区球场 OR 笼式足球 OR 智慧健身房 OR 奥运会 OR 亚运会 OR 大运会 OR 全运会 OR 省运会 OR 市运会 OR 锦标赛 OR 冠军赛 OR 公开赛 OR 挑战赛 OR 选拔赛 OR 巡回赛 OR 大奖赛 OR 邀请赛 OR 职业联赛 OR 马拉松赛 OR 铁人三项赛 OR 电子竞技 OR 电竞 OR LPL OR KPL OR PEL OR DOTA2 OR 英雄联盟 OR 王者荣耀 OR 和平精英 OR 战队 OR 围棋 OR 象棋 OR 国际象棋 OR 桥牌 OR 足球 OR 篮球 OR 排球 OR 乒乓球 OR 羽毛球 OR 网球 OR 台球 OR 棒球 OR 垒球 OR 橄榄球 OR CBA OR 中超 OR NBA OR 五人制足球 OR 气排球 OR 斯诺克 OR 匹克球 OR 笼式网球 OR 壁球 OR 藤球 OR 曲棍球 OR 手球 OR 板球 OR 门球 OR 毽球 OR 马拉松 OR 半马 OR 越野跑 OR 越山向海 OR 彩色跑 OR 垂直马拉松 OR 骑行 OR 公路车 OR 山地车 OR 死飞 OR 滑板 OR 陆冲 OR 陆地冲浪 OR 飞盘 OR 极限飞盘 OR 腰旗橄榄球 OR 攀岩 OR 抱石 OR 徒步 OR 溯溪 OR 露营 OR 定向越野 OR 跑酷 OR BMX OR Citywalk OR Cityride OR 城市漫步 OR 泵道 OR 轮滑 OR 广场舞 OR 街舞 OR 霹雳舞 OR 尊巴 OR 游泳 OR 皮划艇 OR 赛艇 OR 龙舟 OR 桨板 OR 冲浪 OR 尾波冲浪 OR 潜水 OR 自由潜 OR 帆船 OR 帆板 OR 滑雪 OR 滑冰 OR 冰壶 OR 冰球 OR 短道速滑 OR 花样滑冰 OR 室内滑雪 OR 漂流 OR 武术 OR 太极 OR 八段锦 OR 五禽戏 OR 散打 OR 拳击 OR 摔跤 OR 柔道 OR 跆拳道 OR 泰拳 OR 巴西柔术 OR MMA OR UFC OR 瑜伽 OR 空中瑜伽 OR 普拉提 OR 大器械普拉提 OR CrossFit OR 帕梅拉 OR 刘畊宏 OR 撸铁 OR 健美 OR 举重 OR 壶铃 OR 战绳 OR 团课 OR 莱美 OR 动感单车 OR 核心训练 OR 增肌减脂 OR 普拉提床) NOT (招聘 OR 职位 OR 简历 OR 猎头 OR 兼职 OR 刷单 OR 招嫖 OR 约炮 OR 裸聊 OR 捐卵 OR 代孕 OR 催收 OR 贷款 OR 高利贷 OR 杀猪盘 OR 赌博 OR 赔率 OR 庄家 OR 违章 OR 事故 OR 车祸 OR 亡人 OR 维权 OR 讨薪 OR 烂尾楼 OR 房价 OR 首付 OR 租房 OR 二手房 OR 中介 OR 相亲 OR 征婚 OR 交友 OR 情感咨询 OR 算命 OR 风水 OR 股票 OR 基金 OR 涨停 OR 大盘 OR 明星八卦 OR 饭圈 OR 互撕 OR 打投 OR 体育学院 OR 体育大学 OR 体育职业技术学院 OR 体育频道 OR 体育报 OR 体育彩票 OR 体彩中心)"

# 不限制数据量，获取所有数据
MAX_DATA_COUNT = 999999999

# 设置查询时间范围
START_TIME = "2025-01-01 00:00:00"
END_TIME = "2025-02-01 00:00:00"

# 线程数
THREAD_COUNT = 6

# 输出目录
OUTPUT_DIR = "sport_data_output"

# 线程锁，用于打印和去重
print_lock = threading.Lock()

# URL去重集合（线程安全）
seen_urls = set()
dedup_lock = threading.Lock()


def get_province_name(city_keywords):
    """
    从城市关键词中提取省份名称
    """
    # 取第一个城市作为省份名
    first_city = city_keywords.split(" OR ")[0].strip()
    return first_city


def extract_fields(data):
    """
    提取指定字段
    只保留: url, uuid, ctime, wtype, like_count, reply_count, share_count, 
           visit_count, collect_count, gather.site_name, title, content, 
           user.name, user.verified, user.followers_count, ori_data.feature.sentiment
    """
    extracted = {}
    
    # 直接字段
    for field in ['url', 'uuid', 'ctime', 'wtype', 'like_count', 'reply_count', 
                  'share_count', 'visit_count', 'collect_count', 'title', 'content']:
        if field in data:
            extracted[field] = data[field]
    
    # gather.site_name
    if 'gather' in data and isinstance(data['gather'], dict):
        if 'site_name' in data['gather']:
            extracted['site_name'] = data['gather']['site_name']
    
    # user字段
    if 'user' in data and isinstance(data['user'], dict):
        user_data = {}
        for field in ['name', 'verified', 'followers_count']:
            if field in data['user']:
                user_data[field] = data['user'][field]
        if user_data:
            extracted['user'] = user_data
    
    # ori_data.feature.sentiment
    if 'ori_data' in data and isinstance(data['ori_data'], dict):
        if 'feature' in data['ori_data'] and isinstance(data['ori_data']['feature'], dict):
            if 'sentiment' in data['ori_data']['feature']:
                extracted['sentiment'] = data['ori_data']['feature']['sentiment']
    
    return extracted


def deduplicate_and_extract(contents):
    """
    根据URL去重并提取指定字段
    """
    global seen_urls
    
    deduplicated = []
    new_count = 0
    duplicate_count = 0
    
    with dedup_lock:
        for item in contents:
            url = item.get('url')
            if not url:
                continue
            
            # 检查URL是否已存在
            if url in seen_urls:
                duplicate_count += 1
                continue
            
            # 添加到去重集合
            seen_urls.add(url)
            new_count += 1
            
            # 提取指定字段
            extracted = extract_fields(item)
            deduplicated.append(extracted)
    
    return deduplicated, new_count, duplicate_count


def query_single_day(day_info):
    """
    单天查询任务
    """
    idx, total_days, day_start, day_end, keywords = day_info
    
    with print_lock:
        print(f"[线程 {threading.current_thread().name}] [{idx}/{total_days}] 开始查询: {day_start} ~ {day_end}")
    
    try:
        # 生成当天的查询body
        body = daoding_body_gen(keywords, day_start, day_end)
        
        # 查询当天数据（get_data内部已经处理了cursor清理）
        contents, total_count = get_data(body, max_count=MAX_DATA_COUNT)
        
        # 去重并提取字段
        deduplicated, new_count, duplicate_count = deduplicate_and_extract(contents)
        
        with print_lock:
            if contents:
                print(f"[线程 {threading.current_thread().name}] [{idx}/{total_days}] 完成，获取 {len(contents)} 条，去重后 {new_count} 条（重复 {duplicate_count} 条）")
            else:
                print(f"[线程 {threading.current_thread().name}] [{idx}/{total_days}] 完成，未获取到数据")
        
        return {
            'day': day_start,
            'contents': deduplicated,
            'total_count': total_count,
            'success': True
        }
    except KeyboardInterrupt:
        with print_lock:
            print(f"[线程 {threading.current_thread().name}] [{idx}/{total_days}] 检测到中断信号")
        raise
    except Exception as e:
        with print_lock:
            print(f"[线程 {threading.current_thread().name}] [{idx}/{total_days}] 出错: {str(e)}")
            print(f"详细错误: {traceback.format_exc()}")
        return {
            'day': day_start,
            'contents': [],
            'total_count': 0,
            'success': False,
            'error': str(e)
        }


def query_province(province_name, city_keywords):
    """
    查询单个省份的数据
    """
    print(f"\n{'='*80}")
    print(f"开始查询省份: {province_name}")
    print(f"{'='*80}")
    
    try:
        # 组合完整的关键词
        full_keywords = f"({city_keywords}) AND {SPORT_KEYWORDS}"
        
        # 判断时间跨度
        days = get_time_range_days(START_TIME, END_TIME)
        
        if days > 2:
            print(f"时间跨度: {days} 天，使用 {THREAD_COUNT} 线程并发查询\n")
            
            # 拆分时间范围
            time_ranges = split_time_by_day(START_TIME, END_TIME)
            
            # 准备任务列表
            tasks = []
            for idx, (day_start, day_end) in enumerate(time_ranges, 1):
                tasks.append((idx, len(time_ranges), day_start, day_end, full_keywords))
            
            # 使用线程池并发查询
            all_contents = []
            total_count_sum = 0
            
            try:
                with ThreadPoolExecutor(max_workers=THREAD_COUNT) as executor:
                    # 提交所有任务
                    future_to_task = {executor.submit(query_single_day, task): task for task in tasks}
                    
                    # 收集结果
                    for future in as_completed(future_to_task):
                        try:
                            result = future.result()
                            if result['success'] and result['contents']:
                                all_contents.extend(result['contents'])
                                total_count_sum += result['total_count']
                        except KeyboardInterrupt:
                            print("\n检测到中断信号，取消所有任务...")
                            executor.shutdown(wait=False, cancel_futures=True)
                            raise
                        except Exception as e:
                            print(f"处理任务结果时出错: {str(e)}")
                            continue
            except KeyboardInterrupt:
                print(f"\n{province_name} 查询被中断，已获取 {len(all_contents)} 条数据")
                raise
            
            contents = all_contents
            total_count = total_count_sum
            
        else:
            print(f"时间跨度: {days} 天，使用普通查询模式")
            body = daoding_body_gen(full_keywords, START_TIME, END_TIME)
            raw_contents, total_count = get_data(body, max_count=MAX_DATA_COUNT)
            # 去重并提取字段
            contents, new_count, duplicate_count = deduplicate_and_extract(raw_contents)
            print(f"去重后: {new_count} 条（重复 {duplicate_count} 条）")
        
        print(f"\n{province_name} 查询完成: 总数据量 {total_count}, 已获取 {len(contents)} 条")
        
        return contents, total_count
        
    except KeyboardInterrupt:
        print(f"\n{province_name} 查询被中断")
        raise
    except Exception as e:
        print(f"\n{province_name} 查询出现异常: {str(e)}")
        print(f"详细错误: {traceback.format_exc()}")
        return [], 0


def main():
    """
    主函数：遍历城市关键词文件，为每个省份查询并保存数据
    """
    try:
        # 创建输出目录
        if not os.path.exists(OUTPUT_DIR):
            os.makedirs(OUTPUT_DIR)
            print(f"创建输出目录: {OUTPUT_DIR}")
        
        # 读取城市关键词文件
        city_keywords_file = "city_keywords.txt"
        
        if not os.path.exists(city_keywords_file):
            print(f"错误: 找不到文件 {city_keywords_file}")
            return
        
        with open(city_keywords_file, 'r', encoding='utf-8') as f:
            city_lines = f.readlines()
        
        print(f"共读取 {len(city_lines)} 个省份/地区")
        print(f"查询时间范围: {START_TIME} ~ {END_TIME}")
        print(f"输出目录: {OUTPUT_DIR}\n")
        
        # 遍历每个省份
        for idx, city_keywords in enumerate(city_lines, 1):
            city_keywords = city_keywords.strip()
            if not city_keywords:
                continue
            
            try:
                # 提取省份名称
                province_name = get_province_name(city_keywords)
                
                print(f"\n[{idx}/{len(city_lines)}] 处理省份: {province_name}")
                
                # 查询数据
                contents, total_count = query_province(province_name, city_keywords)
                
                # 保存为JSON文件
                if contents:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = os.path.join(OUTPUT_DIR, f"{province_name}_{timestamp}.json")
                    
                    with open(filename, 'w', encoding='utf-8') as f:
                        json.dump(contents, f, ensure_ascii=False, indent=2)
                    
                    print(f"✓ 数据已保存: {filename} (共 {len(contents)} 条)")
                else:
                    print(f"✗ {province_name} 未获取到数据，跳过保存")
                
                print(f"\n{'='*80}\n")
                
            except KeyboardInterrupt:
                print(f"\n检测到中断信号，停止处理")
                print(f"已完成 {idx-1}/{len(city_lines)} 个省份")
                break
            except Exception as e:
                print(f"\n处理 {province_name} 时出错: {str(e)}")
                print(f"详细错误: {traceback.format_exc()}")
                print(f"跳过该省份，继续下一个\n")
                continue
        
        print(f"\n{'='*80}")
        print("所有省份查询完成！")
        print(f"{'='*80}")
        
    except KeyboardInterrupt:
        print("\n\n程序被用户中断")
    except Exception as e:
        print(f"\n主程序出现异常: {str(e)}")
        print(f"详细错误: {traceback.format_exc()}")


if __name__ == "__main__":
    main()
