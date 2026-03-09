import pandas as pd

# 读取原始文件
input_file = "/Users/liuruixi/Desktop/minimind/user_profile_lesson/事件相关/云贵高中生身份.xlsx"
output_file = "云贵高中身份_去重.xlsx"

df = pd.read_excel(input_file)

# 指定用于判断重复的列
subset_cols = ["作者ID", "网站名称"]

# 检查列是否存在
missing_cols = [col for col in subset_cols if col not in df.columns]
if missing_cols:
    raise ValueError(f"Excel 文件中缺少列: {missing_cols}")

# 基于这两列去重，保留第一次出现的行（keep='first' 是默认行为）
df_dedup = df.drop_duplicates(subset=subset_cols, keep='first').reset_index(drop=True)

# 保存到新文件（保留所有原始列）
df_dedup.to_excel(output_file, index=False)

print(f"✅ 去重完成！共 {len(df)} 行 → {len(df_dedup)} 行")
print(f"结果已保存为: {output_file}")