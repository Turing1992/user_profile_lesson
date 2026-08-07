# -*- coding: utf-8 -*-
"""将每日唯一身份分布 Excel 生成正式 Word 数据报告。"""
import argparse
import datetime
import os
import shutil
import tempfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor


BLUE = "17365D"
LIGHT_BLUE = "D9EAF7"
LIGHT_GRAY = "F2F2F2"
OTHER_GROUP = "其他/无明确身份"


def set_cell_shading(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shading = tc_pr.find(qn("w:shd"))
    if shading is None:
        shading = OxmlElement("w:shd")
        tc_pr.append(shading)
    shading.set(qn("w:fill"), fill)


def set_cell_text(cell, text, bold=False, color=None, size=9):
    cell.text = ""
    paragraph = cell.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run(str(text))
    run.bold = bold
    run.font.size = Pt(size)
    run.font.name = "宋体"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    if color:
        run.font.color.rgb = RGBColor.from_string(color)

def add_table(document, headers, rows, widths=None, font_size=8):
    table = document.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.autofit = True
    for index, header in enumerate(headers):
        set_cell_text(table.rows[0].cells[index], header, True, "FFFFFF", font_size)
        set_cell_shading(table.rows[0].cells[index], BLUE)
    for row_index, row in enumerate(rows):
        cells = table.add_row().cells
        for col_index, value in enumerate(row):
            set_cell_text(cells[col_index], value, False, None, font_size)
            if widths and col_index < len(widths):
                cells[col_index].width = Cm(widths[col_index])
            if row_index % 2:
                set_cell_shading(cells[col_index], LIGHT_GRAY)
    document.add_paragraph()
    return table


def add_heading(document, text, level=1):
    heading = document.add_heading(text, level=level)
    heading.paragraph_format.space_before = Pt(10)
    heading.paragraph_format.space_after = Pt(5)
    for run in heading.runs:
        run.font.name = "微软雅黑"
        run._element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")
        run.font.color.rgb = RGBColor.from_string(BLUE)
    return heading


def add_body(document, text, bold_prefix=None):
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.first_line_indent = Cm(0.74)
    paragraph.paragraph_format.line_spacing = 1.35
    if bold_prefix and text.startswith(bold_prefix):
        first = paragraph.add_run(bold_prefix)
        first.bold = True
        paragraph.add_run(text[len(bold_prefix):])
    else:
        paragraph.add_run(text)
    return paragraph


def add_bullet(document, text):
    paragraph = document.add_paragraph(style="List Bullet")
    paragraph.paragraph_format.space_after = Pt(2)
    paragraph.add_run(text)
    return paragraph


def format_int(value):
    return "{:,}".format(int(value))


def format_pct(value):
    return "{:.2%}".format(float(value))

def configure_document(document):
    section = document.sections[0]
    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.2)
    section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(1.8)
    section.right_margin = Cm(1.8)
    styles = document.styles
    normal = styles["Normal"]
    normal.font.name = "宋体"
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    normal.font.size = Pt(10.5)
    for style_name in ("Title", "Heading 1", "Heading 2", "Heading 3"):
        style = styles[style_name]
        style.font.name = "微软雅黑"
        style._element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")
    header = section.header.paragraphs[0]
    header.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = header.add_run("人工预警账号唯一身份分布数据报告｜5000样本增强版（已过滤官号）")
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor(120, 120, 120)
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.add_run("内部数据分析材料")


def create_charts(summary, distribution, temp_dir):
    plt.rcParams["font.sans-serif"] = ["Arial Unicode MS", "PingFang SC", "Heiti TC", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    dates = [str(value)[5:] for value in summary["日期"]]
    trend_path = os.path.join(temp_dir, "daily_trend.png")
    fig, ax1 = plt.subplots(figsize=(9, 4.5))
    ax1.plot(dates, summary["当日唯一活跃账号数"], marker="o", linewidth=2.2, color="#17365D", label="当日唯一活跃账号")
    ax1.set_ylabel("唯一活跃账号数（cardinality近似）", color="#17365D")
    ax1.tick_params(axis="y", labelcolor="#17365D")
    ax1.grid(axis="y", alpha=0.22)
    ax2 = ax1.twinx()
    ax2.plot(dates, summary["估算明确身份账号数"], marker="s", linewidth=2.0, color="#C55A11", label="估算明确身份账号")
    ax2.set_ylabel("估算明确身份账号数", color="#C55A11")
    ax2.tick_params(axis="y", labelcolor="#C55A11")
    ax1.set_title("每日活跃账号与明确身份估算趋势")
    fig.tight_layout()
    fig.savefig(trend_path, dpi=180, bbox_inches="tight")
    plt.close(fig)

    identity = distribution[distribution["唯一身份"] != OTHER_GROUP].groupby("唯一身份", as_index=False).agg(
        估算账号日=("估算身份账号数", "sum"), 样本命中=("样本命中账号数", "sum"))
    identity = identity.sort_values("估算账号日", ascending=True)
    identity_path = os.path.join(temp_dir, "identity_distribution.png")
    fig, ax = plt.subplots(figsize=(9, 6.2))
    ax.barh(identity["唯一身份"], identity["估算账号日"], color="#4472C4")
    ax.set_xlabel("估算账号日（8天逐日估算之和）")
    ax.set_title("各唯一身份估算账号日分布")
    ax.grid(axis="x", alpha=0.2)
    fig.tight_layout()
    fig.savefig(identity_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return trend_path, identity_path, identity.sort_values("估算账号日", ascending=False)

def generate_report(input_path, output_path):
    summary = pd.read_excel(input_path, sheet_name="每日运行汇总")
    distribution = pd.read_excel(input_path, sheet_name="日期身份长表")
    audit = pd.read_excel(input_path, sheet_name="每日抽样明细")
    summary["日期"] = summary["日期"].astype(str)
    distribution["日期"] = distribution["日期"].astype(str)
    audit["日期"] = audit["日期"].astype(str)

    posts = int(summary["预警帖子数"].sum())
    account_days = int(summary["当日唯一活跃账号数"].sum())
    candidate_days = int(summary["身份词候选账号数"].sum())
    sample_days = int(summary["哈希抽样账号数"].sum())
    judged_days = int(summary["模型判断账号数"].sum())
    official_days = int(summary.get("官号/机构账号过滤数", pd.Series(dtype="int64")).sum())
    identified_days = int(summary["估算明确身份账号数"].sum())
    identified_rate = float(identified_days) / account_days if account_days else 0.0
    duplicate_count = int((audit["日期"] + "|" + audit["id(平台|uid)"].astype(str)).duplicated().sum())
    multi_identity = int(audit.groupby(["日期", "id(平台|uid)"])["唯一身份"].nunique().gt(1).sum())
    blank_evidence = int(audit[audit["唯一身份"] != OTHER_GROUP]["证据原文"].fillna("").astype(str).str.strip().eq("").sum())
    daily_sums = distribution.groupby("日期")["估算身份账号数"].sum()
    expected_sums = summary.set_index("日期")["当日唯一活跃账号数"]
    totals_match = bool(daily_sums.equals(expected_sums))

    temp_dir = tempfile.mkdtemp(prefix="identity_report_")
    try:
        trend_path, identity_path, identity = create_charts(summary, distribution, temp_dir)
        document = Document()
        configure_document(document)

        title = document.add_paragraph()
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        title.paragraph_format.space_before = Pt(90)
        title_run = title.add_run("人工预警账号\n唯一身份分布数据报告")
        title_run.bold = True
        title_run.font.name = "微软雅黑"
        title_run._element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")
        title_run.font.size = Pt(28)
        title_run.font.color.rgb = RGBColor.from_string(BLUE)
        subtitle = document.add_paragraph()
        subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
        subtitle.paragraph_format.space_before = Pt(24)
        subtitle_run = subtitle.add_run("2026年7月20日—7月27日｜5000样本增强版（官号过滤校正版）")
        subtitle_run.font.size = Pt(15)
        subtitle_run.font.color.rgb = RGBColor(90, 90, 90)
        meta = document.add_paragraph()
        meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
        meta.paragraph_format.space_before = Pt(80)
        meta.add_run("数据源：artificial_warning_push_2026\n统计粒度：每日平台+账号ID唯一账号\n报告生成日期：2026年7月29日")
        document.add_page_break()

        add_heading(document, "一、执行摘要", 1)
        add_body(document, "本报告统计2026年7月20日至7月27日人工预警数据中的每日活跃账号，并对具备身份直接证据的账号进行唯一主身份识别。8天共覆盖{}条预警帖子、{}个账号日；估算具有明确目标身份的账号日为{}，约占全部账号日的{}。".format(
            format_int(posts), format_int(account_days), format_int(identified_days), format_pct(identified_rate)))
        add_body(document, "本次使用5000目标样本的哈希分区抽样，累计抽样{}个账号日；其中通过认证类型、认证说明和机构型账号名称识别并在模型调用前过滤官号/机构账号{}个账号日，累计调用模型判断{}个个人账号日。因本版新增官号过滤口径，不与旧版身份估算值直接比较。".format(
            format_int(sample_days), format_int(official_days), format_int(judged_days)))
        metrics = [
            ("预警帖子数（ES直接统计）", format_int(posts)),
            ("每日唯一活跃账号日（cardinality近似）", format_int(account_days)),
            ("身份词候选账号日（cardinality近似）", format_int(candidate_days)),
            ("哈希抽样账号日", format_int(sample_days)),
            ("官号/机构账号过滤数", format_int(official_days)),
            ("模型实际判断个人账号日", format_int(judged_days)),
            ("估算明确身份账号日", format_int(identified_days)),
            ("估算明确身份占比", format_pct(identified_rate)),
        ]
        add_table(document, ["核心指标", "结果"], metrics, font_size=9)

        add_heading(document, "二、每日数据概览", 1)
        daily_rows = []
        for _, row in summary.iterrows():
            top = distribution[(distribution["日期"] == row["日期"]) & (distribution["唯一身份"] != OTHER_GROUP)].nlargest(3, "估算身份账号数")
            top_text = "、".join("{}{}".format(item["唯一身份"], format_int(item["估算身份账号数"])) for _, item in top.iterrows())
            daily_rows.append([
                row["日期"][5:], format_int(row["预警帖子数"]),
                format_int(row["当日唯一活跃账号数"]), format_int(row["哈希抽样账号数"]),
                format_int(row.get("官号/机构账号过滤数", 0)),
                format_int(row["模型判断账号数"]), format_int(row["估算明确身份账号数"]), top_text,
            ])
        add_table(document, ["日期", "帖子数", "唯一账号", "哈希抽样", "官号过滤", "模型判断", "明确身份估算", "Top 3身份"], daily_rows, font_size=7)
        document.add_picture(trend_path, width=Cm(16.8))
        document.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        caption = document.add_paragraph("图1  每日活跃账号与明确身份估算趋势")
        caption.alignment = WD_ALIGN_PARAGRAPH.CENTER

        add_heading(document, "三、唯一身份分布", 1)
        add_body(document, "跨日期汇总采用“账号日”口径：同一账号若在不同日期活跃，会在各日期分别计入；因此下表不能解释为8天周期内去重后的自然人或唯一账号总数。身份内部占比以估算明确身份账号日为分母。")
        identity_rows = []
        for _, row in identity.iterrows():
            estimated = int(row["估算账号日"])
            identity_rows.append([
                row["唯一身份"], format_int(row["样本命中"]), format_int(estimated),
                format_pct(float(estimated) / identified_days if identified_days else 0.0),
                format_int(round(float(estimated) / len(summary))),
            ])
        add_table(document, ["唯一身份", "样本命中", "估算账号日", "身份内部占比", "日均估算"], identity_rows, font_size=8)
        document.add_picture(identity_path, width=Cm(16.8))
        document.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        caption = document.add_paragraph("图2  各唯一身份估算账号日分布")
        caption.alignment = WD_ALIGN_PARAGRAPH.CENTER

        add_heading(document, "四、统计方法与唯一身份规则", 1)
        add_bullet(document, "时间窗口：每天00:00:00—23:59:59独立统计。")
        add_bullet(document, "账号去重键：siteName|author_persona.id；同一天同一账号只出现一次。")
        add_bullet(document, "候选召回：统一使用全部身份别名检索，避免按身份分别抽样造成一个账号被重复计算。")
        add_bullet(document, "抽样方式：对候选账号键进行哈希分区抽样，不使用scroll，不全量拉取帖子。")
        add_bullet(document, "官号过滤：优先使用已校准的平台认证类型；同时检查认证说明及已认证账号的机构型名称。命中官号/机构规则的账号不调用模型、不计入任何个人身份，统一留在“其他/无明确身份”口径中。")
        add_bullet(document, "判定门槛：账号资料明确标注身份，或正文存在第一人称身份/从业行为直接表述；证据必须能在原文中找到。")
        add_bullet(document, "唯一主身份：模型可返回多个候选身份，但最终按固定优先级只保留一个；未通过证据校验的账号统一归入“其他/无明确身份”。")
        add_body(document, "估算公式：某身份估算账号数＝身份词候选账号数×硬规则通过率×该身份在模型判断样本中的占比。由于本轮每天硬规则通过账号均未超过500个模型判断上限，硬规则通过账号均已参与模型判断。")
        add_body(document, "主身份优先级为：医护人员＞教师＞律师＞警察＞公务员＞事业单位工作人员＞外卖员＞快递员＞网约车司机＞货车司机＞家政服务人员＞餐饮从业者＞维修人员＞农民＞牧民＞工人＞退役军人＞学生＞家长＞老人。")

        add_heading(document, "五、质量校验与可信度", 1)
        validation_rows = [
            ("每日身份估算数之和＝当日唯一账号数", "通过" if totals_match else "未通过"),
            ("同日重复账号键", format_int(duplicate_count)),
            ("同日同账号多重最终身份", format_int(multi_identity)),
            ("非“其他”结果空证据", format_int(blank_evidence)),
            ("样本中官号/机构账号过滤数", format_int(official_days)),
            ("ES查询超时天数", format_int(summary["查询是否超时"].fillna(False).astype(bool).sum())),
            ("抽样截断桶数", format_int(summary["抽样截断桶数"].sum())),
            ("是否写入media_*正式画像索引", "否"),
        ]
        add_table(document, ["校验项", "结果"], validation_rows, font_size=9)
        add_bullet(document, "高可信：帖子数为ES查询直接统计值；每日账号去重键和唯一身份约束已通过一致性校验。")
        add_bullet(document, "中高可信：每日唯一活跃账号数使用precision_threshold=40000的cardinality聚合，属于高精度近似值，不是逐条精确去重结果。")
        add_bullet(document, "中等可信：各身份数量来自候选池哈希抽样估算。5000版比1000版明显稳定，但不是对全部账号逐个分类。")
        add_bullet(document, "低频身份需谨慎：样本命中较少时区间较宽；Excel“日期身份长表”已保留每日Wilson 95%估算上下限。")
        add_bullet(document, "表中某身份为0，只表示本轮样本未命中，不能断言该日真实数据中不存在该身份。")

        add_heading(document, "六、主要发现", 1)
        top_three = identity.head(3)
        top_description = "、".join("{}（{}账号日）".format(row["唯一身份"], format_int(row["估算账号日"])) for _, row in top_three.iterrows())
        max_accounts = summary.loc[summary["当日唯一活跃账号数"].idxmax()]
        max_identified = summary.loc[summary["估算明确身份账号数"].idxmax()]
        add_bullet(document, "8天估算明确身份账号日合计{}，占全部活跃账号日约{}；绝大多数活跃账号仍归入“其他/无明确身份”。".format(format_int(identified_days), format_pct(identified_rate)))
        add_bullet(document, "明确身份账号日累计排名前三为：{}。".format(top_description))
        add_bullet(document, "日活跃账号最高出现在{}，约{}个；明确身份估算最高出现在{}，约{}个。".format(
            max_accounts["日期"], format_int(max_accounts["当日唯一活跃账号数"]),
            max_identified["日期"], format_int(max_identified["估算明确身份账号数"])))
        add_bullet(document, "律师、农牧从业者、教师/家长等身份在多日样本中持续出现，跨日稳定性相对高于仅偶发命中的低频身份。")
        add_body(document, "综合判断：本报告适合用于观察每日规模、身份结构和变化趋势，不适合把单个身份估算值作为逐账号精确清单或执法、考核依据。如需精确账号数量，应对目标身份执行更大样本复核或逐账号分类，并保留人工审核环节。")

        add_heading(document, "附录：数据口径说明", 1)
        add_table(document, ["字段类型", "代表指标", "解释"], [
            ("ES直接统计值", "预警帖子数", "查询时间窗口内命中文档数"),
            ("cardinality近似值", "每日唯一账号、候选账号", "按平台+账号ID计算的高精度近似去重数"),
            ("抽样实际值", "哈希抽样数、模型判断数、样本命中数", "本轮实际进入对应处理阶段的账号日数量"),
            ("抽样估算值", "各身份账号数、其他账号数", "由候选池样本比例外推，不是全量逐账号分类"),
        ], font_size=8)
        add_body(document, "原始统计明细、每日95%估算区间和抽样证据见配套Excel：《预警账号唯一身份按日期分布_20260720_至今_5000样本.xlsx》。")

        output_dir = os.path.dirname(os.path.abspath(output_path))
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        document.save(output_path)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
    return output_path


def main():
    parser = argparse.ArgumentParser(description="生成每日唯一身份分布Word报告")
    parser.add_argument("--input", required=True, help="5000样本Excel路径")
    parser.add_argument("--output", required=True, help="输出docx路径")
    args = parser.parse_args()
    result = generate_report(args.input, args.output)
    print("Word报告: {}".format(os.path.abspath(result)))


if __name__ == "__main__":
    main()
