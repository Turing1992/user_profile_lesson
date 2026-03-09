"""
=============================================================
第3课：逆运动学 (Inverse Kinematics)
=============================================================

【什么是逆运动学？】
正运动学的反问题：
已知末端执行器的目标位置 → 求各关节角度

这比正运动学难得多，因为：
1. 可能无解（目标超出工作空间）
2. 可能有多个解（多种姿态都能到达同一点）
3. 没有通用的解析解（连杆多了只能用数值方法）

【本课内容】
1. 两连杆的解析解（几何法）
2. 雅可比矩阵法（数值迭代，适用于任意连杆数）
3. CCD方法（循环坐标下降，简单直观）
"""

import numpy as np
import matplotlib.pyplot as plt


def forward_kinematics_2d(joint_angles, link_lengths):
    """正运动学（复用上节课的代码）"""
    positions = [(0.0, 0.0)]
    cumulative_angle = 0.0
    x, y = 0.0, 0.0
    for i in range(len(joint_angles)):
        cumulative_angle += joint_angles[i]
        x += link_lengths[i] * np.cos(cumulative_angle)
        y += link_lengths[i] * np.sin(cumulative_angle)
        positions.append((x, y))
    return positions, cumulative_angle


# ==================== 方法1：解析法（两连杆） ====================

def ik_analytical_2link(target_x, target_y, L1, L2, elbow_up=True):
    """
    两连杆机器人的解析逆运动学（几何法）
    
    原理（余弦定理）：
    目标距离 d = sqrt(x² + y²)
    
    由余弦定理：
    d² = L1² + L2² - 2*L1*L2*cos(π - θ2)
       = L1² + L2² + 2*L1*L2*cos(θ2)
    
    所以：
    cos(θ2) = (d² - L1² - L2²) / (2*L1*L2)
    
    θ1 可以通过 atan2 求得。
    
    参数:
        target_x, target_y: 目标位置
        L1, L2: 连杆长度
        elbow_up: True=肘部朝上的解，False=肘部朝下的解
    
    返回:
        (theta1, theta2) 或 None（无解时）
    """
    d_sq = target_x**2 + target_y**2
    d = np.sqrt(d_sq)
    
    # 检查是否可达
    if d > L1 + L2:
        print(f"  ✗ 目标 ({target_x:.1f}, {target_y:.1f}) 超出工作空间 (d={d:.2f} > {L1+L2})")
        return None
    if d < abs(L1 - L2):
        print(f"  ✗ 目标 ({target_x:.1f}, {target_y:.1f}) 在死区内 (d={d:.2f} < {abs(L1-L2)})")
        return None
    
    # 求 θ2
    cos_theta2 = (d_sq - L1**2 - L2**2) / (2 * L1 * L2)
    cos_theta2 = np.clip(cos_theta2, -1, 1)  # 数值安全
    
    if elbow_up:
        theta2 = np.arccos(cos_theta2)
    else:
        theta2 = -np.arccos(cos_theta2)
    
    # 求 θ1
    # θ1 = atan2(y, x) - atan2(L2*sin(θ2), L1 + L2*cos(θ2))
    alpha = np.arctan2(target_y, target_x)
    beta = np.arctan2(L2 * np.sin(theta2), L1 + L2 * np.cos(theta2))
    theta1 = alpha - beta
    
    return theta1, theta2


# ==================== 方法2：雅可比矩阵法 ====================

def jacobian_2d(joint_angles, link_lengths):
    """
    计算2D平面机器人的雅可比矩阵
    
    雅可比矩阵 J 描述了"关节速度"到"末端速度"的映射：
    [dx/dt]       [dθ1/dt]
    [dy/dt] = J × [dθ2/dt]
                   [  ...  ]
    
    J 的每一列是：如果只转动第 i 个关节，末端会怎么动
    
    J[0][i] = -Σ(Lk * sin(Σθ))  (x方向的偏导数)
    J[1][i] =  Σ(Lk * cos(Σθ))  (y方向的偏导数)
    """
    n = len(joint_angles)
    J = np.zeros((2, n))
    
    for i in range(n):
        for j in range(i, n):
            angle_sum = sum(joint_angles[:j+1])
            J[0][i] += -link_lengths[j] * np.sin(angle_sum)
            J[1][i] +=  link_lengths[j] * np.cos(angle_sum)
    
    return J


def ik_jacobian(target, link_lengths, max_iter=200, tol=0.01, alpha=0.5):
    """
    基于雅可比矩阵的逆运动学（数值迭代法）
    
    算法：
    1. 从初始角度开始
    2. 计算当前末端位置
    3. 计算误差 = 目标位置 - 当前位置
    4. 用雅可比伪逆计算关节角度调整量
    5. 更新关节角度
    6. 重复直到误差足够小
    
    参数:
        target: (x, y) 目标位置
        link_lengths: 连杆长度列表
        max_iter: 最大迭代次数
        tol: 收敛容差
        alpha: 步长（太大会震荡，太小会慢）
    
    返回:
        joint_angles: 求解得到的关节角度
        trajectory: 迭代过程中末端的轨迹（用于可视化）
        success: 是否收敛
    """
    n = len(link_lengths)
    # 初始角度（随机小角度，避免奇异位形）
    joint_angles = np.random.uniform(-0.5, 0.5, n)
    
    target = np.array(target)
    trajectory = []
    
    for iteration in range(max_iter):
        # 当前末端位置
        positions, _ = forward_kinematics_2d(joint_angles, link_lengths)
        current = np.array(positions[-1])
        trajectory.append(current.copy())
        
        # 计算误差
        error = target - current
        error_norm = np.linalg.norm(error)
        
        if error_norm < tol:
            print(f"  ✓ 收敛！迭代 {iteration} 次，误差 {error_norm:.6f}")
            return joint_angles, trajectory, True
        
        # 计算雅可比矩阵
        J = jacobian_2d(joint_angles, link_lengths)
        
        # 雅可比伪逆（处理非方阵和奇异情况）
        # J_pinv = J^T (J J^T)^{-1}
        # 加一个小的正则化项避免奇异
        J_pinv = J.T @ np.linalg.inv(J @ J.T + 1e-6 * np.eye(2))
        
        # 更新关节角度
        delta_theta = alpha * J_pinv @ error
        joint_angles += delta_theta
    
    print(f"  ✗ 未收敛，最终误差 {error_norm:.4f}")
    return joint_angles, trajectory, False


# ==================== 方法3：CCD（循环坐标下降） ====================

def ik_ccd(target, link_lengths, max_iter=100, tol=0.01):
    """
    CCD (Cyclic Coordinate Descent) 逆运动学
    
    这是最直观的方法，常用于游戏和动画：
    
    算法：
    从最后一个关节开始，逐个调整每个关节，
    让末端尽量靠近目标。循环多次直到收敛。
    
    每次调整一个关节时：
    1. 计算"关节→末端"的向量
    2. 计算"关节→目标"的向量
    3. 旋转关节，让这两个向量对齐
    
    优点：简单、直观、不需要矩阵求逆
    缺点：收敛可能慢，不保证最优解
    """
    n = len(link_lengths)
    joint_angles = np.zeros(n)
    target = np.array(target)
    trajectory = []
    
    for iteration in range(max_iter):
        # 从最后一个关节到第一个关节
        for i in range(n - 1, -1, -1):
            positions, _ = forward_kinematics_2d(joint_angles, link_lengths)
            
            # 当前关节位置
            joint_pos = np.array(positions[i])
            # 当前末端位置
            end_pos = np.array(positions[-1])
            
            # 关节→末端 的角度
            to_end = end_pos - joint_pos
            angle_to_end = np.arctan2(to_end[1], to_end[0])
            
            # 关节→目标 的角度
            to_target = target - joint_pos
            angle_to_target = np.arctan2(to_target[1], to_target[0])
            
            # 需要旋转的角度
            delta = angle_to_target - angle_to_end
            
            # 归一化到 [-π, π]
            delta = np.arctan2(np.sin(delta), np.cos(delta))
            
            # 调整当前关节
            joint_angles[i] += delta
        
        # 检查收敛
        positions, _ = forward_kinematics_2d(joint_angles, link_lengths)
        end_pos = np.array(positions[-1])
        trajectory.append(end_pos.copy())
        
        error = np.linalg.norm(target - end_pos)
        if error < tol:
            print(f"  ✓ CCD收敛！迭代 {iteration} 次，误差 {error:.6f}")
            return joint_angles, trajectory, True
    
    print(f"  ✗ CCD未收敛，最终误差 {error:.4f}")
    return joint_angles, trajectory, False


# ==================== 可视化工具 ====================

def plot_arm(ax, joint_angles, link_lengths, color='#2196F3', label=None):
    """画一个机器人手臂"""
    positions, _ = forward_kinematics_2d(joint_angles, link_lengths)
    xs = [p[0] for p in positions]
    ys = [p[1] for p in positions]
    ax.plot(xs, ys, 'o-', linewidth=3, markersize=8, color=color, label=label)
    ax.plot(xs[0], ys[0], 's', color='black', markersize=12, zorder=5)
    ax.plot(xs[-1], ys[-1], '*', color=color, markersize=15, zorder=5)


# ==================== 演示 ====================

def demo_analytical():
    """演示两连杆解析逆运动学"""
    print("=" * 50)
    print("演示1：两连杆解析逆运动学")
    print("=" * 50)
    
    L1, L2 = 3.0, 2.0
    target = (3.5, 2.0)
    
    print(f"\n目标位置: {target}")
    print(f"连杆长度: L1={L1}, L2={L2}")
    
    # 两个解
    sol_up = ik_analytical_2link(target[0], target[1], L1, L2, elbow_up=True)
    sol_down = ik_analytical_2link(target[0], target[1], L1, L2, elbow_up=False)
    
    fig, ax = plt.subplots(figsize=(8, 8))
    limit = L1 + L2 + 1
    ax.set_xlim(-limit, limit)
    ax.set_ylim(-limit, limit)
    ax.set_aspect('equal')
    ax.grid(True, alpha=0.3)
    
    if sol_up:
        t1, t2 = sol_up
        print(f"\n肘部朝上: θ1={np.degrees(t1):.1f}°, θ2={np.degrees(t2):.1f}°")
        plot_arm(ax, [t1, t2], [L1, L2], color='#2196F3', label='肘部朝上')
    
    if sol_down:
        t1, t2 = sol_down
        print(f"肘部朝下: θ1={np.degrees(t1):.1f}°, θ2={np.degrees(t2):.1f}°")
        plot_arm(ax, [t1, t2], [L1, L2], color='#FF9800', label='肘部朝下')
    
    # 标记目标
    ax.plot(*target, 'x', color='red', markersize=15, markeredgewidth=3, label='目标')
    
    # 画工作空间边界
    theta = np.linspace(0, 2*np.pi, 100)
    ax.plot((L1+L2)*np.cos(theta), (L1+L2)*np.sin(theta), 'r--', alpha=0.3)
    ax.plot(abs(L1-L2)*np.cos(theta), abs(L1-L2)*np.sin(theta), 'g--', alpha=0.3)
    
    ax.set_title('两连杆逆运动学：同一目标的两个解', fontsize=14)
    ax.legend(fontsize=12)
    plt.tight_layout()
    plt.savefig('robot_things/01_kinematics/output_03_ik_analytical.png', dpi=100)
    plt.show()


def demo_jacobian_vs_ccd():
    """对比雅可比法和CCD法"""
    print("\n" + "=" * 50)
    print("演示2：雅可比法 vs CCD法（三连杆）")
    print("=" * 50)
    
    link_lengths = [2.0, 1.5, 1.0]
    target = (3.0, 2.5)
    
    print(f"\n目标位置: {target}")
    print(f"连杆长度: {link_lengths}")
    
    # 雅可比法
    print("\n--- 雅可比法 ---")
    np.random.seed(42)
    angles_j, traj_j, ok_j = ik_jacobian(target, link_lengths)
    
    # CCD法
    print("\n--- CCD法 ---")
    angles_c, traj_c, ok_c = ik_ccd(target, link_lengths)
    
    # 可视化
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    limit = sum(link_lengths) + 1
    
    for ax in axes:
        ax.set_xlim(-limit, limit)
        ax.set_ylim(-limit, limit)
        ax.set_aspect('equal')
        ax.grid(True, alpha=0.3)
        ax.plot(*target, 'x', color='red', markersize=15, markeredgewidth=3)
    
    # 雅可比法结果
    if ok_j:
        plot_arm(axes[0], angles_j, link_lengths)
        traj_arr = np.array(traj_j)
        axes[0].plot(traj_arr[:, 0], traj_arr[:, 1], '.-', color='gray',
                     alpha=0.5, markersize=3, label='迭代轨迹')
    axes[0].set_title(f'雅可比伪逆法\n{"成功" if ok_j else "失败"}', fontsize=13)
    axes[0].legend()
    
    # CCD法结果
    if ok_c:
        plot_arm(axes[1], angles_c, link_lengths)
        traj_arr = np.array(traj_c)
        axes[1].plot(traj_arr[:, 0], traj_arr[:, 1], '.-', color='gray',
                     alpha=0.5, markersize=3, label='迭代轨迹')
    axes[1].set_title(f'CCD法\n{"成功" if ok_c else "失败"}', fontsize=13)
    axes[1].legend()
    
    plt.tight_layout()
    plt.savefig('robot_things/01_kinematics/output_03_ik_compare.png', dpi=100)
    plt.show()


# ==================== 主程序 ====================

if __name__ == "__main__":
    print("🤖 第3课：逆运动学")
    print("=" * 50)
    
    demo_analytical()
    demo_jacobian_vs_ccd()
    
    print("\n" + "=" * 50)
    print("📝 课后练习：")
    print("1. 修改目标位置到工作空间边界附近，观察解的变化")
    print("2. 给雅可比法换不同的初始角度，看是否得到不同的解")
    print("3. 思考：为什么CCD从最后一个关节开始调整？反过来会怎样？")
    print("=" * 50)
