"""
=============================================================
第4课：A*路径规划算法
=============================================================

【为什么要学路径规划？】
机器人需要从A点移动到B点，但中间有障碍物。
路径规划就是找到一条安全、高效的路径。

【A*算法】
A* 是最经典的路径规划算法，结合了：
- Dijkstra算法的"已走距离"（保证最优）
- 贪心搜索的"估计剩余距离"（加速搜索）

核心公式：
    f(n) = g(n) + h(n)
    
    g(n) = 从起点到节点n的实际代价
    h(n) = 从节点n到终点的估计代价（启发函数）
    f(n) = 总估计代价

每次选择 f 值最小的节点展开。

【启发函数 h(n)】
- 曼哈顿距离: |x1-x2| + |y1-y2|（只能上下左右走时）
- 欧几里得距离: sqrt((x1-x2)² + (y1-y2)²)（可以任意方向走时）
- 要求：h(n) ≤ 实际距离（不能高估，否则不保证最优）
"""

import numpy as np
import matplotlib.pyplot as plt
import heapq
from collections import defaultdict


class GridMap:
    """
    栅格地图：机器人路径规划的基础环境
    
    0 = 可通行
    1 = 障碍物
    """
    
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.grid = np.zeros((height, width), dtype=int)
    
    def add_obstacle(self, x, y):
        """添加单个障碍物"""
        if 0 <= x < self.width and 0 <= y < self.height:
            self.grid[y][x] = 1
    
    def add_rect_obstacle(self, x, y, w, h):
        """添加矩形障碍物"""
        for dy in range(h):
            for dx in range(w):
                self.add_obstacle(x + dx, y + dy)
    
    def is_free(self, x, y):
        """检查位置是否可通行"""
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.grid[y][x] == 0
        return False
    
    def get_neighbors(self, x, y, allow_diagonal=True):
        """获取相邻的可通行格子"""
        # 4方向
        directions = [(0, 1), (0, -1), (1, 0), (-1, 0)]
        if allow_diagonal:
            # 8方向（加上对角线）
            directions += [(1, 1), (1, -1), (-1, 1), (-1, -1)]
        
        neighbors = []
        for dx, dy in directions:
            nx, ny = x + dx, y + dy
            if self.is_free(nx, ny):
                # 对角线移动的代价是 √2 ≈ 1.414
                cost = np.sqrt(dx**2 + dy**2)
                neighbors.append((nx, ny, cost))
        
        return neighbors


def heuristic(a, b, method='euclidean'):
    """
    启发函数：估计从 a 到 b 的距离
    
    这个估计必须 ≤ 实际距离（可接受性），
    否则 A* 不保证找到最短路径。
    """
    if method == 'manhattan':
        return abs(a[0] - b[0]) + abs(a[1] - b[1])
    elif method == 'euclidean':
        return np.sqrt((a[0] - b[0])**2 + (a[1] - b[1])**2)
    else:
        return 0  # Dijkstra（不用启发函数）


def astar(grid_map, start, goal, heuristic_method='euclidean'):
    """
    A* 路径规划算法
    
    参数:
        grid_map: GridMap 对象
        start: (x, y) 起点
        goal: (x, y) 终点
        heuristic_method: 启发函数类型
    
    返回:
        path: 路径点列表，或 None（无解时）
        visited: 访问过的节点集合（用于可视化搜索过程）
        visit_order: 访问顺序（用于动画）
    """
    # 优先队列：(f值, 节点)
    open_set = []
    heapq.heappush(open_set, (0, start))
    
    # 记录每个节点的来源（用于回溯路径）
    came_from = {}
    
    # g值：从起点到各节点的实际代价
    g_score = defaultdict(lambda: float('inf'))
    g_score[start] = 0
    
    # 已访问集合
    visited = set()
    visit_order = []
    
    while open_set:
        # 取出 f 值最小的节点
        current_f, current = heapq.heappop(open_set)
        
        if current in visited:
            continue
        
        visited.add(current)
        visit_order.append(current)
        
        # 到达终点
        if current == goal:
            # 回溯路径
            path = []
            node = goal
            while node in came_from:
                path.append(node)
                node = came_from[node]
            path.append(start)
            path.reverse()
            return path, visited, visit_order
        
        # 展开邻居
        for nx, ny, move_cost in grid_map.get_neighbors(*current):
            neighbor = (nx, ny)
            
            if neighbor in visited:
                continue
            
            # 计算经过 current 到达 neighbor 的 g 值
            tentative_g = g_score[current] + move_cost
            
            if tentative_g < g_score[neighbor]:
                # 找到更好的路径
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                f = tentative_g + heuristic(neighbor, goal, heuristic_method)
                heapq.heappush(open_set, (f, neighbor))
    
    return None, visited, visit_order  # 无解


# ==================== 演示 ====================

def create_demo_map():
    """创建一个有趣的演示地图"""
    gm = GridMap(30, 30)
    
    # 添加一些障碍物
    gm.add_rect_obstacle(5, 0, 2, 18)    # 左墙
    gm.add_rect_obstacle(10, 12, 2, 18)  # 中墙
    gm.add_rect_obstacle(18, 0, 2, 20)   # 右墙
    gm.add_rect_obstacle(23, 8, 2, 22)   # 远右墙
    
    # 一些零散障碍
    for i in range(0, 8):
        gm.add_obstacle(15, i)
    
    return gm


def demo_astar():
    """演示A*算法"""
    print("=" * 50)
    print("演示：A*路径规划")
    print("=" * 50)
    
    gm = create_demo_map()
    start = (1, 1)
    goal = (28, 28)
    
    # 对比不同启发函数
    methods = [
        ('euclidean', '欧几里得距离'),
        ('manhattan', '曼哈顿距离'),
        ('none', 'Dijkstra（无启发）'),
    ]
    
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    
    for idx, (method, name) in enumerate(methods):
        path, visited, visit_order = astar(gm, start, goal, method)
        
        ax = axes[idx]
        
        # 画地图
        display = np.copy(gm.grid).astype(float)
        
        # 标记访问过的节点（浅蓝色）
        for v in visited:
            if display[v[1]][v[0]] == 0:
                display[v[1]][v[0]] = 0.3
        
        # 标记路径（深色）
        if path:
            for p in path:
                display[p[1]][p[0]] = 0.7
        
        ax.imshow(display, cmap='RdYlBu_r', origin='lower', vmin=0, vmax=1)
        
        # 标记起点和终点
        ax.plot(start[0], start[1], 'go', markersize=12, label='起点')
        ax.plot(goal[0], goal[1], 'r*', markersize=15, label='终点')
        
        path_len = len(path) if path else 0
        ax.set_title(f'{name}\n路径长度: {path_len}, 搜索节点: {len(visited)}',
                     fontsize=11)
        ax.legend(loc='upper left')
    
    plt.tight_layout()
    plt.savefig('robot_things/02_path_planning/output_04_astar.png', dpi=100)
    plt.show()
    
    print("\n关键观察：")
    print("- 欧几里得启发：搜索节点最少，效率最高")
    print("- 曼哈顿启发：稍多搜索，但路径可能不同")
    print("- Dijkstra：搜索最多节点（没有方向引导），但保证最优")
    print("\n图片已保存")


def demo_no_path():
    """演示无解的情况"""
    print("\n" + "=" * 50)
    print("演示：无解情况")
    print("=" * 50)
    
    gm = GridMap(15, 15)
    # 完全封闭的墙
    for i in range(15):
        gm.add_obstacle(7, i)
    
    start = (2, 7)
    goal = (12, 7)
    
    path, visited, _ = astar(gm, start, goal)
    
    if path is None:
        print(f"从 {start} 到 {goal} 无法到达（被墙完全隔开）")
        print(f"搜索了 {len(visited)} 个节点后确认无解")
    
    fig, ax = plt.subplots(figsize=(8, 8))
    display = np.copy(gm.grid).astype(float)
    for v in visited:
        if display[v[1]][v[0]] == 0:
            display[v[1]][v[0]] = 0.3
    ax.imshow(display, cmap='RdYlBu_r', origin='lower', vmin=0, vmax=1)
    ax.plot(start[0], start[1], 'go', markersize=12)
    ax.plot(goal[0], goal[1], 'r*', markersize=15)
    ax.set_title('无解：起点和终点被墙隔开', fontsize=13)
    plt.tight_layout()
    plt.savefig('robot_things/02_path_planning/output_04_nopath.png', dpi=100)
    plt.show()


if __name__ == "__main__":
    print("🤖 第4课：A*路径规划")
    print("=" * 50)
    
    demo_astar()
    demo_no_path()
    
    print("\n" + "=" * 50)
    print("📝 课后练习：")
    print("1. 修改地图，添加更复杂的障碍物")
    print("2. 只允许4方向移动（禁止对角线），路径会怎么变？")
    print("3. 给不同区域设置不同的通行代价（比如沼泽地代价更高）")
    print("=" * 50)
