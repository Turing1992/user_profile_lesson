# -*- coding: utf-8 -*-
"""
事件分析全流水线
输入事件 → 实体抽取 → ES匹配画像 → 未匹配先算身份 → 全部参与平台推演 → 输出结果
"""
import json
import os
import time
import traceback
from typing import Dict, List
from event_analyzer import EventAnalyzer
from es_profile_matcher import ESProfileMatcher
from profile_engine import ProfileEngine
from llm_client import LLMClient
from simulation_engine import SimulationEngine
from social_platform import PlatformType
from platform_adapter import PlatformAdapter


# 身份推断 prompt
IDENTITY_INFER_PROMPT = """你是一个社交媒体分析专家。根据以下事件信息和账号线索，推断该账号的身份信息。

事件背景：
{event_description}

账号名称：{account_name}
账号出现的上下文：{context}

请推断该账号最可能的身份信息，以JSON格式返回：
{{
    "identity": "最可能的身份标签（如：消防员、记者、普通网民等）",
    "description": "基于事件上下文推断的账号描述（50字以内）",
    "verified_reason": "推断的认证原因（如果可能有认证的话）",
    "confidence": 0.0到1.0之间的置信度
}}

只返回JSON，不要其他内容。"""


class EventPipeline:
    """事件分析全流水线"""

    def __init__(self):
        self.event_analyzer = EventAnalyzer()
        self.es_matcher = ESProfileMatcher()
        self._temp_files = []  # 跟踪临时文件，确保清理
        self.profile_engine = ProfileEngine()
        self.llm_client = LLMClient()

    def download_and_build_event(self, keyword: str, start_time: str = None,
                                 end_time: str = None, size: int = 50,
                                 is_expression: bool = False) -> Dict:
        """
        步骤0: 通过关键词下载实时数据，转换为事件格式

        Args:
            keyword: 事件关键词/标题
            start_time: 开始时间 (可选)
            end_time: 结束时间 (可选)
            size: 下载条数

        Returns:
            构建好的事件数据 dict
        """
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'utils'))
        from daoding_body import daoding_body_gen
        from download_API import MyData, get_data

        print(f"\n{'='*60}")
        print(f"[步骤0] 实时数据下载 - 关键词: {keyword}")
        print(f"{'='*60}")

        # 生成请求体
        body = daoding_body_gen(keyword, start=start_time, end=end_time, size=size, is_expression=is_expression)
        print(f"  请求体: source={body.get('source')}, size={body.get('size')}, time={body.get('time')}")

        # 调用下载接口
        contents, total_count = get_data(body)

        if contents == '无' or not contents:
            print(f"  ⚠️ 未获取到数据")
            return {
                "event_id": f"kw_{keyword[:20]}_{int(time.time())}",
                "event_type": "关键词事件",
                "event_description": keyword,
                "related_content": [],
                "download_info": {"keyword": keyword, "total_count": 0, "downloaded": 0}
            }

        print(f"  下载到 {len(contents)} 条数据 (总计 {total_count} 条)")

        # 转换为事件格式
        related_content = []
        account_names = set()

        for item in contents:
            # 提取用户信息
            user_info = item.get("user", {}) if isinstance(item.get("user"), dict) else {}
            user_name = user_info.get("name", "") or item.get("author", "") or ""
            uid = user_info.get("uid", "") or ""
            site_name = item.get("site_name", "") or item.get("gather", {}).get("site_name", "") if isinstance(item.get("gather"), dict) else item.get("site_name", "")

            # 提取内容
            content = item.get("content", "") or item.get("title", "") or ""
            title = item.get("title", "") or ""

            if user_name:
                account_names.add(user_name)

            # 构建 related_content 条目
            if user_name and content:
                line = f"@{user_name} "
                if site_name:
                    line += f"[{site_name}] "
                # 截取内容前200字
                content_short = content[:200] if len(content) > 200 else content
                line += content_short
                related_content.append(line)
            elif content:
                related_content.append(content[:200])

        # 构建事件描述
        event_desc = keyword
        if len(contents) > 0:
            # 用前几条内容的标题丰富事件描述
            titles = [item.get("title", "") for item in contents[:5] if item.get("title")]
            if titles:
                event_desc = f"{keyword}。相关报道：{'；'.join(titles[:3])}"

        event_data = {
            "event_id": f"kw_{keyword[:20]}_{int(time.time())}",
            "event_type": "关键词事件",
            "event_description": event_desc,
            "related_content": related_content,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "download_info": {
                "keyword": keyword,
                "total_count": total_count,
                "downloaded": len(contents),
                "accounts_found": list(account_names)[:50],  # 最多记录50个
                "sources": list(set(
                    item.get("site_name", "") or
                    (item.get("gather", {}).get("site_name", "") if isinstance(item.get("gather"), dict) else "")
                    for item in contents
                ))
            }
        }

        print(f"  构建事件: {event_data['event_id']}")
        print(f"  相关内容条数: {len(related_content)}")
        print(f"  涉及账号数: {len(account_names)}")

        return event_data

    def run_from_keyword(self, keyword: str, platform: str = "weibo",
                         sim_steps: int = 10, use_llm_sim: bool = False,
                         start_time: str = None, end_time: str = None,
                         download_size: int = 50, progress_cb=None,
                         is_expression: bool = False) -> Dict:
        """
        从关键词开始的完整流水线

        Args:
            keyword: 事件关键词/标题
            platform: 推演平台 weibo / douyin
            sim_steps: 模拟步数
            use_llm_sim: 模拟是否使用LLM
            start_time: 数据下载开始时间
            end_time: 数据下载结束时间
            download_size: 下载条数

        Returns:
            完整分析结果
        """
        # 步骤0: 下载数据并构建事件
        if progress_cb:
            progress_cb("⏳ 步骤0/5: 正在下载实时数据...")
        event_data = self.download_and_build_event(
            keyword, start_time=start_time, end_time=end_time, size=download_size,
            is_expression=is_expression
        )

        if not event_data.get("related_content"):
            return {
                "status": "no_data",
                "message": f"关键词 '{keyword}' 未下载到任何数据",
                "event_info": event_data
            }

        # 执行后续流水线
        if progress_cb:
            progress_cb(f"✅ 数据下载完成，获取{event_data['download_info']['downloaded']}条数据")
        result = self.run(event_data, platform=platform,
                          sim_steps=sim_steps, use_llm_sim=use_llm_sim,
                          progress_cb=progress_cb)

        # 在结果中插入步骤0信息
        step0 = {
            "step": "实时数据下载",
            "keyword": keyword,
            "downloaded": event_data["download_info"]["downloaded"],
            "total_count": event_data["download_info"]["total_count"],
            "accounts_found": len(event_data["download_info"].get("accounts_found", [])),
            "sources": event_data["download_info"].get("sources", [])
        }
        result["steps"].insert(0, step0)
        result["download_info"] = event_data["download_info"]

        return result

    def run(self, event_data: Dict, platform: str = "weibo",
            sim_steps: int = 10, use_llm_sim: bool = False,
            progress_cb=None) -> Dict:
        """
        执行完整流水线（三分支模拟）

        Args:
            event_data: 事件数据
            platform: 推演平台 weibo / douyin
            sim_steps: 模拟步数
            use_llm_sim: 模拟是否使用LLM决策

        Returns:
            完整分析结果，包含三个分支的模拟结果
        """
        result = {
            "event_info": event_data,
            "platform": platform,
            "steps": []
        }

        # ===== 步骤1: 实体抽取 =====
        if progress_cb:
            progress_cb("⏳ 步骤1/5: 实体抽取中...")
        print(f"\n{'='*60}")
        print(f"[步骤1] 实体抽取 - 事件: {event_data.get('event_id')}")
        print(f"{'='*60}")

        entities = self.event_analyzer.extract_entities(event_data)
        accounts = entities.get("accounts", [])
        keywords = entities.get("keywords", [])
        print(f"  抽取到 {len(accounts)} 个账号: {accounts}")
        print(f"  抽取到 {len(keywords)} 个关键词: {keywords}")

        result["extracted_entities"] = entities
        result["steps"].append({
            "step": "实体抽取",
            "accounts_found": len(accounts),
            "accounts": accounts,
            "keywords": keywords
        })

        if not accounts:
            result["status"] = "no_accounts"
            result["message"] = "未从事件中抽取到任何账号"
            return result

        # ===== 步骤1.5: 过滤官方媒体账号 =====
        if progress_cb:
            progress_cb(f"✅ 抽取到{len(accounts)}个账号，正在过滤官方媒体...", dict(result))
        print(f"\n{'='*60}")
        print(f"[步骤1.5] 官方媒体过滤 ({len(accounts)} 个账号)")
        print(f"{'='*60}")

        filtered_accounts, official_accounts = self._filter_official_accounts(accounts)
        print(f"  官方/机构账号 ({len(official_accounts)}): {official_accounts}")
        print(f"  个人账号 ({len(filtered_accounts)}): {filtered_accounts}")

        result["steps"].append({
            "step": "官方媒体过滤",
            "before_count": len(accounts),
            "after_count": len(filtered_accounts),
            "official_removed": official_accounts,
            "personal_kept": filtered_accounts
        })

        accounts = filtered_accounts
        if not accounts:
            result["status"] = "no_personal_accounts"
            result["message"] = "所有账号均为官方媒体/机构，无个人账号可推演"
            return result

        # ===== 步骤2: ES画像匹配 =====
        if progress_cb:
            progress_cb(f"⏳ 步骤2/5: ES画像匹配（{len(accounts)}个账号）...")
        print(f"\n{'='*60}")
        print(f"[步骤2] ES画像匹配 ({len(accounts)} 个账号)")
        print(f"{'='*60}")

        matched = {}
        unmatched = []

        for account_name in accounts:
            es_results = self.es_matcher.search_by_name(account_name, platform=platform, size=1)
            if es_results and es_results[0].get("_score", 0) > 50.0:
                matched[account_name] = es_results[0]
                print(f"  ✅ {account_name} -> 匹配到 (score={es_results[0].get('_score', 0):.1f})")
            else:
                unmatched.append(account_name)
                print(f"  ❌ {account_name} -> 未匹配")

        # 保存 ES 匹配到的完整数据供前端展示
        result["es_matched_details"] = {
            name: {k: v for k, v in data.items()}
            for name, data in matched.items()
        }

        result["steps"].append({
            "step": "ES画像匹配",
            "matched_count": len(matched),
            "unmatched_count": len(unmatched),
            "matched_accounts": list(matched.keys()),
            "unmatched_accounts": unmatched
        })

        # ===== 步骤3: 未匹配账号 → LLM推断身份 =====
        if progress_cb:
            progress_cb(f"⏳ 步骤3/5: 匹配{len(matched)}个，推断{len(unmatched)}个未匹配账号身份...", dict(result))
        print(f"\n{'='*60}")
        print(f"[步骤3] 未匹配账号身份推断 ({len(unmatched)} 个)")
        print(f"{'='*60}")

        inferred_profiles = {}
        related_content = event_data.get("related_content", [])

        for account_name in unmatched:
            context_lines = [line for line in related_content if account_name in line]
            context = " | ".join(context_lines) if context_lines else "无具体上下文"

            print(f"  推断 {account_name} 的身份...")
            try:
                inferred = self._infer_identity(
                    account_name,
                    event_data.get("event_description", ""),
                    context
                )
                inferred_profiles[account_name] = inferred
                print(f"    → 身份: {inferred.get('identity', '未知')}, 置信度: {inferred.get('confidence', 0)}")
            except Exception as e:
                print(f"    → 推断失败: {e}")
                inferred_profiles[account_name] = {
                    "identity": "未知",
                    "description": "事件相关账号",
                    "verified_reason": "",
                    "confidence": 0.1
                }

        result["steps"].append({
            "step": "身份推断",
            "inferred_count": len(inferred_profiles),
            "inferred": {k: v.get("identity", "未知") for k, v in inferred_profiles.items()}
        })

        # ===== 步骤4: 组装全部账号画像，进行平台推演 =====
        if progress_cb:
            progress_cb(f"⏳ 步骤4/5: 画像推演（{len(matched)+len(inferred_profiles)}个账号，每个6维度LLM调用）...")
        print(f"\n{'='*60}")
        print(f"[步骤4] 画像推演 - 平台: {platform}")
        print(f"{'='*60}")

        all_profiles = []       # 分支A: 全部账号
        identity_profiles = []  # 分支B: 有identity字段的
        community_profiles = [] # 分支C: 有community字段的
        profile_results = []
        total_accounts = len(matched) + len(inferred_profiles)
        profile_idx = 0

        # 已匹配的账号
        for account_name, es_data in matched.items():
            profile_idx += 1
            if progress_cb:
                progress_cb(f"⏳ 步骤4: 画像推演 ({profile_idx}/{total_accounts}) {account_name}...")
            # 检查是否有三新身份(community)
            community_val = es_data.get("community", "")
            has_community = bool(community_val and str(community_val).strip() and str(community_val).strip() != "[]")

            account_data = {
                "account_id": es_data.get("uid", account_name),
                "platform": platform,
                "name": es_data.get("name", account_name),
                "identity": es_data.get("identity", ""),
                "description": es_data.get("description", ""),
                "verified_reason": es_data.get("verified_reason", ""),
                "gender": es_data.get("gender", ""),
                "followers_count": es_data.get("followers_count", 0),
                "ip_region": es_data.get("ip_region", ""),
            }

            if has_community:
                print(f"  推演已匹配账号: {account_name} (identity={es_data.get('identity', '无')}, community={community_val})")
                try:
                    profile_result = self.profile_engine.generate_full_profile(account_data, platform=platform)
                    profile_result["source"] = "es_matched"
                    profile_result["es_data"] = es_data
                    profile_results.append(profile_result)
                except Exception as e:
                    print(f"    推演失败: {e}")
                    profile_results.append({
                        "account_id": account_name, "source": "es_matched",
                        "status": "failed", "error": str(e)
                    })
            else:
                print(f"  跳过推演（无三新身份）: {account_name} (identity={es_data.get('identity', '无')}, community=空)")
                profile_results.append({
                    "account_id": account_name, "source": "es_matched",
                    "status": "skipped", "reason": "无三新身份(community)",
                    "es_data": es_data
                })

            sim_profile = self._build_sim_profile(account_name, es_data, platform)
            all_profiles.append(sim_profile)

            # 分支B: 有identity字段
            identity_val = es_data.get("identity", "")
            if identity_val and str(identity_val).strip() and str(identity_val).strip() != "[]":
                identity_profiles.append(sim_profile)

            # 分支C: 有community字段
            if has_community:
                community_profiles.append(sim_profile)

        # 未匹配的账号
        for account_name, inferred in inferred_profiles.items():
            profile_idx += 1
            if progress_cb:
                progress_cb(f"⏳ 步骤4: 画像推演 ({profile_idx}/{total_accounts}) {account_name}（推断）...")
            account_data = {
                "account_id": account_name,
                "platform": platform,
                "name": account_name,
                "identity": inferred.get("identity", ""),
                "description": inferred.get("description", ""),
                "verified_reason": inferred.get("verified_reason", ""),
            }
            print(f"  推演新账号: {account_name} (推断身份: {inferred.get('identity', '未知')})")
            try:
                profile_result = self.profile_engine.generate_full_profile(account_data, platform=platform)
                profile_result["source"] = "inferred"
                profile_result["inferred_identity"] = inferred
                profile_results.append(profile_result)
            except Exception as e:
                print(f"    推演失败: {e}")
                profile_results.append({
                    "account_id": account_name, "source": "inferred",
                    "status": "failed", "error": str(e)
                })

            sim_profile = self._build_sim_profile(account_name, inferred, platform)
            all_profiles.append(sim_profile)

            # 推断出来的账号都有identity，加入分支B
            inferred_identity = inferred.get("identity", "")
            if inferred_identity and inferred_identity != "未知":
                identity_profiles.append(sim_profile)

        result["profile_results"] = profile_results
        result["steps"].append({
            "step": "画像推演",
            "total_profiles": len(profile_results),
            "success": len([p for p in profile_results if p.get("status") == "success"]),
            "failed": len([p for p in profile_results if p.get("status") == "failed"]),
            "skipped": len([p for p in profile_results if p.get("status") == "skipped"])
        })
        if progress_cb:
            progress_cb(f"✅ 画像推演完成，开始三分支分析...", dict(result))

        # ===== 步骤5: 三分支深度分析 + 社交模拟 =====
        if progress_cb:
            progress_cb(f"⏳ 步骤5: 三分支深度分析与社交模拟...")
        print(f"\n{'='*60}")
        print(f"[步骤5] 三分支深度分析 + 社交模拟")
        print(f"{'='*60}")

        event_id = event_data.get('event_id', 'temp')
        platform_type = PlatformType.DOUYIN if platform == "douyin" else PlatformType.WEIBO

        # 按分支收集原始账号数据（用于深度分析）
        branch_source_data = {
            "branch_a_all": {},
            "branch_b_identity": {},
            "branch_c_community": {},
        }
        for account_name, es_data in matched.items():
            branch_source_data["branch_a_all"][account_name] = {"source": "es", "data": es_data}
            identity_val = es_data.get("identity", "")
            if identity_val and str(identity_val).strip() and str(identity_val).strip() != "[]":
                branch_source_data["branch_b_identity"][account_name] = {"source": "es", "data": es_data}
            community_val = es_data.get("community", "")
            if community_val and str(community_val).strip() and str(community_val).strip() != "[]":
                branch_source_data["branch_c_community"][account_name] = {"source": "es", "data": es_data}
        for account_name, inf_data in inferred_profiles.items():
            branch_source_data["branch_a_all"][account_name] = {"source": "inferred", "data": inf_data}
            inf_identity = inf_data.get("identity", "")
            if inf_identity and inf_identity != "未知":
                branch_source_data["branch_b_identity"][account_name] = {"source": "inferred", "data": inf_data}

        branches = {
            "branch_a_all": {
                "label": "全部账号",
                "profiles": all_profiles,
            },
            "branch_b_identity": {
                "label": "有身份(identity)账号",
                "profiles": identity_profiles,
            },
            "branch_c_community": {
                "label": "有三新身份(community)账号",
                "profiles": community_profiles,
            },
        }

        simulations = {}
        for branch_key, branch_info in branches.items():
            profiles = branch_info["profiles"]
            label = branch_info["label"]
            source_accounts = branch_source_data.get(branch_key, {})
            print(f"\n  --- {label} ({len(profiles)} 个账号) ---")

            if len(profiles) < 2:
                print(f"  跳过（账号不足2个）")
                simulations[branch_key] = {
                    "label": label,
                    "agent_count": len(profiles),
                    "agents": [p.get("name", p.get("account_id")) for p in profiles],
                    "skipped": True,
                    "reason": "账号不足2个"
                }
                continue

            # --- 5a: 分支深度分析 ---
            branch_analysis = None
            try:
                if progress_cb:
                    progress_cb(f"⏳ 分支{label}: 群体深度分析中...")
                branch_analysis = self._generate_branch_analysis(
                    event_data, platform, label, source_accounts
                )
                print(f"  ✅ {label} 深度分析完成")
            except Exception as e:
                print(f"  ⚠️ {label} 深度分析失败: {e}")
                branch_analysis = {"error": str(e)}

            # --- 5b: 社交模拟 ---
            db_path = f"pipeline_{event_id}_{branch_key}.db"
            output_file = f"pipeline_{event_id}_{branch_key}.json"
            try:
                if progress_cb:
                    progress_cb(f"⏳ 分支{label}: 社交模拟推演中...")
                sim_engine = SimulationEngine(
                    db_path=db_path,
                    platform_type=platform_type,
                    max_workers=5
                )
                sim_engine.load_agents(profiles)
                sim_engine.run_simulation(steps=sim_steps, use_llm=use_llm_sim)

                sim_engine.export_data(output_file)

                with open(output_file, 'r', encoding='utf-8') as f:
                    sim_data = json.load(f)

                simulations[branch_key] = {
                    "label": label,
                    "agent_count": len(profiles),
                    "agents": [p.get("name", p.get("account_id")) for p in profiles],
                    "result": sim_data,
                    "branch_analysis": branch_analysis,
                    "status": "completed"
                }
                print(f"  ✅ {label} 模拟完成")
            except Exception as e:
                print(f"  ❌ {label} 模拟失败: {e}")
                traceback.print_exc()
                simulations[branch_key] = {
                    "label": label,
                    "agent_count": len(profiles),
                    "branch_analysis": branch_analysis,
                    "status": "failed",
                    "error": str(e)
                }
            finally:
                # 确保临时文件被清理
                for fp in [db_path, output_file]:
                    if os.path.exists(fp):
                        try:
                            os.remove(fp)
                        except:
                            pass

        result["simulations"] = simulations
        result["steps"].append({
            "step": "三分支社交模拟",
            "branches": {
                k: {"label": v["label"], "agents": v["agent_count"],
                    "status": v.get("status", "skipped")}
                for k, v in simulations.items()
            }
        })
        if progress_cb:
            progress_cb("✅ 三分支模拟完成，生成舆情报告...", dict(result))

        # ===== 步骤6: LLM 综合分析报告 =====
        if progress_cb:
            progress_cb("⏳ 步骤6/6: 生成舆情推演分析报告...")
        print(f"\n{'='*60}")
        print(f"[步骤6] 生成舆情推演分析报告")
        print(f"{'='*60}")

        try:
            summary_report = self._generate_summary_report(
                event_data, platform, simulations, profile_results,
                matched, inferred_profiles
            )
            result["summary_report"] = summary_report
            result["steps"].append({"step": "舆情推演报告"})
            print(f"  ✅ 报告生成完成")
        except Exception as e:
            print(f"  ⚠️ 报告生成失败: {e}")
            traceback.print_exc()
            result["summary_report"] = {"error": str(e)}

        result["status"] = "success"
        print(f"\n{'='*60}")
        print(f"流水线执行完成（三分支）")
        print(f"{'='*60}\n")

        return result

    def _infer_identity(self, account_name: str, event_desc: str, context: str) -> Dict:
        """用LLM推断未知账号的身份"""
        prompt = IDENTITY_INFER_PROMPT.format(
            event_description=event_desc,
            account_name=account_name,
            context=context
        )
        result, _, _ = self.llm_client.call(prompt)
        if isinstance(result, dict):
            return result
        return {
            "identity": "未知",
            "description": "事件相关账号",
            "verified_reason": "",
            "confidence": 0.1
        }

    def _filter_official_accounts(self, accounts: List[str]) -> tuple:
        """
        用LLM判断哪些是官方媒体/机构账号，返回 (个人账号列表, 官方账号列表)
        """
        if not accounts:
            return [], []

        prompt = f"""你是一个社交媒体分析专家。请判断以下账号名称中，哪些是官方媒体、政府机构、新闻媒体、官方组织的账号，哪些是个人用户账号。

账号列表：
{json.dumps(accounts, ensure_ascii=False)}

判断标准：
- 官方媒体：如 中国日报、央视频、CCTV法治在线、东南早报、西安晚报、千龙网、中工网 等
- 政府/司法机构：如 XX法院、XX检察院、XX公安局、XX省政府 等
- 官方组织：如 XX协会、XX基金会、XX官微 等
- 新闻平台：如 各界新闻网、台风FM、今日头条官方 等
- 以上都算官方账号，其余算个人账号

请以JSON格式返回：
{{"official": ["官方账号1", "官方账号2"], "personal": ["个人账号1", "个人账号2"]}}

只返回JSON，不要其他内容。"""

        try:
            result, _, _ = self.llm_client.call(prompt)
            if isinstance(result, dict):
                official = result.get("official", [])
                personal = result.get("personal", [])
                # 确保没有遗漏：LLM没归类的默认保留为个人
                classified = set(official) | set(personal)
                for acc in accounts:
                    if acc not in classified:
                        personal.append(acc)
                return personal, official
        except Exception as e:
            print(f"  ⚠️ LLM过滤失败，使用规则过滤: {e}")

        # LLM失败时的规则兜底
        official_keywords = [
            "日报", "晚报", "早报", "新闻", "电视", "广播", "FM", "频道",
            "央视", "CCTV", "卫视", "法院", "检察", "公安", "政府",
            "官微", "官方", "中工网", "千龙网", "人民网", "新华",
            "协会", "基金会", "委员会", "中国", "省", "市", "区",
            "网信", "发布", "共青团", "工会"
        ]
        official = []
        personal = []
        for acc in accounts:
            clean = acc.lstrip("@")
            if any(kw in clean for kw in official_keywords):
                official.append(acc)
            else:
                personal.append(acc)
        return personal, official

    def _build_sim_profile(self, account_name: str, data: Dict, platform: str) -> Dict:
        """构建社交模拟用的Agent画像"""
        identity = data.get("identity", "普通用户")
        if isinstance(identity, list):
            identity = identity[0] if identity else "普通用户"

        description = data.get("description", "")
        # 从身份推断兴趣
        interests = self._guess_interests(identity, description)

        prefix = "dy" if platform == "douyin" else "wb"
        return {
            "account_id": f"{prefix}_{account_name}",
            "user_id": f"{prefix}_{account_name}",
            "name": account_name,
            "identity": identity,
            "interests": interests,
            "personality": self._guess_personality(identity),
            "description": description or f"{identity}，事件相关账号",
        }

    def _guess_interests(self, identity: str, description: str) -> List[str]:
        """根据身份猜测兴趣标签"""
        identity_interests = {
            "消防员": ["消防", "救援", "安全"],
            "记者": ["新闻", "时事", "社会"],
            "医生": ["医疗", "健康", "科普"],
            "教师": ["教育", "学习", "成长"],
            "警察": ["治安", "法律", "安全"],
            "律师": ["法律", "维权", "社会"],
            "科技博主": ["科技", "AI", "互联网"],
            "美食博主": ["美食", "探店", "生活"],
            "健身教练": ["健身", "运动", "健康"],
        }
        for key, interests in identity_interests.items():
            if key in str(identity):
                return interests
        return ["社会", "时事", "生活"]

    def _guess_personality(self, identity: str) -> Dict:
        """根据身份猜测性格"""
        active_identities = ["记者", "博主", "主播", "达人", "教练"]
        is_active = any(k in str(identity) for k in active_identities)
        return {
            "type": "外向" if is_active else "内向",
            "activity": "高" if is_active else "中",
            "sentiment": "积极"
        }

    def _generate_summary_report(self, event_data: Dict, platform: str,
                                  simulations: Dict, profile_results: List,
                                  matched: Dict, inferred: Dict) -> Dict:
        """用LLM生成舆情推演综合分析报告"""
        # 构建模拟数据摘要
        branch_summaries = []
        for key, sim in simulations.items():
            label = sim.get("label", key)
            if sim.get("skipped"):
                branch_summaries.append(f"- {label}: 跳过（{sim.get('reason', '账号不足')}）")
                continue
            if sim.get("status") == "failed":
                branch_summaries.append(f"- {label}: 模拟失败")
                continue
            r = sim.get("result", {})
            ps = r.get("platform_stats", {})
            stats = r.get("stats", {})
            agents = r.get("agents", [])
            # 每步快照的趋势
            snapshots = r.get("step_snapshots", [])
            trend = ""
            if len(snapshots) >= 2:
                first = snapshots[0].get("platform_stats", {})
                last = snapshots[-1].get("platform_stats", {})
                trend = f"（趋势：帖子{first.get('total_posts',0)}→{last.get('total_posts',0)}，赞{first.get('total_likes',0)}→{last.get('total_likes',0)}，评{first.get('total_comments',0)}→{last.get('total_comments',0)}，转{first.get('total_reposts',0)}→{last.get('total_reposts',0)}）"

            # agent行为分布
            agent_details = []
            for ag in agents[:5]:
                bd = ag.get("action_breakdown", {})
                if bd:
                    acts = ", ".join([f"{k}:{v}" for k, v in bd.items()])
                    agent_details.append(f"  {ag.get('username','?')}({ag.get('identity','?')}): {acts}")

            branch_summaries.append(
                f"- {label}（{sim.get('agent_count',0)}人）: "
                f"帖子{ps.get('total_posts',0)}, 点赞{ps.get('total_likes',0)}, "
                f"评论{ps.get('total_comments',0)}, 转发{ps.get('total_reposts',0)}, "
                f"总行为{stats.get('total_actions',0)}{trend}\n"
                + "\n".join(agent_details)
            )

        # 账号画像摘要
        profile_summary = []
        for name, data in matched.items():
            identity = data.get("identity", "未知")
            community = data.get("community", "")
            profile_summary.append(f"  {name}: 身份={identity}, 三新身份={community or '无'}")
        for name, data in inferred.items():
            profile_summary.append(f"  {name}(推断): 身份={data.get('identity', '未知')}")

        platform_name = "微博" if platform == "weibo" else "抖音"

        # 收集各分支深度分析的关键结论
        branch_analysis_summaries = []
        for key, sim in simulations.items():
            ba = sim.get("branch_analysis")
            if ba and not ba.get("error"):
                label = sim.get("label", key)
                parts = []
                for field in ["group_composition", "stance_prediction", "risk_profiles", "branch_insight"]:
                    val = ba.get(field, "")
                    if val:
                        parts.append(f"  {field}: {val[:150]}")
                if parts:
                    branch_analysis_summaries.append(f"- {label}:\n" + "\n".join(parts))

        branch_analysis_section = ""
        if branch_analysis_summaries:
            branch_analysis_section = f"""

【各分支群体深度分析摘要】
{chr(10).join(branch_analysis_summaries)}"""

        prompt = f"""你是一个资深舆情分析师。请根据以下社交媒体模拟推演数据，生成一份专业的舆情推演分析报告。

【事件信息】
事件ID: {event_data.get('event_id', '')}
事件描述: {event_data.get('event_description', '')}
推演平台: {platform_name}

【涉事账号画像】
{chr(10).join(profile_summary)}

【三分支模拟结果】
{chr(10).join(branch_summaries)}
{branch_analysis_section}

请生成以下结构的分析报告（用JSON返回）：
{{
    "title": "报告标题（简洁概括事件和推演结论）",
    "overview": "事件概述（2-3句话）",
    "spread_prediction": "传播预测：基于模拟数据，预测该事件在{platform_name}上的传播趋势、速度、范围",
    "key_actors": "关键角色分析：哪些账号/群体在传播中最活跃，他们的行为模式",
    "sentiment_trend": "舆情走向：基于参与者身份和行为，预测舆论情绪走向（正面/负面/中性）",
    "risk_points": "风险提示：可能出现的舆情风险点、次生舆情",
    "branch_comparison": "三分支对比：全部账号 vs 有身份账号 vs 三新身份账号的模拟差异说明了什么",
    "recommendations": "应对建议：针对该事件的舆情应对策略建议"
}}

要求：
1. 分析要基于实际模拟数据，不要空泛
2. 结合账号身份特征做差异化分析
3. 语言专业但易懂
4. 只返回JSON"""

        result, _, _ = self.llm_client.call(prompt)
        if isinstance(result, dict) and result:
            return result
        return {
            "title": f"{event_data.get('event_description', '事件')}舆情推演报告",
            "overview": "模拟推演已完成，但自动分析生成失败，请参考上方模拟数据自行分析。",
            "error": "LLM分析生成失败"
        }

    def _generate_group_profile_analysis(self, event_data: Dict, platform: str,
                                          matched: Dict, inferred: Dict,
                                          profile_results: List) -> Dict:
        """用LLM对所有涉事账号做群体画像深度分析"""
        # 构建账号详情
        account_details = []
        for name, data in matched.items():
            detail = f"- {name}（ES匹配）: 身份={data.get('identity','未知')}, " \
                     f"三新身份={data.get('community','无')}, " \
                     f"粉丝={data.get('followers_count',0)}, " \
                     f"简介={str(data.get('description',''))[:60]}, " \
                     f"认证={data.get('verified_reason','无')}, " \
                     f"性别={data.get('gender','未知')}, " \
                     f"IP={data.get('ip_region','未知')}"
            account_details.append(detail)
        for name, data in inferred.items():
            detail = f"- {name}（LLM推断）: 身份={data.get('identity','未知')}, " \
                     f"置信度={data.get('confidence',0)}, " \
                     f"描述={data.get('description','')[:60]}"
            account_details.append(detail)

        # 画像推演结果摘要
        profile_summaries = []
        for pr in profile_results:
            if pr.get("status") == "success":
                aid = pr.get("account_id", "?")
                # 提取6维度的关键信息
                dims = []
                for key in ["behavior_pattern", "interest_map", "social_influence",
                            "content_style", "activity_rhythm", "psychological_profile"]:
                    val = pr.get(key)
                    if isinstance(val, dict):
                        summary = json.dumps(val, ensure_ascii=False)[:80]
                        dims.append(f"{key}: {summary}")
                    elif isinstance(val, str):
                        dims.append(f"{key}: {val[:80]}")
                if dims:
                    profile_summaries.append(f"- {aid}: " + "; ".join(dims[:3]))

        platform_name = "微博" if platform == "weibo" else "抖音"
        prompt = f"""你是一个资深用户画像分析师。请根据以下事件涉及的账号数据，生成一份群体画像深度分析报告。

【事件信息】
事件: {event_data.get('event_description', '')}
平台: {platform_name}

【涉事账号详情】（共{len(account_details)}个）
{chr(10).join(account_details)}

【画像推演结果摘要】
{chr(10).join(profile_summaries) if profile_summaries else '（部分账号因无三新身份跳过推演）'}

请生成以下结构的群体画像分析（用JSON返回）：
{{
    "group_composition": "群体构成：这些账号整体是什么人群构成？职业分布、身份层次、地域分布等",
    "common_traits": "共性特征：这些账号有什么共同点？为什么他们都出现在这个事件中？",
    "influence_hierarchy": "影响力层级：谁是核心传播者、谁是跟随者、谁是旁观者？基于粉丝数、认证、身份判断",
    "stance_prediction": "立场预判：基于身份和背景，预判各账号/群体对事件的态度倾向（支持/反对/中立/观望）",
    "motivation_analysis": "传播动机：不同身份的人参与传播的可能动机是什么（职业需要/情感共鸣/蹭热度/维权等）",
    "risk_profiles": "高风险账号：哪些账号可能引发舆情升级或带节奏？为什么？",
    "profile_depth_note": "画像深度说明：当前画像维度的局限性，以及如果有更多数据（如历史发帖、互动网络）可以进一步分析什么"
}}

要求：
1. 分析要具体到人，不要泛泛而谈
2. 结合事件背景做针对性分析
3. 对没有三新身份的账号也要给出判断
4. 只返回JSON"""

        result, _, _ = self.llm_client.call(prompt)
        if isinstance(result, dict) and result:
            return result
        return {"error": "群体画像分析生成失败"}

    def _generate_branch_analysis(self, event_data: Dict, platform: str,
                                   branch_label: str, source_accounts: Dict) -> Dict:
        """为单个分支生成群体深度分析"""
        if not source_accounts:
            return {"error": "该分支无账号数据"}

        account_lines = []
        for name, info in source_accounts.items():
            src = info["source"]
            data = info["data"]
            if src == "es":
                line = f"- {name}（ES匹配）: 身份={data.get('identity','未知')}, " \
                       f"三新身份={data.get('community','无')}, " \
                       f"粉丝={data.get('followers_count',0)}, " \
                       f"简介={str(data.get('description',''))[:60]}, " \
                       f"认证={data.get('verified_reason','无')}, " \
                       f"性别={data.get('gender','未知')}, " \
                       f"IP={data.get('ip_region','未知')}"
            else:
                line = f"- {name}（LLM推断）: 身份={data.get('identity','未知')}, " \
                       f"置信度={data.get('confidence',0)}, " \
                       f"描述={data.get('description','')[:60]}"
            account_lines.append(line)

        platform_name = "微博" if platform == "weibo" else "抖音"
        prompt = f"""你是一个资深用户画像分析师。请对以下分支的账号群体做深度分析。

【事件】{event_data.get('event_description', '')}
【平台】{platform_name}
【分支】{branch_label}（共{len(source_accounts)}个账号）

【账号详情】
{chr(10).join(account_lines)}

请生成以下结构的分析（JSON格式）：
{{
    "group_composition": "群体构成：这个分支的人群是什么构成？职业分布、身份层次",
    "common_traits": "共性特征：这些人有什么共同点？为什么被归入这个分支",
    "influence_hierarchy": "影响力层级：谁是核心传播者、谁是跟随者",
    "stance_prediction": "立场预判：各账号对事件的态度倾向",
    "motivation_analysis": "传播动机：不同身份参与传播的可能动机",
    "risk_profiles": "风险点：这个群体可能引发什么舆情风险",
    "branch_insight": "分支洞察：这个分支相比其他分支（全部账号/有身份/三新身份）有什么独特之处"
}}

要求：具体到人分析，结合事件背景，只返回JSON"""

        result, _, _ = self.llm_client.call(prompt)
        if isinstance(result, dict) and result:
            return result
        return {"error": f"{branch_label}分析生成失败"}
