"""
=============================================================
第8课：综合项目 —— 移动机器人自主导航仿真
=============================================================

【项目目标】
把前面学的所有知识串起来，实现一个完整的移动机器人：
1. 在有障碍物的环境中用 A* 规划路径
2. 用 PID 控制器跟踪路径
3. 用卡尔曼滤波融合带噪声的传感器数据
4. 实时可视化整个过程

【系统架构】
感知层 → 定位层 → 规划层 → 控制层 → 执行层

传感器(带噪声) → 卡尔曼滤波(定位) → A*(路径规划) → PID(控制) → 电机(运动)

【机器人模型】
差速驱动模型（两个轮子独立控制）：
    x' = v * cos(θ)
    y' = v * sin(θ)
    θ' = ω
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyArrow
import heapq
from collections import defaultdict


# ==================== 环境 ====================

class Environment:
    """仿真环境：栅格地图 + 连续空间"""
    
    def __init__(self, width, height, resolution=0.5):
        """
        参数:
            width, height: 环境尺寸（米）
            resolution: 栅格分辨率（米/格）
        """
        self.width = width
        self.height = height
        self.resolution = resolution
        self.grid_w = int(width / resolution)
        self.grid_h = int(height / resolution)
        self.grid = np.zeros((self.grid_h, self.grid_w), dtype=int)
        self.obstacles = []  # 连续空间障碍物 (cx, cy, radius)
    
    def add_circle_obstacle(self, cx, cy, radius):
        """添加圆形障碍物（同时更新栅格和连续表示）"""
        self.obstacles.append((cx, cy, radius))
        # 更新栅格（膨胀一点，给机器人留余量）
        inflate = 0.3  # 膨胀半径
        for gy in range(self.grid_h):
            for gx in range(self.grid_w):
                wx = gx * self.resolution
                wy = gy * self.resolution
                if (wx - cx)**2 + (wy - cy)**2 <= (radius + inflate)**2:
                    self.grid[gy][gx] = 1
    
    def world_to_grid(self, x, y):
        """世界坐标 → 栅格坐标"""
        gx = int(x / self.resolution)
        gy = int(y / self.resolution)
        gx = max(0, min(gx, self.grid_w - 1))
        gy = max(0, min(gy, self.grid_h - 1))
        return gx, gy
    
    def grid_to_world(self, gx, gy):
        """栅格坐标 → 世界坐标"""
        return gx * self.resolution, gy * self.resolution
    
    def is_free_grid(self, gx, gy):
        if 0 <= gx < self.grid_w and 0 <= gy < self.grid_h:
            return self.grid[gy][gx] == 0
        return False
    
    def is_collision(self, x, y, robot_radius=0.2):
        """检查连续空间中是否碰撞"""
        for cx, cy, r in self.obstacles:
            if (x - cx)**2 + (y - cy)**2 <= (r + robot_radius)**2:
                return True
        if x < 0 or x > self.width or y < 0 or y > self.height:
            return True
        return False


# ==================== 路径规划（A*） ====================

def plan_path(env, start_world, goal_world):
    """
    A* 路径规划
    
    输入世界坐标，输出世界坐标路径
    """
    start = env.world_to_grid(*start_world)
    goal = env.world_to_grid(*goal_world)
    
    open_set = []
    heapq.heappush(open_set, (0, start))
    came_from = {}
    g_score = defaultdict(lambda: float('inf'))
    g_score[start] = 0
    visited = set()
    
    directions = [(0,1),(0,-1),(1,0),(-1,0),(1,1),(1,-1),(-1,1),(-1,-1)]
    
    while open_set:
        _, current = heapq.heappop(open_set)
        if current in visited:
            continue
        visited.add(current)
        
        if current == goal:
            path = []
            node = goal
            while node in came_from:
                path.append(env.grid_to_world(*node))
                node = came_from[node]
            path.append(env.grid_to_world(*start))
            path.reverse()
            return path
        
        for dx, dy in directions:
            nx, ny = current[0] + dx, current[1] + dy
            neighbor = (nx, ny)
            if not env.is_free_grid(nx, ny) or neighbor in visited:
                continue
            cost = np.sqrt(dx**2 + dy**2)
            tentative_g = g_score[current] + cost
            if tentative_g < g_score[neighbor]:
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                h = np.sqrt((nx - goal[0])**2 + (ny - goal[1])**2)
                heapq.heappush(open_set, (tentative_g + h, neighbor))
    
    return None  # 无路径


def smooth_path(path, iterations=50, weight_smooth=0.3, weight_data=0.5):
    """
    路径平滑：让A*产生的锯齿路径变得平滑
    
    使用梯度下降法，在"贴近原始路径"和"平滑"之间取平衡
    """
    if not path or len(path) <= 2:
        return path
    
    smoothed = [list(p) for p in path]
    
    for _ in range(iterations):
        for i in range(1, len(smoothed) - 1):
            for dim in range(2):
                original = path[i][dim]
                prev_s = smoothed[i-1][dim]
                next_s = smoothed[i+1][dim]
                curr_s = smoothed[i][dim]
                
                smoothed[i][dim] += (
                    weight_data * (original - curr_s) +
                    weight_smooth * (prev_s + next_s - 2 * curr_s)
                )
    
    return [tuple(p) for p in smoothed]


# ==================== 卡尔曼滤波（定位） ====================

class RobotLocalizer:
    """机器人定位：卡尔曼滤波"""
    
    def __init__(self, dt):
        self.dt = dt
        # 状态: [x, y, theta, v, omega]
        self.x = np.zeros(5)
        self.P = np.eye(5) * 0.1
        
        # 过程噪声
        self.Q = np.diag([0.01, 0.01, 0.005, 0.1, 0.05])
        # 观测噪声（GPS-like）
        self.R = np.diag([0.3, 0.3, 0.1])
    
    def predict(self, v_cmd, omega_cmd):
        """预测步：基于运动模型"""
        x, y, theta, v, omega = self.x
        dt = self.dt
        
        # 非线性运动模型
        self.x[0] = x + v * np.cos(theta) * dt
        self.x[1] = y + v * np.sin(theta) * dt
        self.x[2] = theta + omega * dt
        self.x[3] = v_cmd   # 假设速度能立即响应
        self.x[4] = omega_cmd
        
        # 线性化的状态转移矩阵（EKF近似）
        F = np.eye(5)
        F[0, 2] = -v * np.sin(theta) * dt
        F[0, 3] = np.cos(theta) * dt
        F[1, 2] = v * np.cos(theta) * dt
        F[1, 3] = np.sin(theta) * dt
        F[2, 4] = dt
        
        self.P = F @ self.P @ F.T + self.Q
    
    def update(self, z_x, z_y, z_theta):
        """更新步：用观测修正"""
        H = np.array([
            [1, 0, 0, 0, 0],
            [0, 1, 0, 0, 0],
            [0, 0, 1, 0, 0]
        ])
        
        z = np.array([z_x, z_y, z_theta])
        y = z - H @ self.x
        y[2] = np.arctan2(np.sin(y[2]), np.cos(y[2]))  # 角度归一化
        
        S = H @ self.P @ H.T + self.R
        K = self.P @ H.T @ np.linalg.inv(S)
        
        self.x = self.x + K @ y
        self.P = (np.eye(5) - K @ H) @ self.P
    
    def get_pose(self):
        return self.x[0], self.x[1], self.x[2]


# ==================== PID控制 ====================

class PathTracker:
    """路径跟踪控制器"""
    
    def __init__(self):
        self.Kp_linear = 1.5
        self.Kp_angular = 4.0
        self.Kd_angular = 0.5
        self.prev_heading_error = 0
        self.lookahead = 1.0  # 前瞻距离
        self.waypoint_idx = 0
    
    def get_target_waypoint(self, robot_x, robot_y, path):
        """找到前方最近的路径点"""
        while self.waypoint_idx < len(path) - 1:
            dx = path[self.waypoint_idx][0] - robot_x
            dy = path[self.waypoint_idx][1] - robot_y
            dist = np.sqrt(dx**2 + dy**2)
            if dist > self.lookahead:
                break
            self.waypoint_idx += 1
        return path[min(self.waypoint_idx, len(path) - 1)]
    
    def compute(self, robot_x, robot_y, robot_theta, path, dt):
        """
        计算控制量
        返回: (v, omega) 线速度和角速度
        """
        if self.waypoint_idx >= len(path):
            return 0, 0
        
        # 目标点
        target = self.get_target_waypoint(robot_x, robot_y, path)
        
        # 距离和角度
        dx = target[0] - robot_x
        dy = target[1] - robot_y
        distance = np.sqrt(dx**2 + dy**2)
        target_angle = np.arctan2(dy, dx)
        
        # 航向误差
        heading_error = target_angle - robot_theta
        heading_error = np.arctan2(np.sin(heading_error), np.cos(heading_error))
        
        # PD控制角速度
        d_error = (heading_error - self.prev_heading_error) / dt if dt > 0 else 0
        omega = self.Kp_angular * heading_error + self.Kd_angular * d_error
        self.prev_heading_error = heading_error
        
        # 线速度：角度偏差大时减速
        v = self.Kp_linear * distance * np.cos(heading_error)
        v = np.clip(v, 0, 2.0)  # 限速
        omega = np.clip(omega, -3.0, 3.0)
        
        # 到达终点附近停下
        final_dist = np.sqrt((path[-1][0] - robot_x)**2 + (path[-1][1] - robot_y)**2)
        if final_dist < 0.3:
            return 0, 0
        
        return v, omega
    
    def is_done(self, robot_x, robot_y, path):
        final_dist = np.sqrt((path[-1][0] - robot_x)**2 + (path[-1][1] - robot_y)**2)
        return final_dist < 0.3


# ==================== 机器人 ====================

class DiffDriveRobot:
    """差速驱动机器人"""
    
    def __init__(self, x, y, theta):
        self.x = x
        self.y = y
        self.theta = theta
    
    def move(self, v, omega, dt):
        """执行运动（加入一点噪声模拟真实情况）"""
        noise_v = np.random.normal(0, 0.05)
        noise_omega = np.random.normal(0, 0.02)
        
        actual_v = v + noise_v
        actual_omega = omega + noise_omega
        
        self.x += actual_v * np.cos(self.theta) * dt
        self.y += actual_v * np.sin(self.theta) * dt
        self.theta += actual_omega * dt
    
    def get_noisy_observation(self):
        """模拟带噪声的传感器观测"""
        obs_x = self.x + np.random.normal(0, 0.2)
        obs_y = self.y + np.random.normal(0, 0.2)
        obs_theta = self.theta + np.random.normal(0, 0.05)
        return obs_x, obs_y, obs_theta


# ==================== 主仿真 ====================

def run_simulation():
    """运行完整的机器人导航仿真"""
    print("=" * 60)
    print("🤖 综合项目：移动机器人自主导航仿真")
    print("=" * 60)
    
    # --- 1. 创建环境 ---
    print("\n[1/4] 创建环境...")
    env = Environment(20, 20, resolution=0.25)
    
    # 添加障碍物
    obstacles = [
        (5, 5, 1.5), (10, 3, 1.0), (8, 10, 1.2),
        (14, 7, 1.3), (4, 14, 1.0), (12, 14, 1.5),
        (17, 10, 0.8), (7, 17, 1.0), (16, 16, 1.2),
    ]
    for cx, cy, r in obstacles:
        env.add_circle_obstacle(cx, cy, r)
    print(f"  环境大小: {env.width}x{env.height}m, 障碍物: {len(obstacles)}个")
    
    # --- 2. 路径规划 ---
    print("\n[2/4] A*路径规划...")
    start = (1.0, 1.0)
    goal = (18.0, 18.0)
    
    raw_path = plan_path(env, start, goal)
    if raw_path is None:
        print("  无法找到路径！")
        return
    
    path = smooth_path(raw_path)
    print(f"  原始路径点: {len(raw_path)}, 平滑后: {len(path)}")
    
    # --- 3. 初始化各模块 ---
    print("\n[3/4] 初始化机器人系统...")
    dt = 0.05
    robot = DiffDriveRobot(start[0], start[1], 0)
    localizer = RobotLocalizer(dt)
    localizer.x = np.array([start[0], start[1], 0, 0, 0])
    tracker = PathTracker()
    
    # --- 4. 运行仿真 ---
    print("\n[4/4] 开始仿真...")
    max_steps = 2000
    
    true_path_log = []
    estimated_path_log = []
    observed_path_log = []
    control_log = []
    
    np.random.seed(42)
    
    for step in range(max_steps):
        # 获取估计位姿
        est_x, est_y, est_theta = localizer.get_pose()
        
        # 路径跟踪控制
        v, omega = tracker.compute(est_x, est_y, est_theta, path, dt)
        
        # 执行运动
        robot.move(v, omega, dt)
        
        # 传感器观测
        obs_x, obs_y, obs_theta = robot.get_noisy_observation()
        
        # 卡尔曼滤波
        localizer.predict(v, omega)
        localizer.update(obs_x, obs_y, obs_theta)
        
        # 记录
        true_path_log.append((robot.x, robot.y))
        est_x, est_y, _ = localizer.get_pose()
        estimated_path_log.append((est_x, est_y))
        observed_path_log.append((obs_x, obs_y))
        control_log.append((v, omega))
        
        # 检查是否到达
        if tracker.is_done(est_x, est_y, path):
            print(f"  到达目标！用时 {step * dt:.1f}s ({step}步)")
            break
        
        # 碰撞检测
        if env.is_collision(robot.x, robot.y):
            print(f"  碰撞！步骤 {step}")
            break
    else:
        print(f"  超时（{max_steps}步）")
    
    # --- 可视化 ---
    visualize_simulation(env, obstacles, path, raw_path,
                         true_path_log, estimated_path_log,
                         observed_path_log, control_log,
                         start, goal, dt)


def visualize_simulation(env, obstacles, path, raw_path,
                         true_log, est_log, obs_log, ctrl_log,
                         start, goal, dt):
    """可视化仿真结果"""
    
    fig = plt.figure(figsize=(16, 12))
    
    # --- 主图：导航全景 ---
    ax1 = fig.add_subplot(2, 2, (1, 3))  # 左侧大图
    ax1.set_xlim(-1, env.width + 1)
    ax1.set_ylim(-1, env.height + 1)
    ax1.set_aspect('equal')
    ax1.grid(True, alpha=0.2)
    ax1.set_title('移动机器人自主导航', fontsize=14)
    
    # 画障碍物
    for cx, cy, r in obstacles:
        circle = Circle((cx, cy), r, color='gray', alpha=0.6)
        ax1.add_patch(circle)
    
    # 画路径
    raw_arr = np.array(raw_path)
    path_arr = np.array(path)
    ax1.plot(raw_arr[:, 0], raw_arr[:, 1], 'y-', alpha=0.3, linewidth=1,
             label='A*原始路径')
    ax1.plot(path_arr[:, 0], path_arr[:, 1], 'g--', linewidth=1.5,
             label='平滑路径')
    
    # 画轨迹
    true_arr = np.array(true_log)
    est_arr = np.array(est_log)
    obs_arr = np.array(obs_log)
    
    ax1.scatter(obs_arr[::5, 0], obs_arr[::5, 1], c='red', s=3, alpha=0.2,
                label='传感器观测')
    ax1.plot(true_arr[:, 0], true_arr[:, 1], 'b-', linewidth=2,
             label='真实轨迹')
    ax1.plot(est_arr[:, 0], est_arr[:, 1], 'c-', linewidth=1.5, alpha=0.7,
             label='卡尔曼估计')
    
    # 起点终点
    ax1.plot(*start, 'go', markersize=15, zorder=10, label='起点')
    ax1.plot(*goal, 'r*', markersize=18, zorder=10, label='终点')
    ax1.plot(true_arr[-1, 0], true_arr[-1, 1], 'bs', markersize=10, zorder=10)
    
    ax1.legend(fontsize=9, loc='upper left')
    
    # --- 控制量 ---
    ax2 = fig.add_subplot(2, 2, 2)
    ctrl_arr = np.array(ctrl_log)
    t = np.arange(len(ctrl_log)) * dt
    ax2.plot(t, ctrl_arr[:, 0], 'b-', label='线速度 v')
    ax2.plot(t, ctrl_arr[:, 1], 'r-', alpha=0.7, label='角速度 ω')
    ax2.set_xlabel('时间 (s)')
    ax2.set_ylabel('控制量')
    ax2.set_title('控制信号', fontsize=12)
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    # --- 定位误差 ---
    ax3 = fig.add_subplot(2, 2, 4)
    
    min_len = min(len(true_arr), len(est_arr), len(obs_arr))
    true_arr_t = true_arr[:min_len]
    est_arr_t = est_arr[:min_len]
    obs_arr_t = obs_arr[:min_len]
    
    err_kf = np.sqrt(np.sum((true_arr_t - est_arr_t)**2, axis=1))
    err_obs = np.sqrt(np.sum((true_arr_t - obs_arr_t)**2, axis=1))
    
    t2 = np.arange(min_len) * dt
    ax3.plot(t2, err_obs, 'r-', alpha=0.3, linewidth=0.5, label='观测误差')
    ax3.plot(t2, err_kf, 'b-', linewidth=1.5, label='卡尔曼估计误差')
    ax3.set_xlabel('时间 (s)')
    ax3.set_ylabel('定位误差 (m)')
    ax3.set_title('定位精度对比', fontsize=12)
    ax3.legend()
    ax3.grid(True, alpha=0.3)
    
    avg_obs_err = np.mean(err_obs)
    avg_kf_err = np.mean(err_kf)
    ax3.text(0.95, 0.95, f'观测平均误差: {avg_obs_err:.3f}m\n卡尔曼平均误差: {avg_kf_err:.3f}m',
             transform=ax3.transAxes, ha='right', va='top', fontsize=10,
             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    
    plt.tight_layout()
    plt.savefig('robot_things/05_project/output_08_simulation.png', dpi=120)
    plt.show()
    
    print(f"\n仿真结果:")
    print(f"  观测平均误差: {avg_obs_err:.3f}m")
    print(f"  卡尔曼平均误差: {avg_kf_err:.3f}m")
    print(f"  定位精度提升: {(1 - avg_kf_err/avg_obs_err)*100:.1f}%")
    print(f"\n图片已保存到 robot_things/05_project/output_08_simulation.png")


if __name__ == "__main__":
    run_simulation()
    
    print("\n" + "=" * 60)
    print("📝 进阶挑战：")
    print("1. 添加动态障碍物（移动的行人），实现动态避障")
    print("2. 实现多机器人协同导航")
    print("3. 用粒子滤波替换卡尔曼滤波，处理非高斯噪声")
    print("4. 加入激光雷达模拟，实现简单的SLAM")
    print("=" * 60)
