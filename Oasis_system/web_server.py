# -*- coding: utf-8 -*-
"""
Oasis系统 Web 测试服务
整合三大模块：画像推演、社交模拟、事件分析
"""
import json
import os
import uuid
import threading
import traceback
from flask import Flask, request, jsonify, send_file
from profile_engine import ProfileEngine
from storage import ProfileStorage
from event_analyzer import EventAnalyzer
from batch_event_processor import BatchEventProcessor
from simulation_engine import SimulationEngine
from social_platform import PlatformType
from oasis_simulation import generate_sample_profiles
from event_pipeline import EventPipeline

app = Flask(__name__)
engine = ProfileEngine()
storage = ProfileStorage()
event_analyzer = EventAnalyzer()

# 模拟任务状态
sim_tasks = {}


@app.route('/')
def index():
    return send_file('web_app.html')


@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "ok", "service": "Oasis Web Platform"})


# ==================== 模块1: 画像推演 ====================

@app.route('/api/profile/analyze', methods=['POST'])
def analyze_profile():
    """单个账号画像推演"""
    try:
        data = request.json
        if not data or "account_id" not in data:
            return jsonify({"status": "error", "message": "缺少 account_id"}), 400
        result = engine.generate_full_profile(data, platform=data.get("platform"))
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/profile/batch', methods=['POST'])
def batch_analyze_profile():
    """批量账号画像推演"""
    try:
        account_list = request.json
        if not isinstance(account_list, list):
            return jsonify({"status": "error", "message": "请求体必须是数组"}), 400
        results = []
        for acc in account_list:
            try:
                result = engine.generate_full_profile(acc, platform=acc.get("platform"))
                results.append(result)
            except Exception as e:
                results.append({"account_id": acc.get("account_id"), "status": "failed", "error": str(e)})
        return jsonify({"status": "success", "total": len(account_list), "results": results})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


# ==================== 模块2: 社交模拟 ====================

@app.route('/api/simulation/start', methods=['POST'])
def start_simulation():
    """启动社交模拟（异步）"""
    try:
        data = request.json or {}
        platform_str = data.get("platform", "weibo")
        agent_count = int(data.get("agent_count", 20))
        steps = int(data.get("steps", 10))
        use_llm = data.get("use_llm", False)
        profiles = data.get("profiles")

        platform_type = PlatformType.DOUYIN if platform_str == "douyin" else PlatformType.WEIBO

        if not profiles:
            profiles = generate_sample_profiles(agent_count, platform_str)

        task_id = str(uuid.uuid4())[:8]
        db_path = f"sim_{task_id}.db"

        sim_tasks[task_id] = {"status": "running", "progress": 0, "result": None, "error": None}

        def run_sim():
            try:
                sim_engine = SimulationEngine(db_path=db_path, platform_type=platform_type, max_workers=5)
                sim_engine.load_agents(profiles)
                sim_engine.run_simulation(steps=steps, use_llm=use_llm)
                output_file = f"sim_{task_id}_results.json"
                sim_engine.export_data(output_file)
                with open(output_file, 'r', encoding='utf-8') as f:
                    result_data = json.load(f)
                sim_tasks[task_id]["status"] = "completed"
                sim_tasks[task_id]["result"] = result_data
                # 清理临时文件
                for fp in [db_path, output_file]:
                    if os.path.exists(fp):
                        try:
                            os.remove(fp)
                        except:
                            pass
            except Exception as e:
                traceback.print_exc()
                sim_tasks[task_id]["status"] = "failed"
                sim_tasks[task_id]["error"] = str(e)

        t = threading.Thread(target=run_sim, daemon=True)
        t.start()

        return jsonify({"status": "started", "task_id": task_id,
                         "params": {"platform": platform_str, "agents": len(profiles), "steps": steps, "use_llm": use_llm}})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/simulation/status/<task_id>', methods=['GET'])
def simulation_status(task_id):
    """查询模拟任务状态"""
    task = sim_tasks.get(task_id)
    if not task:
        return jsonify({"status": "error", "message": "任务不存在"}), 404
    resp = {"task_id": task_id, "status": task["status"]}
    if task["status"] == "completed":
        resp["result"] = task["result"]
    elif task["status"] == "failed":
        resp["error"] = task["error"]
    return jsonify(resp)


# ==================== 模块3: 事件分析 ====================

@app.route('/api/event/analyze', methods=['POST'])
def analyze_event():
    """单个事件分析"""
    try:
        data = request.json
        if not data or "event_id" not in data:
            return jsonify({"status": "error", "message": "缺少 event_id"}), 400
        report = event_analyzer.analyze_event(data)
        return jsonify({"status": "success", "report": report})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/event/batch', methods=['POST'])
def batch_analyze_events():
    """批量事件分析"""
    try:
        events = request.json
        if not isinstance(events, list):
            return jsonify({"status": "error", "message": "请求体必须是数组"}), 400
        processor = BatchEventProcessor()
        reports = processor.process_events(events)
        cross = processor.generate_cross_event_analysis()
        return jsonify({"status": "success", "reports": reports, "cross_analysis": cross})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


# ==================== 模块4: 事件全流水线 ====================

pipeline = EventPipeline()
pipeline_tasks = {}


@app.route('/api/pipeline/run', methods=['POST'])
def run_pipeline():
    """启动事件全流水线（异步）"""
    try:
        data = request.json
        if not data or "event_id" not in data:
            return jsonify({"status": "error", "message": "缺少 event_id"}), 400

        platform = data.pop("_platform", "weibo")
        sim_steps = int(data.pop("_sim_steps", 10))
        use_llm_sim = data.pop("_use_llm_sim", False)

        task_id = str(uuid.uuid4())[:8]
        pipeline_tasks[task_id] = {"status": "running", "result": None, "error": None, "progress": "⏳ 初始化中..."}

        def run():
            try:
                def on_progress(msg):
                    pipeline_tasks[task_id]["progress"] = msg

                result = pipeline.run(
                    event_data=data,
                    platform=platform,
                    sim_steps=sim_steps,
                    use_llm_sim=use_llm_sim,
                    progress_cb=on_progress
                )
                pipeline_tasks[task_id]["status"] = "completed"
                pipeline_tasks[task_id]["result"] = result
            except Exception as e:
                traceback.print_exc()
                pipeline_tasks[task_id]["status"] = "failed"
                pipeline_tasks[task_id]["error"] = str(e)

        t = threading.Thread(target=run, daemon=True)
        t.start()

        return jsonify({"status": "started", "task_id": task_id,
                         "params": {"platform": platform, "sim_steps": sim_steps}})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/pipeline/status/<task_id>', methods=['GET'])
def pipeline_status(task_id):
    """查询流水线任务状态"""
    task = pipeline_tasks.get(task_id)
    if not task:
        return jsonify({"status": "error", "message": "任务不存在"}), 404
    resp = {"task_id": task_id, "status": task["status"]}
    if task["status"] == "running":
        resp["progress"] = task.get("progress", "")
    if task["status"] == "completed":
        resp["result"] = task["result"]
    elif task["status"] == "failed":
        resp["error"] = task["error"]
    return jsonify(resp)


@app.route('/api/pipeline/run_keyword', methods=['POST'])
def run_pipeline_keyword():
    """通过关键词启动事件全流水线（异步）"""
    try:
        data = request.json
        if not data or "keyword" not in data:
            return jsonify({"status": "error", "message": "缺少 keyword 参数"}), 400

        keyword = data["keyword"]
        platform = data.get("platform", "weibo")
        sim_steps = int(data.get("sim_steps", 10))
        use_llm_sim = data.get("use_llm_sim", False)
        start_time = data.get("start_time")
        end_time = data.get("end_time")
        download_size = int(data.get("download_size", 50))
        is_expression = data.get("is_expression", False)

        task_id = str(uuid.uuid4())[:8]
        pipeline_tasks[task_id] = {"status": "running", "result": None, "error": None, "progress": "⏳ 初始化中..."}

        def run():
            try:
                def on_progress(msg):
                    pipeline_tasks[task_id]["progress"] = msg

                result = pipeline.run_from_keyword(
                    keyword=keyword,
                    platform=platform,
                    sim_steps=sim_steps,
                    use_llm_sim=use_llm_sim,
                    start_time=start_time,
                    end_time=end_time,
                    download_size=download_size,
                    progress_cb=on_progress,
                    is_expression=is_expression
                )
                pipeline_tasks[task_id]["status"] = "completed"
                pipeline_tasks[task_id]["result"] = result
            except Exception as e:
                traceback.print_exc()
                pipeline_tasks[task_id]["status"] = "failed"
                pipeline_tasks[task_id]["error"] = str(e)

        t = threading.Thread(target=run, daemon=True)
        t.start()

        return jsonify({"status": "started", "task_id": task_id,
                         "params": {"keyword": keyword, "platform": platform,
                                    "sim_steps": sim_steps, "download_size": download_size}})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


# ==================== 示例数据 ====================

@app.route('/api/examples/<name>', methods=['GET'])
def get_example(name):
    """获取示例数据"""
    mapping = {
        "profile": "example_input.json",
        "simulation": "example_profiles.json",
        "event": "example_events.json",
    }
    filename = mapping.get(name)
    if not filename or not os.path.exists(filename):
        return jsonify({"status": "error", "message": "示例不存在"}), 404
    with open(filename, 'r', encoding='utf-8') as f:
        return jsonify(json.load(f))


if __name__ == '__main__':
    try:
        storage.init_table()
    except Exception as e:
        print(f"[警告] MySQL 初始化跳过: {e}")
    print("\n" + "=" * 50)
    print("  OASIS Web 测试平台已启动")
    print("  访问 http://localhost:5001")
    print("=" * 50 + "\n")
    app.run(host='0.0.0.0', port=5001, debug=False)
