import numpy as np
import faiss

# 生成示例向量（假设是 768 维，共 1000 个向量）
dimension = 768
nb_vectors = 1000
np.random.seed(42)
vectors = np.random.rand(nb_vectors, dimension).astype('float32')

# 构建 Faiss 索引（使用 L2 距离）
index = faiss.IndexFlatL2(dimension)  # 也可以用 IndexIVFFlat, HNSW 等加速

# 添加向量到索引
index.add(vectors)

# 保存索引到磁盘
faiss.write_index(index, "vector_index.faiss")

print("✅ 向量已成功存入 Faiss 并保存到文件。")



import faiss
import numpy as np

# 加载之前保存的索引
index = faiss.read_index("vector_index.faiss")

print(f"✅ 成功加载索引，包含 {index.ntotal} 个向量。")

# 准备一个查询向量（形状: 1 x d）
query_vector = np.random.rand(1, 768).astype('float32')

# 设置返回最相似的 k 个结果
k = 5
distances, indices = index.search(query_vector, k)

print("最相似的向量索引:", indices)
print("对应的距离（L2）:", distances)
# 注意：距离越小，相似度越高（若需余弦相似度，需先对向量归一化）