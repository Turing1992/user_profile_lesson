"""
=============================================================
第7课：PID控制
=============================================================

【什么是PID控制？】
PID是最广泛使用的控制算法，几乎所有机器人都用到它。
它通过三个部分来计算控制量：

P (Proportional，比例): 误差越大，控制力越大
    "离目标远，就使劲推"
    
I (Integral，积分): 累积误差，消除稳态偏差
    "一直有小偏差？慢慢加力修正"
    
D (Derivative，微分): 误差变化率，防止超调
    "快到目标了？减速别冲过头"

控制公式：
    u(t) = Kp * e(t) + Ki * ∫e(t)dt + Kd * de(t)/dt

其中 e(t) = 目标值 - 当前值

【调参口诀】
1. 先调P：从小到大，直到系统能快速响应但不剧烈震荡
2. 再调D：抑制震荡，让系统平稳到达目标
3. 最后调I：消除稳态误差（如果有的话）
"""

import numpy as np
import matplotlib.pyplot as plt


class PIDController:
    """PID控制器"""
    
    def __init__(self, Kp=1.0, Ki=0.0, Kd=0.0, output_limits=None):
        """
        参数:
            Kp: 比例增益
            Ki: 积分增益
            Kd: 微分增益
            output_limits: (min, max) 输出限幅
        """
        self.Kp = Kp
        self.Ki = Ki
        self.Kd = Kd
        self.output_limits = output_limits
        
        self.integral = 0.0
        self.prev_error = 0.0
        self.first_call = True
    
    def reset(self):
        self.integral = 0.0
        self.prev_error = 0.0
        self.first_call = True
    
    def compute(self, error, dt):
        """
        计算PID输出
        
        参数:
            error: 当前误差 (目标 - 实际)
            dt: 时间步长
        返回:
            控制输出
        """
        # P项
        P = self.Kp * error
        
        # I项（积分累积）
        self.integral += error * dt
        I = self.Ki * self.integral
        
        # D项（微分）
        if self.first_call:
            D = 0
            self.first_call = False
        else:
            D = self.Kd * (error - self.prev_error) / dt
        
        self.prev_error = error
        
        # 总输出
        output = P + I + D
        
        # 限幅
        if self.output_limits:
            output = np.clip(output, *self.output_limits)
        
        return output


# ==================== 演示1：理解P、I、D各自的作用 ====================

def demo_pid_components():
    """
    分别展示P、PI、PD、PID的效果
    
    场景：控制一个质量块到达目标位置
    运动方程：m * a = F（力 = 质量 × 加速度）
    """
    print("=" * 50)
    print("演示1：P、I、D各部分的作用")
    print("=" * 50)
    
    dt = 0.02
    n_steps = 500
    target = 10.0  # 目标位置
    mass = 1.0
    damping = 0.5  # 阻尼（模拟摩擦）
    
    configs = [
        ("纯P控制", PIDController(Kp=2.0, Ki=0, Kd=0)),
        ("PI控制", PIDController(Kp=2.0, Ki=0.5, Kd=0)),
        ("PD控制", PIDController(Kp=2.0, Ki=0, Kd=1.5)),
        ("PID控制", PIDController(Kp=2.0, Ki=0.5, Kd=1.5)),
    ]
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    axes = axes.flatten()
    
    for idx, (name, pid) in enumerate(configs):
        positions = []
        velocities = []
        controls = []
        
        pos = 0.0
        vel = 0.0
        
        for i in range(n_steps):
            error = target - pos
            
            # PID计算控制力
            force = pid.compute(error, dt)
            controls.append(force)
            
            # 物理模拟：F = ma + damping
            acc = (force - damping * vel) / mass
            vel += acc * dt
            pos += vel * dt
            
            positions.append(pos)
            velocities.append(vel)
        
        t = np.arange(n_steps) * dt
        
        ax = axes[idx]
        ax.plot(t, positions, 'b-', linewidth=2, label='位置')
        ax.axhline(y=target, color='r', linestyle='--', alpha=0.5, label='目标')
        ax.set_xlabel('时间 (s)')
        ax.set_ylabel('位置')
        ax.set_title(name, fontsize=13)
        ax.legend()
        ax.grid(True, alpha=0.3)
        ax.set_ylim(-2, 18)
        
        # 计算性能指标
        final_error = abs(positions[-1] - target)
        overshoot = max(0, max(positions) - target)
        print(f"{name}: 最终误差={final_error:.3f}, 超调量={overshoot:.2f}")
    
    plt.tight_layout()
    plt.savefig('robot_things/04_control/output_07_pid_components.png', dpi=100)
    plt.show()
    
    print("\n观察：")
    print("- 纯P：有稳态误差（到不了目标）")
    print("- PI：消除稳态误差，但可能震荡")
    print("- PD：快速稳定，但可能有小偏差")
    print("- PID：综合最优")


# ==================== 演示2：移动机器人轨迹跟踪 ====================

def demo_trajectory_tracking():
    """
    用PID控制移动机器人跟踪一条预定轨迹
    
    机器人模型（差速驱动）：
    - 控制量：线速度 v 和角速度 ω
    - 用一个PID控制横向偏差，一个PID控制航向偏差
    """
    print("\n" + "=" * 50)
    print("演示2：移动机器人轨迹跟踪")
    print("=" * 50)
    
    dt = 0.05
    n_steps = 600
    
    # 目标轨迹：8字形
    def reference_trajectory(t):
        x = 5 * np.sin(0.02 * t)
        y = 5 * np.sin(0.04 * t)
        return x, y
    
    # PID控制器
    pid_heading = PIDController(Kp=3.0, Ki=0.1, Kd=0.8)
    
    # 机器人状态
    robot_x, robot_y, robot_theta = -0.5, -0.5, 0.0  # 初始位置有偏差
    base_speed = 2.0
    
    robot_path = []
    ref_path = []
    errors = []
    
    for i in range(n_steps):
        t = i * dt
        
        # 参考点（前方一小段距离的目标点）
        lookahead = 5
        ref_x, ref_y = reference_trajectory(i + lookahead)
        ref_path.append((ref_x, ref_y))
        
        # 计算到目标点的角度
        dx = ref_x - robot_x
        dy = ref_y - robot_y
        target_angle = np.arctan2(dy, dx)
        
        # 航向误差
        heading_error = target_angle - robot_theta
        # 归一化到 [-π, π]
        heading_error = np.arctan2(np.sin(heading_error), np.cos(heading_error))
        
        # PID控制角速度
        omega = pid_heading.compute(heading_error, dt)
        omega = np.clip(omega, -3.0, 3.0)
        
        # 更新机器人状态
        robot_x += base_speed * np.cos(robot_theta) * dt
        robot_y += base_speed * np.sin(robot_theta) * dt
        robot_theta += omega * dt
        
        robot_path.append((robot_x, robot_y))
        
        # 跟踪误差
        actual_ref_x, actual_ref_y = reference_trajectory(i)
        err = np.sqrt((robot_x - actual_ref_x)**2 + (robot_y - actual_ref_y)**2)
        errors.append(err)
    
    # 可视化
    robot_arr = np.array(robot_path)
    
    # 完整参考轨迹
    ref_t = np.arange(n_steps)
    ref_full = np.array([reference_trajectory(t) for t in ref_t])
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    
    ax1.plot(ref_full[:, 0], ref_full[:, 1], 'r--', linewidth=1, alpha=0.5, label='参考轨迹')
    ax1.plot(robot_arr[:, 0], robot_arr[:, 1], 'b-', linewidth=2, label='实际轨迹')
    ax1.plot(robot_arr[0, 0], robot_arr[0, 1], 'go', markersize=10, label='起点')
    ax1.set_aspect('equal')
    ax1.grid(True, alpha=0.3)
    ax1.set_title('轨迹跟踪效果', fontsize=14)
    ax1.legend(fontsize=11)
    
    t = np.arange(n_steps) * dt
    ax2.plot(t, errors, 'b-', linewidth=1)
    ax2.set_xlabel('时间 (s)')
    ax2.set_ylabel('跟踪误差')
    ax2.set_title('跟踪误差随时间变化', fontsize=14)
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('robot_things/04_control/output_07_tracking.png', dpi=100)
    plt.show()
    
    print(f"平均跟踪误差: {np.mean(errors):.3f}")
    print(f"最大跟踪误差: {np.max(errors):.3f}")


# ==================== 演示3：PID调参对比 ====================

def demo_tuning():
    """
    展示不同PID参数对系统响应的影响
    
    这是实际工程中最重要的技能：调参
    """
    print("\n" + "=" * 50)
    print("演示3：PID调参对比")
    print("=" * 50)
    
    dt = 0.02
    n_steps = 400
    target = 10.0
    mass = 1.0
    damping = 0.3
    
    param_sets = [
        ("Kp过小 (欠阻尼)", 0.5, 0, 0, '#FF6B6B'),
        ("Kp适中", 2.0, 0, 0, '#4ECDC4'),
        ("Kp过大 (震荡)", 8.0, 0, 0, '#45B7D1'),
        ("加D抑制震荡", 8.0, 0, 3.0, '#96CEB4'),
        ("完整PID", 5.0, 0.3, 2.0, '#2196F3'),
    ]
    
    fig, ax = plt.subplots(figsize=(12, 6))
    
    for name, kp, ki, kd, color in param_sets:
        pid = PIDController(Kp=kp, Ki=ki, Kd=kd)
        positions = []
        pos, vel = 0.0, 0.0
        
        for i in range(n_steps):
            error = target - pos
            force = pid.compute(error, dt)
            acc = (force - damping * vel) / mass
            vel += acc * dt
            pos += vel * dt
            positions.append(pos)
        
        t = np.arange(n_steps) * dt
        ax.plot(t, positions, color=color, linewidth=2, label=name)
    
    ax.axhline(y=target, color='black', linestyle='--', alpha=0.3, label='目标')
    ax.set_xlabel('时间 (s)', fontsize=12)
    ax.set_ylabel('位置', fontsize=12)
    ax.set_title('PID调参对比', fontsize=14)
    ax.legend(fontsize=10, loc='lower right')
    ax.grid(True, alpha=0.3)
    ax.set_ylim(-2, 20)
    
    plt.tight_layout()
    plt.savefig('robot_things/04_control/output_07_tuning.png', dpi=100)
    plt.show()
    
    print("调参要点：")
    print("- Kp太小：响应慢，到不了目标")
    print("- Kp太大：震荡")
    print("- 加Kd：抑制震荡")
    print("- 加Ki：消除稳态误差")


if __name__ == "__main__":
    print("🤖 第7课：PID控制")
    print("=" * 50)
    
    demo_pid_components()
    demo_trajectory_tracking()
    demo_tuning()
    
    print("\n" + "=" * 50)
    print("📝 课后练习：")
    print("1. 修改PID参数，尝试让轨迹跟踪误差更小")
    print("2. 给系统加入外部扰动（比如突然的推力），观察PID如何恢复")
    print("3. 实现一个自动调参算法（比如Ziegler-Nichols方法）")
    print("=" * 50)
