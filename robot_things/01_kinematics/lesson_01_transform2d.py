"""
=============================================================
第1课：2D坐标变换 —— 机器人学的数学基础
=============================================================

【为什么要学这个？】
机器人在空间中运动，我们需要描述它的位置和朝向。
比如：机器人在世界坐标系中的位置是 (3, 5)，朝向是 45°。
坐标变换就是在不同坐标系之间"翻译"位置信息的工具。

【核心概念】
1. 平移 (Translation): 移动位置，不改变朝向
2. 旋转 (Rotation): 改变朝向，不改变位置
3. 齐次变换矩阵: 把平移和旋转统一成一个矩阵乘法

【齐次变换矩阵 (3x3)】
    | cos(θ)  -sin(θ)  tx |
T = | sin(θ)   cos(θ)  ty |
    |   0        0      1 |

其中 θ 是旋转角度，(tx, ty) 是平移量。
"""

import numpy as np
import matplotlib.pyplot as plt


# ==================== 基础工具函数 ====================

def rotation_matrix_2d(theta):
    """
    创建2D旋转矩阵
    
    参数:
        theta: 旋转角度（弧度）
    返回:
        2x2 旋转矩阵
    
    数学原理：
    旋转矩阵将一个向量绕原点旋转 θ 角度
    | cos(θ)  -sin(θ) |   | x |   | x*cos(θ) - y*sin(θ) |
    | sin(θ)   cos(θ) | × | y | = | x*sin(θ) + y*cos(θ) |
    """
    c, s = np.cos(theta), np.sin(theta)
    return np.array([
        [c, -s],
        [s,  c]
    ])


def homogeneous_transform_2d(theta, tx, ty):
    """
    创建2D齐次变换矩阵
    
    参数:
        theta: 旋转角度（弧度）
        tx, ty: 平移量
    返回:
        3x3 齐次变换矩阵
    
    为什么用齐次坐标？
    普通矩阵乘法无法同时表示旋转+平移，
    但如果我们把 (x, y) 扩展成 (x, y, 1)，
    就可以用一个矩阵搞定所有变换！
    """
    c, s = np.cos(theta), np.sin(theta)
    return np.array([
        [c, -s, tx],
        [s,  c, ty],
        [0,  0,  1]
    ])


def transform_point(T, point):
    """
    用变换矩阵 T 变换一个2D点
    
    参数:
        T: 3x3 齐次变换矩阵
        point: (x, y) 坐标
    返回:
        变换后的 (x, y) 坐标
    """
    # 把 (x, y) 变成齐次坐标 (x, y, 1)
    p = np.array([point[0], point[1], 1.0])
    # 矩阵乘法
    result = T @ p
    # 返回前两个分量
    return result[:2]


# ==================== 可视化工具 ====================

def plot_frame(ax, T, label="", length=1.0, colors=('r', 'b')):
    """
    在图上画一个坐标系
    
    红色箭头 = X轴方向
    蓝色箭头 = Y轴方向
    """
    origin = T[:2, 2]  # 提取平移部分，即坐标系原点
    x_axis = T[:2, 0] * length  # X轴方向（旋转矩阵第一列）
    y_axis = T[:2, 1] * length  # Y轴方向（旋转矩阵第二列）
    
    ax.arrow(origin[0], origin[1], x_axis[0], x_axis[1],
             head_width=0.1, head_length=0.08, fc=colors[0], ec=colors[0])
    ax.arrow(origin[0], origin[1], y_axis[0], y_axis[1],
             head_width=0.1, head_length=0.08, fc=colors[1], ec=colors[1])
    
    if label:
        ax.text(origin[0] - 0.3, origin[1] - 0.3, label, fontsize=10,
                fontweight='bold')


# ==================== 演示1：基本变换 ====================

def demo_basic_transforms():
    """
    演示平移、旋转、以及组合变换
    """
    print("=" * 50)
    print("演示1：基本的2D变换")
    print("=" * 50)
    
    # --- 纯平移 ---
    # 向右移动3，向上移动2
    T_translate = homogeneous_transform_2d(0, 3, 2)
    print("\n纯平移矩阵 (右移3, 上移2):")
    print(T_translate)
    
    # 变换一个点
    p = (1, 1)
    p_new = transform_point(T_translate, p)
    print(f"点 {p} 经过平移后 → ({p_new[0]:.1f}, {p_new[1]:.1f})")
    # 预期：(1+3, 1+2) = (4, 3) ✓
    
    # --- 纯旋转 ---
    # 旋转90度（π/2弧度）
    theta = np.pi / 2
    T_rotate = homogeneous_transform_2d(theta, 0, 0)
    print(f"\n纯旋转矩阵 (旋转90°):")
    print(np.round(T_rotate, 4))
    
    p_new = transform_point(T_rotate, p)
    print(f"点 {p} 经过旋转后 → ({p_new[0]:.1f}, {p_new[1]:.1f})")
    # 预期：(1,1) 旋转90° → (-1, 1) ✓
    
    # --- 组合变换：先旋转再平移 ---
    # 关键理解：矩阵乘法的顺序很重要！
    # T_combined = T_translate @ T_rotate 表示"先旋转，再平移"
    T_combined = T_translate @ T_rotate
    print(f"\n组合变换 (先旋转90°，再平移(3,2)):")
    print(np.round(T_combined, 4))
    
    p_new = transform_point(T_combined, p)
    print(f"点 {p} 经过组合变换后 → ({p_new[0]:.2f}, {p_new[1]:.2f})")
    # 先旋转：(1,1) → (-1,1)，再平移：(-1+3, 1+2) = (2, 3) ✓
    
    # --- 可视化 ---
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    
    # 世界坐标系（不动的参考系）
    T_world = np.eye(3)
    
    for ax in axes:
        ax.set_xlim(-2, 6)
        ax.set_ylim(-2, 6)
        ax.set_aspect('equal')
        ax.grid(True, alpha=0.3)
    
    # 图1：纯平移
    axes[0].set_title('纯平移 (tx=3, ty=2)', fontsize=12)
    plot_frame(axes[0], T_world, "世界坐标系")
    plot_frame(axes[0], T_translate, "平移后")
    
    # 图2：纯旋转
    axes[1].set_title('纯旋转 (θ=90°)', fontsize=12)
    plot_frame(axes[1], T_world, "世界坐标系")
    plot_frame(axes[1], T_rotate, "旋转后")
    
    # 图3：组合变换
    axes[2].set_title('先旋转90°再平移(3,2)', fontsize=12)
    plot_frame(axes[2], T_world, "世界坐标系")
    plot_frame(axes[2], T_combined, "组合变换后")
    
    plt.tight_layout()
    plt.savefig('robot_things/01_kinematics/output_01_transforms.png', dpi=100)
    plt.show()
    print("\n图片已保存到 robot_things/01_kinematics/output_01_transforms.png")


# ==================== 演示2：变换链 ====================

def demo_transform_chain():
    """
    演示变换链 —— 机器人手臂的核心思想
    
    想象一个简单的机器人手臂：
    - 基座在世界坐标系原点
    - 第一个关节旋转 θ1，臂长 L1
    - 第二个关节旋转 θ2，臂长 L2
    - 末端执行器（手）在哪里？
    
    答案：把每个关节的变换矩阵依次相乘！
    T_hand = T_joint1 @ T_link1 @ T_joint2 @ T_link2
    """
    print("\n" + "=" * 50)
    print("演示2：变换链 —— 两连杆机器人手臂")
    print("=" * 50)
    
    # 机器人参数
    L1 = 3.0  # 第一段臂长
    L2 = 2.0  # 第二段臂长
    theta1 = np.radians(45)   # 第一个关节角度：45°
    theta2 = np.radians(-30)  # 第二个关节角度：-30°
    
    # 构建变换链
    # 第一个关节：在原点旋转 θ1
    T_joint1 = homogeneous_transform_2d(theta1, 0, 0)
    
    # 第一段连杆：沿（局部）X轴平移 L1
    T_link1 = homogeneous_transform_2d(0, L1, 0)
    
    # 第二个关节：旋转 θ2
    T_joint2 = homogeneous_transform_2d(theta2, 0, 0)
    
    # 第二段连杆：沿（局部）X轴平移 L2
    T_link2 = homogeneous_transform_2d(0, L2, 0)
    
    # 计算各个位置
    T_elbow = T_joint1 @ T_link1                          # 肘关节位置
    T_hand = T_joint1 @ T_link1 @ T_joint2 @ T_link2      # 手的位置
    
    # 提取坐标
    base = np.array([0, 0])
    elbow = T_elbow[:2, 2]
    hand = T_hand[:2, 2]
    
    print(f"关节角度: θ1={np.degrees(theta1):.0f}°, θ2={np.degrees(theta2):.0f}°")
    print(f"臂长: L1={L1}, L2={L2}")
    print(f"基座位置: ({base[0]:.2f}, {base[1]:.2f})")
    print(f"肘关节位置: ({elbow[0]:.2f}, {elbow[1]:.2f})")
    print(f"手的位置: ({hand[0]:.2f}, {hand[1]:.2f})")
    
    # 可视化
    fig, ax = plt.subplots(1, 1, figsize=(8, 8))
    ax.set_xlim(-6, 6)
    ax.set_ylim(-6, 6)
    ax.set_aspect('equal')
    ax.grid(True, alpha=0.3)
    ax.set_title(f'两连杆机器人手臂\nθ1={np.degrees(theta1):.0f}°, θ2={np.degrees(theta2):.0f}°',
                 fontsize=14)
    
    # 画连杆
    ax.plot([base[0], elbow[0]], [base[1], elbow[1]], 'o-',
            color='#2196F3', linewidth=4, markersize=10, label=f'连杆1 (L={L1})')
    ax.plot([elbow[0], hand[0]], [elbow[1], hand[1]], 'o-',
            color='#FF9800', linewidth=4, markersize=10, label=f'连杆2 (L={L2})')
    
    # 标记关节
    ax.plot(*base, 's', color='black', markersize=15, zorder=5, label='基座')
    ax.plot(*hand, '*', color='red', markersize=20, zorder=5, label='末端执行器')
    
    # 画坐标系
    T_world = np.eye(3)
    plot_frame(ax, T_world, "世界", length=0.8)
    plot_frame(ax, T_elbow, "肘", length=0.6)
    plot_frame(ax, T_hand, "手", length=0.6)
    
    ax.legend(fontsize=11, loc='upper left')
    plt.tight_layout()
    plt.savefig('robot_things/01_kinematics/output_01_arm.png', dpi=100)
    plt.show()
    print("图片已保存到 robot_things/01_kinematics/output_01_arm.png")


# ==================== 演示3：逆变换 ====================

def demo_inverse_transform():
    """
    逆变换：已知世界坐标系中的点，求它在机器人坐标系中的坐标
    
    应用场景：
    机器人看到一个目标在世界坐标 (5, 3)，
    机器人自己在世界坐标 (2, 1) 朝向 30°，
    那么目标相对于机器人在哪个方向、多远？
    """
    print("\n" + "=" * 50)
    print("演示3：逆变换 —— 从世界坐标到机器人坐标")
    print("=" * 50)
    
    # 机器人在世界坐标系中的位姿
    robot_x, robot_y = 2.0, 1.0
    robot_theta = np.radians(30)
    
    # 世界坐标系 → 机器人坐标系的变换
    T_world_robot = homogeneous_transform_2d(robot_theta, robot_x, robot_y)
    
    # 逆变换：机器人坐标系 → 世界坐标系
    T_robot_world = np.linalg.inv(T_world_robot)
    
    # 目标在世界坐标系中的位置
    target_world = (5, 3)
    
    # 目标在机器人坐标系中的位置
    target_robot = transform_point(T_robot_world, target_world)
    
    print(f"机器人位姿: x={robot_x}, y={robot_y}, θ={np.degrees(robot_theta):.0f}°")
    print(f"目标世界坐标: {target_world}")
    print(f"目标在机器人坐标系中: ({target_robot[0]:.2f}, {target_robot[1]:.2f})")
    
    # 计算距离和方向
    distance = np.linalg.norm(target_robot)
    angle = np.degrees(np.arctan2(target_robot[1], target_robot[0]))
    print(f"目标距离机器人: {distance:.2f}")
    print(f"目标相对机器人的方向: {angle:.1f}°")


# ==================== 主程序 ====================

if __name__ == "__main__":
    print("🤖 第1课：2D坐标变换")
    print("=" * 50)
    
    demo_basic_transforms()
    demo_transform_chain()
    demo_inverse_transform()
    
    print("\n" + "=" * 50)
    print("📝 课后练习：")
    print("1. 修改 demo_transform_chain 中的 theta1 和 theta2，观察手臂变化")
    print("2. 试试把变换顺序反过来（先平移再旋转），结果有什么不同？")
    print("3. 给机器人手臂加第三个关节，变成三连杆")
    print("=" * 50)
