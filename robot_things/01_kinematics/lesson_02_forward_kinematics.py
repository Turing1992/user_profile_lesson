"""
=============================================================
第2课：正运动学 (Forward Kinematics)
=============================================================

【什么是正运动学？】
已知每个关节的角度 → 求末端执行器的位置和朝向
这是"从关节空间到笛卡尔空间"的映射。

【DH参数法】(Denavit-Hartenberg)
工业界描述机器人关节的标准方法。
每个关节用4个参数描述：
- θ (theta): 关节角度（旋转关节的变量）
- d: 沿Z轴的偏移
- a: 连杆长度（沿X轴）
- α (alpha): 连杆扭转角

对于2D平面机器人，我们只需要 θ 和 a。

【本课目标】
实现一个通用的N连杆平面机器人正运动学求解器，
并可视化机器人在不同关节角度下的姿态。
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider


def forward_kinematics_2d(joint_angles, link_lengths):
    """
    2D平面机器人的正运动学
    
    参数:
        joint_angles: 各关节角度列表 [θ1, θ2, ..., θn]（弧度）
        link_lengths: 各连杆长度列表 [L1, L2, ..., Ln]
    
    返回:
        positions: 各关节位置列表 [(x0,y0), (x1,y1), ..., (xn,yn)]
                   其中 (x0,y0) 是基座，(xn,yn) 是末端
        total_angle: 末端执行器的总朝向角
    
    算法：
    累积角度法 —— 每个关节的绝对角度 = 之前所有关节角度之和
    """
    n = len(joint_angles)
    positions = [(0.0, 0.0)]  # 基座在原点
    
    cumulative_angle = 0.0  # 累积角度
    x, y = 0.0, 0.0
    
    for i in range(n):
        cumulative_angle += joint_angles[i]
        # 沿当前方向前进 link_lengths[i]
        x += link_lengths[i] * np.cos(cumulative_angle)
        y += link_lengths[i] * np.sin(cumulative_angle)
        positions.append((x, y))
    
    return positions, cumulative_angle


def workspace_analysis(link_lengths, resolution=100):
    """
    工作空间分析：机器人末端能到达的所有位置
    
    通过遍历所有可能的关节角度组合，
    找出末端执行器能到达的区域。
    
    这对于机器人设计很重要 —— 你需要知道机器人能够到哪里。
    """
    n = len(link_lengths)
    
    if n == 2:
        # 两连杆：遍历 θ1 和 θ2
        points = []
        for theta1 in np.linspace(0, 2 * np.pi, resolution):
            for theta2 in np.linspace(0, 2 * np.pi, resolution):
                positions, _ = forward_kinematics_2d(
                    [theta1, theta2], link_lengths
                )
                points.append(positions[-1])
        return np.array(points)
    elif n == 3:
        # 三连杆：采样（完全遍历太慢）
        points = []
        for theta1 in np.linspace(0, 2 * np.pi, 40):
            for theta2 in np.linspace(0, 2 * np.pi, 40):
                for theta3 in np.linspace(0, 2 * np.pi, 20):
                    positions, _ = forward_kinematics_2d(
                        [theta1, theta2, theta3], link_lengths
                    )
                    points.append(positions[-1])
        return np.array(points)
    return np.array([])


# ==================== 演示1：正运动学计算 ====================

def demo_forward_kinematics():
    """
    演示不同关节角度下机器人的姿态
    """
    print("=" * 50)
    print("演示1：正运动学 —— 不同姿态")
    print("=" * 50)
    
    link_lengths = [3.0, 2.0, 1.5]  # 三连杆
    
    # 定义几组关节角度
    configs = [
        ("伸直", [0, 0, 0]),
        ("L形", [np.pi/4, -np.pi/2, 0]),
        ("折叠", [np.pi/3, -2*np.pi/3, np.pi/2]),
        ("向下", [-np.pi/4, -np.pi/4, -np.pi/4]),
    ]
    
    fig, axes = plt.subplots(2, 2, figsize=(12, 12))
    axes = axes.flatten()
    
    for idx, (name, angles) in enumerate(configs):
        positions, end_angle = forward_kinematics_2d(angles, link_lengths)
        
        ax = axes[idx]
        limit = sum(link_lengths) + 1
        ax.set_xlim(-limit, limit)
        ax.set_ylim(-limit, limit)
        ax.set_aspect('equal')
        ax.grid(True, alpha=0.3)
        
        # 画连杆
        xs = [p[0] for p in positions]
        ys = [p[1] for p in positions]
        ax.plot(xs, ys, 'o-', linewidth=3, markersize=8, color='#2196F3')
        
        # 标记基座和末端
        ax.plot(xs[0], ys[0], 's', color='black', markersize=12, zorder=5)
        ax.plot(xs[-1], ys[-1], '*', color='red', markersize=15, zorder=5)
        
        # 标注末端位置
        end = positions[-1]
        angle_degs = [f"{np.degrees(a):.0f}°" for a in angles]
        ax.set_title(f'{name}\n关节角: {angle_degs}\n末端: ({end[0]:.2f}, {end[1]:.2f})',
                     fontsize=11)
        
        print(f"\n{name}:")
        print(f"  关节角度: {angle_degs}")
        print(f"  末端位置: ({end[0]:.2f}, {end[1]:.2f})")
        print(f"  末端朝向: {np.degrees(end_angle):.1f}°")
    
    plt.tight_layout()
    plt.savefig('robot_things/01_kinematics/output_02_fk.png', dpi=100)
    plt.show()
    print("\n图片已保存")


# ==================== 演示2：工作空间 ====================

def demo_workspace():
    """
    可视化机器人的工作空间
    
    工作空间 = 末端执行器能到达的所有点的集合
    
    对于两连杆机器人：
    - 如果 L1 > L2：工作空间是一个环形区域
      内半径 = L1 - L2，外半径 = L1 + L2
    - 如果 L1 = L2：工作空间是一个圆盘（能到达原点）
    """
    print("\n" + "=" * 50)
    print("演示2：工作空间分析")
    print("=" * 50)
    
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    
    # 情况1：L1 ≠ L2（环形工作空间）
    L = [3.0, 2.0]
    points = workspace_analysis(L, resolution=80)
    axes[0].scatter(points[:, 0], points[:, 1], s=0.5, alpha=0.3, c='blue')
    axes[0].set_title(f'工作空间: L1={L[0]}, L2={L[1]}\n(环形: 内径={abs(L[0]-L[1])}, 外径={sum(L)})',
                      fontsize=12)
    axes[0].set_aspect('equal')
    axes[0].grid(True, alpha=0.3)
    
    # 画理论边界
    theta = np.linspace(0, 2*np.pi, 100)
    r_outer = sum(L)
    r_inner = abs(L[0] - L[1])
    axes[0].plot(r_outer*np.cos(theta), r_outer*np.sin(theta), 'r--', label='外边界')
    axes[0].plot(r_inner*np.cos(theta), r_inner*np.sin(theta), 'g--', label='内边界')
    axes[0].legend()
    
    # 情况2：L1 = L2（圆盘工作空间）
    L = [2.5, 2.5]
    points = workspace_analysis(L, resolution=80)
    axes[1].scatter(points[:, 0], points[:, 1], s=0.5, alpha=0.3, c='orange')
    axes[1].set_title(f'工作空间: L1={L[0]}, L2={L[1]}\n(圆盘: 半径={sum(L)})',
                      fontsize=12)
    axes[1].set_aspect('equal')
    axes[1].grid(True, alpha=0.3)
    
    r_outer = sum(L)
    axes[1].plot(r_outer*np.cos(theta), r_outer*np.sin(theta), 'r--', label='外边界')
    axes[1].legend()
    
    plt.tight_layout()
    plt.savefig('robot_things/01_kinematics/output_02_workspace.png', dpi=100)
    plt.show()
    
    print("L1≠L2 时工作空间是环形，L1=L2 时是圆盘")
    print("图片已保存")


# ==================== 演示3：交互式滑块 ====================

def demo_interactive():
    """
    交互式演示：拖动滑块改变关节角度，实时看到机器人运动
    
    这个演示需要 matplotlib 的交互模式，
    如果在某些环境下不工作，可以跳过。
    """
    print("\n" + "=" * 50)
    print("演示3：交互式正运动学（拖动滑块）")
    print("=" * 50)
    
    link_lengths = [3.0, 2.5, 1.5]
    
    fig, ax = plt.subplots(figsize=(8, 8))
    plt.subplots_adjust(bottom=0.3)
    
    limit = sum(link_lengths) + 1
    
    # 初始角度
    init_angles = [0.5, -0.3, 0.2]
    
    # 初始绘制
    positions, _ = forward_kinematics_2d(init_angles, link_lengths)
    xs = [p[0] for p in positions]
    ys = [p[1] for p in positions]
    line, = ax.plot(xs, ys, 'o-', linewidth=3, markersize=10, color='#2196F3')
    end_marker, = ax.plot(xs[-1], ys[-1], '*', color='red', markersize=20, zorder=5)
    
    ax.set_xlim(-limit, limit)
    ax.set_ylim(-limit, limit)
    ax.set_aspect('equal')
    ax.grid(True, alpha=0.3)
    ax.set_title('拖动下方滑块改变关节角度', fontsize=14)
    
    # 创建滑块
    ax_s1 = plt.axes([0.2, 0.18, 0.6, 0.03])
    ax_s2 = plt.axes([0.2, 0.12, 0.6, 0.03])
    ax_s3 = plt.axes([0.2, 0.06, 0.6, 0.03])
    
    s1 = Slider(ax_s1, 'θ1 (°)', -180, 180, valinit=np.degrees(init_angles[0]))
    s2 = Slider(ax_s2, 'θ2 (°)', -180, 180, valinit=np.degrees(init_angles[1]))
    s3 = Slider(ax_s3, 'θ3 (°)', -180, 180, valinit=np.degrees(init_angles[2]))
    
    def update(val):
        angles = [np.radians(s1.val), np.radians(s2.val), np.radians(s3.val)]
        positions, _ = forward_kinematics_2d(angles, link_lengths)
        xs = [p[0] for p in positions]
        ys = [p[1] for p in positions]
        line.set_data(xs, ys)
        end_marker.set_data([xs[-1]], [ys[-1]])
        fig.canvas.draw_idle()
    
    s1.on_changed(update)
    s2.on_changed(update)
    s3.on_changed(update)
    
    plt.savefig('robot_things/01_kinematics/output_02_interactive.png', dpi=100)
    plt.show()
    print("提示：在弹出的窗口中拖动滑块来控制机器人手臂")


# ==================== 主程序 ====================

if __name__ == "__main__":
    print("🤖 第2课：正运动学")
    print("=" * 50)
    
    demo_forward_kinematics()
    demo_workspace()
    demo_interactive()
    
    print("\n" + "=" * 50)
    print("📝 课后练习：")
    print("1. 增加到4个连杆，观察工作空间如何变化")
    print("2. 如果所有连杆等长，工作空间有什么特点？")
    print("3. 思考：给定末端位置，如何反过来求关节角度？（下节课的内容）")
    print("=" * 50)
