# -*- coding: utf-8 -*-
"""
投资组合再平衡计算器

功能：
1.  首次运行时，根据您输入的初始金额，计算并保存“基础比例”。
2.  后续运行时，读取之前保存的基础比例，并让您输入当前各资产的市值。
3.  计算当前占比，并与基础比例对比。
4.  给出明确的买卖建议：应卖出哪些资产（减少），买入哪些资产（投入）。

使用方法：
1.  将此代码保存为 .py 文件（例如 portfolio_rebalance.py）。
2.  第一次运行时，选择【1】设定初始比例。
3.  之后每三个月运行一次，选择【2】进行再平衡分析。
"""

import json
import os

# 定义文件名，用于保存基础比例
CONFIG_FILE = "base_ratio_config.json"


def load_base_ratio():
    """从文件加载基础比例"""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    else:
        return None


def save_base_ratio(base_ratio):
    """将基础比例保存到文件"""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(base_ratio, f, ensure_ascii=False, indent=2)


def calculate_ratio(amounts):
    """根据金额字典计算各资产占比"""
    total = sum(amounts.values())
    ratio = {}
    for asset, amount in amounts.items():
        ratio[asset] = round(amount / total * 100, 2)  # 保留两位小数
    return ratio, total


def main():
    print("=" * 50)
    print("      欢迎使用投资组合再平衡计算器")
    print("=" * 50)

    base_ratio = load_base_ratio()

    while True:
        print("\n请选择操作：")
        if base_ratio is None:
            print("【1】设定初始比例 (首次使用)")
        else:
            print("【1】重新设定基础比例 (谨慎操作)")
        print("【2】进行再平衡分析 (常规操作)")
        print("【3】退出程序")

        choice = input("\n请输入选项 (1/2/3): ").strip()

        if choice == "1":
            print("\n" + "-" * 30)
            print("设定基础比例")
            print("-" * 30)
            print("请按提示输入各项资产的初始金额（单位：元）：")

            assets = {
                "纳斯达克100": 0,
                "黄金ETF": 0,
                "红利低波": 0,
                "标普500": 0,
                "沪深300": 0
            }

            for asset in assets.keys():
                while True:
                    try:
                        amount = float(input(f"{asset}: "))
                        if amount < 0:
                            print("金额不能为负，请重新输入。")
                            continue
                        assets[asset] = amount
                        break
                    except ValueError:
                        print("输入无效，请输入一个数字。")

            base_ratio_dict, total_base = calculate_ratio(assets)
            print(f"\n✅ 基础比例计算完成！")
            print(f"总金额: {total_base:.2f} 元")
            print("基础配置比例如下：")
            for asset, ratio in base_ratio_dict.items():
                print(f"  {asset}: {ratio}%")

            # 询问是否确认保存
            confirm = input("\n是否确认保存此为基础比例？(y/n): ").strip().lower()
            if confirm == 'y' or confirm == 'yes':
                save_base_ratio(base_ratio_dict)
                base_ratio = base_ratio_dict
                print("基础比例已成功保存！")
            else:
                print("操作已取消。")

        elif choice == "2":
            if base_ratio is None:
                print("\n❌ 错误：尚未设定基础比例！")
                print("请先选择【1】来设定您的初始配置。")
                continue

            print("\n" + "-" * 30)
            print("再平衡分析")
            print("-" * 30)
            print("请按提示输入当前各项资产的市值（单位：元）：")

            current_assets = {}
            for asset in base_ratio.keys():
                while True:
                    try:
                        amount = float(input(f"{asset}: "))
                        if amount < 0:
                            print("金额不能为负，请重新输入。")
                            continue
                        current_assets[asset] = amount
                        break
                    except ValueError:
                        print("输入无效，请输入一个数字。")

            current_ratio, total_current = calculate_ratio(current_assets)

            print(f"\n📊 当前投资组合状态:")
            print(f"总市值: {total_current:.2f} 元")
            print("当前占比如下：")
            for asset, ratio in current_ratio.items():
                print(f"  {asset}: {ratio}%")

            print(f"\n🎯 基础目标比例:")
            for asset, ratio in base_ratio.items():
                print(f"  {asset}: {ratio}%")

            print(f"\n🔄 再平衡建议:")
            to_sell = []
            to_buy = []

            for asset in base_ratio.keys():
                current_r = current_ratio[asset]
                target_r = base_ratio[asset]
                diff = current_r - target_r

                if diff > 0.5:  # 当前占比超过目标占比0.5个百分点以上，建议减仓
                    to_sell.append((asset, round(diff, 2)))
                elif diff < -0.5:  # 当前占比低于目标占比0.5个百分点以上，建议加仓
                    to_buy.append((asset, round(-diff, 2)))

            if not to_sell and not to_buy:
                print("✅ 恭喜！您的投资组合非常均衡，无需调整。")
            else:
                if to_sell:
                    print("📉 建议减少持仓:")
                    for asset, excess in to_sell:
                        sell_amount = excess / 100 * total_current
                        print(f"  • 卖出 {asset} (占比高出{excess}%，约 {sell_amount:.2f}元)")

                if to_buy:
                    print("📈 建议增加投入:")
                    for asset, deficit in to_buy:
                        buy_amount = deficit / 100 * total_current
                        print(f"  • 买入 {asset} (占比不足{deficit}%，约 {buy_amount:.2f}元)")

            print("\n💡 温馨提示：")
            print("  1. 此建议基于‘回到基础比例’的原则。")
            print("  2. 实际操作中可分批进行，避免一次性交易冲击市场。")
            print("  3. 建议每年或在重大策略变更时才重新设定基础比例。")

        elif choice == "3":
            print("\n感谢使用，祝您投资顺利！")
            break

        else:
            print("\n❌ 输入无效，请输入 1、2 或 3。")


if __name__ == "__main__":
    main()