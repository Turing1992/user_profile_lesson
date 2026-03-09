"""
=============================================================
第5课：RRT路径规划（快速随机树）
=============================================================

【为什么需要RRT？】
A* 在栅格地图上很好用，但在连续空间（比如高维关节空间）中，
栅格化会导致维度爆炸。RRT 直接在连续空间中采样，适合：
- 高维空间（多关节机器人）
- 复杂约束
- 不需要最优解，只需要可行解

【RRT算法】(Rapidly-exploring Random Tree)
1. 从起点开始建一棵树
2. 随机采样一个点
3. 找到树上离采样点最近的节点
4. 从最近节点向采样点方向延伸一步
5. 如果新节点不碰障碍物，加入树中
6. 重复直到树到达终点附近

【RRT*】(RRT的优化版本)
在RRT基础上加了"重新布线"(rewire)：
新节点加入后，检查附近节点是否能通过新节点获得更短路径。
这使得RRT*能渐近收敛到最优路径。
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle


class ContinuousMap:
    """连续空间地图，障碍物用圆形和矩形表示"""
    
    def __init__(self, x_range, y_range):
        self.x_min, self.x_max = x_range
        self.y_min, self.y_max = y_range
        self.obstacles = []  # [(type, params), ...]
    
    def add_circle(self, cx, cy, r):
        self.obstacles.append(('circle', (cx, cy, r)))
    
    def add_rect(self, x, y, w, h):
        self.obstacles.append(('rect', (x, y, w, h)))
    
    def is_free(self, x, y):
        """检查点是否在自由空间"""
        for obs_type, params in self.obstacles:
            if obs_type == 'circle':
                cx, cy, r = params
                if (x - cx)**2 + (y - cy)**2 <= r**2:
                    return False
            elif obs_type == 'rect':
                rx, ry, rw, rh = params
                if rx <= x <= rx + rw and ry <= y <= ry + rh:
                    return False
        return True
    
    def is_path_free(self, p1, p2, resolution=20):
        """检查两点之间的路径是否无碰撞"""
        for t in np.linspace(0, 1, resolution):
            x = p1[0] + t * (p2[0] - p1[0])
            y = p1[1] + t * (p2[1] - p1[1])
            if not self.is_free(x, y):
                return False
        return True


class RRTNode:
    """RRT树的节点"""
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.parent = None
        self.cost = 0.0  # 从起点到此节点的路径代价（RRT*用）


def rrt(env_map, start, goal, max_iter=3000, step_size=1.0, goal_bias=0.1):
    """
    基础RRT算法
    
    参数:
        env_map: ContinuousMap 环境
        start: (x, y) 起点
        goal: (x, y) 终点
        max_iter: 最大迭代次数
        step_size: 每步延伸距离
        goal_bias: 以此概率直接向目标采样（加速收敛）
    
    返回:
        path: 路径点列表，或 None
        tree: 所有树节点（用于可视化）
    """
    start_node = RRTNode(*start)
    tree = [start_node]
    
    for i in range(max_iter):
        # 1. 随机采样（偶尔直接采样目标点）
        if np.random.random() < goal_bias:
            sample = goal
        else:
            sample = (
                np.random.uniform(env_map.x_min, env_map.x_max),
                np.random.uniform(env_map.y_min, env_map.y_max)
            )
        
        # 2. 找最近节点
        nearest = min(tree, key=lambda n: (n.x - sample[0])**2 + (n.y - sample[1])**2)
        
        # 3. 向采样点方向延伸 step_size
        dx = sample[0] - nearest.x
        dy = sample[1] - nearest.y
        dist = np.sqrt(dx**2 + dy**2)
        
        if dist < 1e-6:
            continue
        
        # 限制步长
        if dist > step_size:
            dx = dx / dist * step_size
            dy = dy / dist * step_size
        
        new_x = nearest.x + dx
        new_y = nearest.y + dy
        
        # 4. 碰撞检测
        if not env_map.is_path_free((nearest.x, nearest.y), (new_x, new_y)):
            continue
        
        # 5. 加入树
        new_node = RRTNode(new_x, new_y)
        new_node.parent = nearest
        tree.append(new_node)
        
        # 6. 检查是否到达目标
        dist_to_goal = np.sqrt((new_x - goal[0])**2 + (new_y - goal[1])**2)
        if dist_to_goal < step_size:
            if env_map.is_path_free((new_x, new_y), goal):
                goal_node = RRTNode(*goal)
                goal_node.parent = new_node
                tree.append(goal_node)
                
                # 回溯路径
                path = []
                node = goal_node
                while node is not None:
                    path.append((node.x, node.y))
                    node = node.parent
                path.reverse()
                
                print(f"  ✓ RRT找到路径！迭代 {i} 次，路径点数 {len(path)}")
                return path, tree
    
    print(f"  ✗ RRT未找到路径（{max_iter}次迭代）")
    return None, tree


def rrt_star(env_map, start, goal, max_iter=3000, step_size=1.0,
             goal_bias=0.1, rewire_radius=2.0):
    """
    RRT* 算法（带重新布线的RRT）
    
    与RRT的区别：
    1. 新节点不一定连接最近节点，而是连接"代价最小"的邻居
    2. 加入新节点后，检查附近节点是否能通过新节点获得更短路径
    
    这两步使得RRT*能渐近收敛到最优路径。
    """
    start_node = RRTNode(*start)
    start_node.cost = 0
    tree = [start_node]
    
    for i in range(max_iter):
        # 随机采样
        if np.random.random() < goal_bias:
            sample = goal
        else:
            sample = (
                np.random.uniform(env_map.x_min, env_map.x_max),
                np.random.uniform(env_map.y_min, env_map.y_max)
            )
        
        # 找最近节点
        nearest = min(tree, key=lambda n: (n.x - sample[0])**2 + (n.y - sample[1])**2)
        
        # 延伸
        dx = sample[0] - nearest.x
        dy = sample[1] - nearest.y
        dist = np.sqrt(dx**2 + dy**2)
        if dist < 1e-6:
            continue
        if dist > step_size:
            dx = dx / dist * step_size
            dy = dy / dist * step_size
        
        new_x = nearest.x + dx
        new_y = nearest.y + dy
        
        if not env_map.is_path_free((nearest.x, nearest.y), (new_x, new_y)):
            continue
        
        new_node = RRTNode(new_x, new_y)
        
        # === RRT* 特有：选择最优父节点 ===
        nearby = [n for n in tree
                  if (n.x - new_x)**2 + (n.y - new_y)**2 <= rewire_radius**2]
        
        best_parent = nearest
        best_cost = nearest.cost + np.sqrt((new_x - nearest.x)**2 + (new_y - nearest.y)**2)
        
        for n in nearby:
            cost = n.cost + np.sqrt((new_x - n.x)**2 + (new_y - n.y)**2)
            if cost < best_cost and env_map.is_path_free((n.x, n.y), (new_x, new_y)):
                best_parent = n
                best_cost = cost
        
        new_node.parent = best_parent
        new_node.cost = best_cost
        tree.append(new_node)
        
        # === RRT* 特有：重新布线 ===
        for n in nearby:
            new_cost = new_node.cost + np.sqrt((n.x - new_x)**2 + (n.y - new_y)**2)
            if new_cost < n.cost and env_map.is_path_free((new_x, new_y), (n.x, n.y)):
                n.parent = new_node
                n.cost = new_cost
        
        # 检查目标
        dist_to_goal = np.sqrt((new_x - goal[0])**2 + (new_y - goal[1])**2)
        if dist_to_goal < step_size:
            if env_map.is_path_free((new_x, new_y), goal):
                goal_node = RRTNode(*goal)
                goal_node.parent = new_node
                goal_node.cost = new_node.cost + dist_to_goal
                tree.append(goal_node)
                
                path = []
                node = goal_node
                while node is not None:
                    path.append((node.x, node.y))
                    node = node.parent
                path.reverse()
                
                print(f"  ✓ RRT*找到路径！迭代 {i} 次，路径代价 {goal_node.cost:.2f}")
                return path, tree
    
    print(f"  ✗ RRT*未找到路径")
    return None, tree


# ==================== 可视化 ====================

def plot_environment(ax, env_map, start, goal):
    """画环境"""
    ax.set_xlim(env_map.x_min, env_map.x_max)
    ax.set_ylim(env_map.y_min, env_map.y_max)
    ax.set_aspect('equal')
    ax.grid(True, alpha=0.2)
    
    for obs_type, params in env_map.obstacles:
        if obs_type == 'circle':
            cx, cy, r = params
            circle = Circle((cx, cy), r, color='gray', alpha=0.7)
            ax.add_patch(circle)
        elif obs_type == 'rect':
            x, y, w, h = params
            rect = Rectangle((x, y), w, h, color='gray', alpha=0.7)
            ax.add_patch(rect)
    
    ax.plot(*start, 'go', markersize=12, zorder=5, label='起点')
    ax.plot(*goal, 'r*', markersize=15, zorder=5, label='终点')


def plot_tree(ax, tree, color='lightblue', alpha=0.3):
    """画RRT树"""
    for node in tree:
        if node.parent:
            ax.plot([node.x, node.parent.x], [node.y, node.parent.y],
                    '-', color=color, alpha=alpha, linewidth=0.5)


def plot_path(ax, path, color='red', linewidth=2):
    """画路径"""
    if path:
        xs = [p[0] for p in path]
        ys = [p[1] for p in path]
        ax.plot(xs, ys, '-', color=color, linewidth=linewidth, label='路径')


# ==================== 演示 ====================

def create_demo_env():
    """创建演示环境"""
    env = ContinuousMap((0, 20), (0, 20))
    env.add_circle(5, 5, 2)
    env.add_circle(10, 10, 2.5)
    env.add_circle(15, 5, 1.5)
    env.add_rect(7, 14, 4, 2)
    env.add_rect(2, 10, 2, 5)
    env.add_circle(16, 15, 1.8)
    return env


def demo_rrt_vs_rrt_star():
    """对比RRT和RRT*"""
    print("=" * 50)
    print("演示：RRT vs RRT*")
    print("=" * 50)
    
    env = create_demo_env()
    start = (1, 1)
    goal = (19, 19)
    
    np.random.seed(42)
    
    fig, axes = plt.subplots(1, 2, figsize=(14, 7))
    
    # RRT
    print("\n--- RRT ---")
    path_rrt, tree_rrt = rrt(env, start, goal, max_iter=5000, step_size=1.5)
    
    plot_environment(axes[0], env, start, goal)
    plot_tree(axes[0], tree_rrt)
    plot_path(axes[0], path_rrt)
    axes[0].set_title(f'RRT\n树节点: {len(tree_rrt)}', fontsize=13)
    axes[0].legend()
    
    # RRT*
    print("\n--- RRT* ---")
    np.random.seed(42)
    path_star, tree_star = rrt_star(env, start, goal, max_iter=5000, step_size=1.5)
    
    plot_environment(axes[1], env, start, goal)
    plot_tree(axes[1], tree_star, color='lightgreen')
    plot_path(axes[1], path_star, color='blue')
    axes[1].set_title(f'RRT*\n树节点: {len(tree_star)}', fontsize=13)
    axes[1].legend()
    
    plt.tight_layout()
    plt.savefig('robot_things/02_path_planning/output_05_rrt.png', dpi=100)
    plt.show()
    
    print("\n关键区别：")
    print("- RRT：找到可行路径就停，路径可能弯弯曲曲")
    print("- RRT*：通过重新布线优化路径，更接近最优")


if __name__ == "__main__":
    print("🤖 第5课：RRT路径规划")
    print("=" * 50)
    
    demo_rrt_vs_rrt_star()
    
    print("\n" + "=" * 50)
    print("📝 课后练习：")
    print("1. 调整 step_size 和 goal_bias，观察对搜索效率的影响")
    print("2. 增加更多障碍物，创建一个迷宫环境")
    print("3. 实现路径平滑：对RRT找到的路径做后处理，去掉不必要的拐弯")
    print("=" * 50)
