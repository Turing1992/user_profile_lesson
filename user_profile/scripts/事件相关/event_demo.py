# -*- coding: utf-8 -*-
import queue

# 在全局区域添加以下配置
TASK_QUEUE = queue.Queue(maxsize=1000)  # 定长队列
from utils.prompts import *
from utils.http_llm_factory import *
from utils.about_log import *
import pandas as pd
import math

mylog_hd = config_log("draw_graph", "WARNING")

# 读取Excel身份映射
def load_identity_mapping(excel_path="final_stanterd.xlsx"):
    df_excel = pd.read_excel(excel_path,engine='openpyxl')
    identity_map = dict(zip(df_excel["原始身份"], df_excel["最终身份"]))
    return identity_map

identity_map = load_identity_mapping()


def process(batch_df):
    """
    输入：pandas DataFrame（一批，如10行）
    输出：添加了 'identity', 'identity_standerd', 'info_response_id' 列的 DataFrame
    只对“作者描述”非空非NaN的行调用API，其余行保留原样（新列为空）。
    """
    import json
    import pandas as pd

    batch_df = batch_df.copy()
    n = len(batch_df)
    # 初始化新列
    batch_df['identity'] = [None] * n
    batch_df['identity_standerd'] = [None] * n
    batch_df['info_response_id'] = None

    inputs = []
    valid_local_indices = []  # 记录哪些 local index 是有效的

    for i, row in batch_df.iterrows():
        author_desc = row.get('作者描述', '')
        # 跳过 NaN 或空字符串
        if pd.isna(author_desc) or str(author_desc).strip() == '':
            continue
        dd = {
            '账号名': row['作者名称'],
            '账号自我介绍': str(author_desc).strip(),
            '账号认证原因': "",
            'input_id': i  # 使用局部索引（0~9）
        }
        inputs.append(dd)
        valid_local_indices.append(i)

    # 如果本批次没有有效数据，直接返回
    if not inputs:
        return batch_df

    json_input = json.dumps(inputs, ensure_ascii=False, indent=2)
    results, info_response_id, response_content = get_user_infos(USER_INFOS, json_input, mylog_hd)

    if info_response_id == 0:
        mylog_hd.error(f"请求出错 - {json_input}")
        return batch_df

    mylog_hd.info(f"请求ID: {info_response_id}, 输入数量: {len(inputs)}, 返回结果数量: {len(results)}")

    if len(results) != len(inputs):
        mylog_hd.warning(
            f"结果数量不一致 - 请求ID: {info_response_id}\n"
            f"输入:\n{json_input}\n"
            f"响应:\n{response_content}"
        )

    # 构建 lookup: input_id (int) -> result
    results_lookup = {}
    for res in results:
        inp_id = res.get('input_id')
        if inp_id is not None:
            results_lookup[inp_id] = res

    # 填充有效行的结果
    for local_idx in valid_local_indices:
        result_item = results_lookup.get(local_idx)
        identity = result_item.get('identity', []) if result_item is not None else []

        # 标准化 identity_standerd
        if not identity:
            identity_standerd = []
        elif isinstance(identity, str):
            s = identity.strip()
            if not s or s == "":
                identity_standerd = []
            elif ',' not in s:
                mapped = identity_map.get(s, "其他")
                identity_standerd = [mapped]
            else:
                items = [x.strip() for x in s.split(',') if x.strip()]
                mapped_list = [identity_map.get(item, "其他") for item in items]
                identity_standerd = list(set(mapped_list))
        elif isinstance(identity, list):
            mapped_list = [identity_map.get(str(x).strip(), "其他") for x in identity if str(x).strip()]
            identity_standerd = list(set(mapped_list))
        else:
            identity_standerd = []

        batch_df.at[local_idx, 'identity'] = identity
        batch_df.at[local_idx, 'identity_standerd'] = identity_standerd
        batch_df.at[local_idx, 'info_response_id'] = info_response_id

    return batch_df


from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

def process_xlsx_in_batches(input_file, output_file=None, batch_size=10, max_workers=5):
    # 读取 Excel 文件
    df = pd.read_excel(input_file)

    total_rows = len(df)
    num_batches = math.ceil(total_rows / batch_size)

    # 预切分所有批次，并重置局部索引
    batches = []
    for i in range(num_batches):
        start_idx = i * batch_size
        end_idx = min(start_idx + batch_size, total_rows)
        batch = df.iloc[start_idx:end_idx].copy()
        batch.index = range(len(batch))  # 局部索引 0~N-1
        batches.append((i, batch))

    processed_dfs = [None] * num_batches  # 按顺序存储结果

    # 多线程处理
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_batch_id = {
            executor.submit(process, batch): bid
            for bid, batch in batches
        }

        # 显示进度
        for future in tqdm(as_completed(future_to_batch_id), total=num_batches, desc="Processing batches", unit="batch"):
            bid = future_to_batch_id[future]
            try:
                result = future.result()
                processed_dfs[bid] = result
            except Exception as e:
                tqdm.write(f"⚠️ 批次 {bid} 异常: {e}")
                # 回退到原始 batch（加空列）
                fallback = batches[bid][1].copy()
                for col in ['identity', 'identity_standerd', 'info_response_id']:
                    if col not in fallback.columns:
                        fallback[col] = None
                processed_dfs[bid] = fallback

    # 合并结果（保持原始顺序）
    final_df = pd.concat(processed_dfs, ignore_index=True)

    # 写回 Excel
    if output_file is None:
        output_file = input_file
    final_df.to_excel(output_file, index=False)

    print(f"\n✅ 处理完成，共 {total_rows} 行，已保存到 {output_file}")


if __name__ == "__main__":

    input_path = "事件测试4.xlsx"      # 替换为你的文件路径
    output_path = "output4.xlsx"   # 可选：输出文件名，若为 None 则覆盖原文件
    process_xlsx_in_batches(input_path, output_file=output_path, batch_size=10)