"""
=============================================================
第6课：卡尔曼滤波 (Kalman Filter)
=============================================================

【为什么需要卡尔曼滤波？】
机器人的传感器都有噪声：
- GPS定位有几米的误差
- 轮子编码器会打滑
- 激光雷达有测量噪声

卡尔曼滤波通过融合"预测"和"观测"，得到比任何单一来源更准确的估计。

【核心思想】
两步循环：
1. 预测 (Predict): 根据运动模型预测下一时刻的状态
   "我觉得我应该在这里"
2. 更新 (Update): 用传感器观测修正预测
   "传感器说我在那里，综合一下我大概在这里"

【数学公式】
状态: x（比如位置和速度）
协方差: P（不确定性有多大）

预测步:
    x_pred = F @ x + B @ u        # 状态预测
    P_pred = F @ P @ F^T + Q      # 协方差预测

更新步:
    K = P_pred @ H^T @ (H @ P_pred @ H^T + R)^{-1}  # 卡尔曼增益
    x = x_pred + K @ (z - H @ x_pred)                 # 状态更新
    P = (I - K @ H) @ P_pred                           # 协方差更新

其中:
    F = 状态转移矩阵（运动模型）
    H = 观测矩阵（传感器模型）
    Q = 过程噪声协方差（运动不确定性）
    R = 观测噪声协方差（传感器不确定性）
    K = 卡尔曼增益（决定更相信预测还是观测）
"""

import numpy as np
import matplotlib.pyplot as plt


class KalmanFilter:
    """
    通用卡尔曼滤波器
    
    使用方法：
    1. 初始化状态和各矩阵
    2. 循环调用 predict() 和 update()
    """
    
    def __init__(self, dim_state, dim_obs):
        """
        参数:
            dim_state: 状态维度（比如 [x, y, vx, vy] 就是4）
            dim_obs: 观测维度（比如只能观测 [x, y] 就是2）
        """
        self.dim_state = dim_state
        self.dim_obs = dim_obs
        
        # 状态和协方差
        self.x = np.zeros(dim_state)           # 状态估计
        self.P = np.eye(dim_state)             # 协方差（初始不确定性）
        
        # 模型矩阵
        self.F = np.eye(dim_state)             # 状态转移矩阵
        self.H = np.zeros((dim_obs, dim_state))  # 观测矩阵
        self.Q = np.eye(dim_state) * 0.01      # 过程噪声
        self.R = np.eye(dim_obs) * 1.0         # 观测噪声
        self.B = np.zeros((dim_state, 1))       # 控制输入矩阵
    
    def predict(self, u=None):
        """
        预测步：根据运动模型预测下一状态
        
        参数:
            u: 控制输入（可选，比如加速度）
        """
        if u is not None:
            self.x = self.F @ self.x + self.B @ u
        else:
            self.x = self.F @ self.x
        
        self.P = self.F @ self.P @ self.F.T + self.Q
    
    def update(self, z):
        """
        更新步：用观测值修正预测
        
        参数:
            z: 观测值向量
        """
        # 创新（观测残差）：实际观测 - 预测观测
        y = z - self.H @ self.x
        
        # 创新协方差
        S = self.H @ self.P @ self.H.T + self.R
        
        # 卡尔曼增益
        # K 大 → 更相信观测
        # K 小 → 更相信预测
        K = self.P @ self.H.T @ np.linalg.inv(S)
        
        # 更新状态
        self.x = self.x + K @ y
        
        # 更新协方差
        I = np.eye(self.dim_state)
        self.P = (I - K @ self.H) @ self.P


# ==================== 演示1：1D位置跟踪 ====================

def demo_1d_tracking():
    """
    最简单的例子：跟踪一个匀速运动的物体
    
    状态: [位置, 速度]
    观测: [位置]（带噪声的GPS）
    """
    print("=" * 50)
    print("演示1：1D匀速运动跟踪")
    print("=" * 50)
    
    dt = 1.0  # 时间步长
    
    # 创建卡尔曼滤波器
    kf = KalmanFilter(dim_state=2, dim_obs=1)
    
    # 状态转移矩阵：匀速运动模型
    # x_new = x + v * dt
    # v_new = v
    kf.F = np.array([
        [1, dt],
        [0,  1]
    ])
    
    # 观测矩阵：只能观测位置
    kf.H = np.array([[1, 0]])
    
    # 噪声参数
    kf.Q = np.array([
        [0.1, 0],
        [0, 0.1]
    ]) * 0.5  # 过程噪声（运动模型不完美）
    
    kf.R = np.array([[10.0]])  # 观测噪声（GPS精度差）
    
    # 初始状态
    kf.x = np.array([0.0, 1.0])  # 初始位置0，初始速度1
    kf.P = np.eye(2) * 100       # 初始不确定性很大
    
    # 模拟真实运动和带噪声的观测
    n_steps = 50
    true_positions = []
    measurements = []
    estimates = []
    uncertainties = []
    
    true_pos = 0.0
    true_vel = 1.0  # 真实速度
    
    np.random.seed(42)
    
    for i in range(n_steps):
        # 真实运动（加一点过程噪声）
        true_pos += true_vel * dt + np.random.normal(0, 0.3)
        true_positions.append(true_pos)
        
        # 带噪声的观测
        measurement = true_pos + np.random.normal(0, 3.0)  # GPS噪声 σ=3
        measurements.append(measurement)
        
        # 卡尔曼滤波
        kf.predict()
        kf.update(np.array([measurement]))
        
        estimates.append(kf.x[0])
        uncertainties.append(np.sqrt(kf.P[0, 0]))  # 位置的标准差
    
    # 可视化
    t = np.arange(n_steps)
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
    
    # 位置跟踪
    ax1.plot(t, true_positions, 'g-', linewidth=2, label='真实位置')
    ax1.scatter(t, measurements, c='red', s=15, alpha=0.5, label='GPS观测（噪声大）')
    ax1.plot(t, estimates, 'b-', linewidth=2, label='卡尔曼估计')
    
    # 画不确定性区间
    est = np.array(estimates)
    unc = np.array(uncertainties)
    ax1.fill_between(t, est - 2*unc, est + 2*unc, alpha=0.2, color='blue',
                     label='95%置信区间')
    
    ax1.set_xlabel('时间步')
    ax1.set_ylabel('位置')
    ax1.set_title('卡尔曼滤波：1D位置跟踪', fontsize=14)
    ax1.legend(fontsize=10)
    ax1.grid(True, alpha=0.3)
    
    # 不确定性变化
    ax2.plot(t, uncertainties, 'b-', linewidth=2)
    ax2.set_xlabel('时间步')
    ax2.set_ylabel('位置不确定性 (σ)')
    ax2.set_title('不确定性随时间的变化（越来越小 → 越来越确信）', fontsize=12)
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('robot_things/03_perception/output_06_kf_1d.png', dpi=100)
    plt.show()
    
    # 计算误差
    err_meas = np.mean(np.abs(np.array(measurements) - np.array(true_positions)))
    err_kf = np.mean(np.abs(np.array(estimates) - np.array(true_positions)))
    print(f"\nGPS观测平均误差: {err_meas:.2f}")
    print(f"卡尔曼估计平均误差: {err_kf:.2f}")
    print(f"精度提升: {(1 - err_kf/err_meas)*100:.1f}%")


# ==================== 演示2：2D机器人跟踪 ====================

def demo_2d_robot_tracking():
    """
    跟踪一个在2D平面上运动的机器人
    
    状态: [x, y, vx, vy]
    观测: [x, y]（带噪声）
    """
    print("\n" + "=" * 50)
    print("演示2：2D机器人运动跟踪")
    print("=" * 50)
    
    dt = 0.1
    
    kf = KalmanFilter(dim_state=4, dim_obs=2)
    
    # 匀速运动模型
    kf.F = np.array([
        [1, 0, dt, 0],
        [0, 1, 0, dt],
        [0, 0, 1,  0],
        [0, 0, 0,  1]
    ])
    
    # 观测位置
    kf.H = np.array([
        [1, 0, 0, 0],
        [0, 1, 0, 0]
    ])
    
    kf.Q = np.eye(4) * 0.1
    kf.R = np.eye(2) * 2.0
    kf.x = np.array([0, 0, 1, 0.5])
    kf.P = np.eye(4) * 10
    
    # 模拟：机器人走一个圆形轨迹
    n_steps = 200
    true_path = []
    meas_path = []
    est_path = []
    
    np.random.seed(123)
    
    for i in range(n_steps):
        t = i * dt
        # 真实轨迹：圆形
        true_x = 5 * np.cos(0.5 * t)
        true_y = 5 * np.sin(0.5 * t)
        true_path.append((true_x, true_y))
        
        # 带噪声的观测
        meas_x = true_x + np.random.normal(0, 1.0)
        meas_y = true_y + np.random.normal(0, 1.0)
        meas_path.append((meas_x, meas_y))
        
        # 卡尔曼滤波
        kf.predict()
        kf.update(np.array([meas_x, meas_y]))
        est_path.append((kf.x[0], kf.x[1]))
    
    # 可视化
    true_arr = np.array(true_path)
    meas_arr = np.array(meas_path)
    est_arr = np.array(est_path)
    
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.plot(true_arr[:, 0], true_arr[:, 1], 'g-', linewidth=2, label='真实轨迹')
    ax.scatter(meas_arr[:, 0], meas_arr[:, 1], c='red', s=5, alpha=0.3, label='观测')
    ax.plot(est_arr[:, 0], est_arr[:, 1], 'b-', linewidth=2, label='卡尔曼估计')
    
    ax.set_aspect('equal')
    ax.grid(True, alpha=0.3)
    ax.set_title('2D机器人跟踪：圆形轨迹', fontsize=14)
    ax.legend(fontsize=12)
    
    plt.tight_layout()
    plt.savefig('robot_things/03_perception/output_06_kf_2d.png', dpi=100)
    plt.show()
    
    print("蓝色线（卡尔曼估计）比红色点（原始观测）更贴近绿色线（真实轨迹）")


# ==================== 演示3：传感器融合 ====================

def demo_sensor_fusion():
    """
    传感器融合：同时使用两个精度不同的传感器
    
    场景：
    - 传感器A：精度低但更新快（比如轮式里程计）
    - 传感器B：精度高但更新慢（比如GPS）
    
    卡尔曼滤波自动根据各传感器的噪声水平分配权重。
    """
    print("\n" + "=" * 50)
    print("演示3：传感器融合")
    print("=" * 50)
    
    dt = 0.1
    n_steps = 200
    
    np.random.seed(42)
    
    # 真实运动：匀速
    true_positions = np.cumsum(np.ones(n_steps) * 0.5 * dt)
    
    # 传感器A：噪声大，每步都有
    sensor_a = true_positions + np.random.normal(0, 2.0, n_steps)
    
    # 传感器B：噪声小，但只有每10步才有一次
    sensor_b_indices = list(range(0, n_steps, 10))
    sensor_b = true_positions[sensor_b_indices] + np.random.normal(0, 0.3, len(sensor_b_indices))
    
    # 卡尔曼滤波融合
    kf = KalmanFilter(dim_state=2, dim_obs=1)
    kf.F = np.array([[1, dt], [0, 1]])
    kf.H = np.array([[1, 0]])
    kf.Q = np.eye(2) * 0.01
    kf.x = np.array([0, 0.5])
    kf.P = np.eye(2) * 10
    
    estimates = []
    b_idx = 0
    
    for i in range(n_steps):
        kf.predict()
        
        # 传感器A（每步更新，噪声大）
        kf.R = np.array([[4.0]])  # σ² = 2²
        kf.update(np.array([sensor_a[i]]))
        
        # 传感器B（偶尔更新，噪声小）
        if b_idx < len(sensor_b_indices) and i == sensor_b_indices[b_idx]:
            kf.R = np.array([[0.09]])  # σ² = 0.3²
            kf.update(np.array([sensor_b[b_idx]]))
            b_idx += 1
        
        estimates.append(kf.x[0])
    
    # 可视化
    t = np.arange(n_steps) * dt
    
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(t, true_positions, 'g-', linewidth=2, label='真实位置')
    ax.scatter(t, sensor_a, c='red', s=5, alpha=0.3, label='传感器A（噪声大，频率高）')
    ax.scatter(t[sensor_b_indices], sensor_b, c='orange', s=50, marker='^',
               zorder=5, label='传感器B（噪声小，频率低）')
    ax.plot(t, estimates, 'b-', linewidth=2, label='融合估计')
    
    ax.set_xlabel('时间 (s)')
    ax.set_ylabel('位置')
    ax.set_title('传感器融合：卡尔曼滤波自动分配权重', fontsize=14)
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('robot_things/03_perception/output_06_fusion.png', dpi=100)
    plt.show()
    
    print("注意：每当传感器B（橙色三角）出现时，估计值会明显修正")
    print("卡尔曼滤波自动给精度高的传感器更大权重")


if __name__ == "__main__":
    print("🤖 第6课：卡尔曼滤波")
    print("=" * 50)
    
    demo_1d_tracking()
    demo_2d_robot_tracking()
    demo_sensor_fusion()
    
    print("\n" + "=" * 50)
    print("📝 课后练习：")
    print("1. 调整 R（观测噪声）的大小，观察滤波器行为变化")
    print("2. 如果 Q 设得很大，滤波器会怎样？（提示：更相信观测）")
    print("3. 试试跟踪一个做加速运动的物体，匀速模型还好用吗？")
    print("=" * 50)
