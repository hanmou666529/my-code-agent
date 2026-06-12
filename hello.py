import random

# 生成5个前区号码（范围1-35，不重复）
front_numbers = sorted(random.sample(range(1, 36), 5))

# 生成2个后区号码（范围1-12，不重复）
back_numbers = sorted(random.sample(range(1, 13), 2))

# 输出结果
print('前区号码（5个，范围1-35）：', front_numbers)
print('后区号码（2个，范围1-12）：', back_numbers)
print()
print(f"完整号码：{' '.join(map(str, front_numbers))} | {' '.join(map(str, back_numbers))}")
