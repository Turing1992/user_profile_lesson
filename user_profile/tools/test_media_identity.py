#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试脚本：从ES查询media开头的索引，提取账号信息并进行身份判断
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import json
from opensearchpy import OpenSearch
from sport_data_get.config import config
from utils.opinin_extract import identity_auto, promts6


def connect_es():
    """连接OpenSearch"""
    es_config = config["ESsearch"]
    client = OpenSearch(
        hosts=es_config["hosts"],
        http_auth=es_config["http_auth"],
        use_ssl=es_config["use_ssl"],
        verify_certs=es_config["verify_certs"],
        ca_certs=es_config["ca_certs"],
        timeout=es_config["timeout"]
    )
    return client


def get_media_indices(client):
    """获取所有media开头的索引"""
    try:
        indices = client.cat.indices(index="media*", format="json")
        index_names = [idx["index"] for idx in indices]
        print(f"找到 {len(index_names)} 个media开头的索引:")
        
        # 显示每个索引的文档数
        total_docs = 0
        for idx in indices:
            doc_count = int(idx.get("docs.count", 0))
            total_docs += doc_count
            print(f"  - {idx['index']}: {doc_count:,} 条")
        
        print(f"\n所有索引总计: {total_docs:,} 条文档")
        return index_names
    except Exception as e:
        print(f"获取索引列表失败: {e}")
        return []


def query_data_with_scroll(client, index_name, size=100):
    """
    使用scroll API查询大量数据
    :param client: ES客户端
    :param index_name: 索引名称
    :param size: 每批查询数量
    :return: generator yielding (hits, total)
    """
    query = {
        "query": {
            "bool": {
                "must": [
                    {"exists": {"field": "description"}},
                    {"bool": {
                        "must_not": [
                            {"term": {"description.keyword": ""}}
                        ]
                    }}
                ],
                "must_not": [
                    {"exists": {"field": "community"}}  # 排除已有community字段的数据
                ]
            }
        },
        "_source": ["verified_reason", "name", "description", "id"]
    }
    
    try:
        # 初始化scroll
        response = client.search(
            index=index_name,
            body=query,
            scroll='5m',  # scroll上下文保持5分钟
            size=size
        )
        
        scroll_id = response['_scroll_id']
        total = response["hits"]["total"]["value"]
        hits = response["hits"]["hits"]
        
        print(f"索引 {index_name}:")
        print(f"  - 符合条件的数据: {total:,} 条 (description不为空 且 没有community字段)")
        
        # 返回第一批数据
        if hits:
            yield hits, total, scroll_id
        
        # 继续scroll获取后续数据
        while len(hits) > 0:
            response = client.scroll(
                scroll_id=scroll_id,
                scroll='5m'
            )
            
            scroll_id = response['_scroll_id']
            hits = response["hits"]["hits"]
            
            if hits:
                yield hits, total, scroll_id
            else:
                break
        
        # 清理scroll上下文
        try:
            client.clear_scroll(scroll_id=scroll_id)
        except:
            pass
            
    except Exception as e:
        print(f"查询索引 {index_name} 失败: {e}")
        return


def update_es_identity(client, index_name, doc_id, identity, identity2):
    """
    更新ES中的身份字段
    :param client: ES客户端
    :param index_name: 索引名称
    :param doc_id: 文档ID
    :param identity: identity字段值（对应three_new_identity）
    :param identity2: identity2字段值（对应community）
    """
    try:
        update_body = {
            "doc": {
                "three_new_identity": identity,
                "community": identity2
            }
        }
        
        response = client.update(
            index=index_name,
            id=doc_id,
            body=update_body
        )
        
        print(f"✓ 更新成功: index={index_name}, id={doc_id}")
        print(f"  three_new_identity: {identity}")
        print(f"  community: {identity2}")
        return True
    except Exception as e:
        print(f"✗ 更新失败: {e}")
        return False


def process_data(client, index_pattern, data_list):
    """
    处理数据并调用身份判断
    :param client: ES客户端
    :param index_pattern: 索引模式（用于更新时获取实际索引名）
    :param data_list: 查询到的数据列表
    :return: (results, kuaidi_count) - 结果列表和快递员数量
    """
    results = []
    kuaidi_count = 0
    
    for idx, hit in enumerate(data_list, 1):
        source = hit.get("_source", {})
        doc_id = hit.get("_id")
        actual_index = hit.get("_index")  # 获取实际的索引名
        
        # 提取字段
        verified_reason = source.get("verified_reason", "")
        name = source.get("name", "")
        description = source.get("description", "")
        user_id = source.get("id", "")
        
        # 拼接文本
        combined_text = f"{verified_reason} {name} {description}".strip()
        
        # 先检查文本中是否包含"快递"
        if "快递" not in combined_text:
            results.append({
                "user_id": user_id,
                "doc_id": doc_id,
                "name": name,
                "result": {"skipped": "不包含快递关键词"},
                "updated": False
            })
            continue
        
        # 包含"快递"才打印和判断
        print(f"\n{'='*60}")
        print(f"发现包含'快递'的数据 (第 {idx} 条)")
        print(f"Index: {actual_index}")
        print(f"Document ID: {doc_id}")
        print(f"User ID: {user_id}")
        print(f"Name: {name}")
        print(f"拼接后文本: {combined_text[:200]}...")
        print(f"✓ 进行LLM判断...")
        
        # 调用身份判断函数
        try:
            result = identity_auto(promts6, combined_text)
            print(f"判断结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
            
            # 提取identity和identity2
            identity = result.get("identity", "")
            identity2 = result.get("identity2", "")
            
            # 判断identity2是否为"快递员"
            if identity2 == "快递员":
                print(f"\n🎯 发现快递员！准备更新ES...")
                
                # 更新ES（使用实际的索引名）
                update_success = update_es_identity(
                    client, 
                    actual_index, 
                    doc_id, 
                    identity, 
                    identity2
                )
                
                if update_success:
                    kuaidi_count += 1
                    print(f"✓ 快递员身份已更新到ES (累计: {kuaidi_count})")
                    
                    results.append({
                        "user_id": user_id,
                        "doc_id": doc_id,
                        "name": name,
                        "result": result,
                        "updated": True
                    })
                else:
                    results.append({
                        "user_id": user_id,
                        "doc_id": doc_id,
                        "name": name,
                        "result": result,
                        "updated": False
                    })
            else:
                print(f"identity2={identity2}，不是快递员")
                results.append({
                    "user_id": user_id,
                    "doc_id": doc_id,
                    "name": name,
                    "result": result,
                    "updated": False
                })
            
        except Exception as e:
            print(f"❌ 身份判断失败: {e}")
            results.append({
                "user_id": user_id,
                "doc_id": doc_id,
                "name": name,
                "result": {"error": str(e)},
                "updated": False
            })
    
    return results, kuaidi_count


def main():
    """主函数 - 全量处理版本（使用scroll API，直接查询media_*）"""
    print("开始执行全量处理脚本...")
    print("=" * 80)
    
    # 1. 连接ES
    print("\n1. 连接OpenSearch...")
    client = connect_es()
    print("✓ 连接成功")
    
    # 2. 直接使用media_*通配符查询所有索引
    print("\n2. 使用 media_* 通配符查询所有索引...")
    index_pattern = "media_*"
    
    # 3. 全量处理
    print(f"\n3. 开始全量处理...")
    print("=" * 80)
    
    batch_size = 10000  # 每批查询10000条
    total_processed = 0
    total_kuaidi = 0
    total_skipped = 0
    total_errors = 0
    batch_num = 0
    
    try:
        # 使用scroll API遍历所有数据
        for data_list, total, scroll_id in query_data_with_scroll(client, index_pattern, size=batch_size):
            batch_num += 1
            
            if not data_list:
                break
            
            print(f"\n[批次 {batch_num}] 开始处理 {len(data_list)} 条数据...")
            
            # 处理数据
            results, kuaidi_count = process_data(client, index_pattern, data_list)
            
            # 统计
            total_processed += len(results)
            total_kuaidi += kuaidi_count
            
            # 统计跳过和错误
            batch_skipped = 0
            batch_errors = 0
            for r in results:
                if r.get("result", {}).get("skipped"):
                    total_skipped += 1
                    batch_skipped += 1
                elif r.get("result", {}).get("error"):
                    total_errors += 1
                    batch_errors += 1
            
            # 显示批次统计
            print(f"\n[批次 {batch_num}] 完成:")
            print(f"  - 处理: {len(results)} 条")
            print(f"  - 跳过: {batch_skipped} 条 (不含'快递')")
            print(f"  - 错误: {batch_errors} 条")
            print(f"  - 本批发现快递员: {kuaidi_count} 个")
            
            # 显示总体进度
            progress = min(100, (total_processed / total) * 100) if total > 0 else 0
            print(f"\n总体进度: {progress:.1f}% ({total_processed:,}/{total:,})")
            print(f"累计统计: 已处理 {total_processed:,} 条, 发现快递员 {total_kuaidi} 个")
            
    except Exception as e:
        print(f"\n处理时出错: {e}")
        import traceback
        traceback.print_exc()
    
    # 4. 输出最终统计
    print(f"\n{'='*80}")
    print("全量处理完成！")
    print(f"{'='*80}")
    print(f"总计处理数据: {total_processed:,} 条")
    print(f"发现快递员: {total_kuaidi} 个")
    print(f"跳过处理: {total_skipped:,} 条 (不包含'快递'关键词)")
    print(f"处理失败: {total_errors} 条")
    print(f"成功更新: {total_kuaidi} 条")
    print(f"{'='*80}")
    
    if total_kuaidi > 0:
        print(f"\n✓ 成功识别并更新了 {total_kuaidi} 个快递员身份到ES")
    else:
        print(f"\n⚠ 未发现任何快递员")
    
    print("\n处理完成！")


if __name__ == "__main__":
    main()
