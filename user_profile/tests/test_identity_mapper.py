# -*- coding: utf-8 -*-
"""
身份映射模块单元测试。

测试 identity_mapper 模块中 standardize_identity 函数的核心逻辑，
以及 load_identity_mapping 函数的 Excel 加载功能。
"""

import os
import pytest

from utils.identity_mapper import load_identity_mapping, standardize_identity


# --- standardize_identity 测试 ---

class TestStandardizeIdentity(object):
    """standardize_identity 函数测试。"""

    def setup_method(self):
        # type: () -> None
        """每个测试方法前初始化映射表。"""
        self.identity_map = {
            "记者": "媒体从业者",
            "律师": "法律从业者",
            "医生": "医疗从业者",
            "教师": "教育从业者",
        }  # type: dict

    def test_none_input_returns_empty_string(self):
        # type: () -> None
        """输入 None 时返回空字符串。"""
        result = standardize_identity(None, self.identity_map)
        assert result == ""

    def test_empty_string_returns_empty_string(self):
        # type: () -> None
        """输入空字符串时返回空字符串。"""
        result = standardize_identity("", self.identity_map)
        assert result == ""

    def test_whitespace_only_returns_empty_string(self):
        # type: () -> None
        """输入仅含空白字符时返回空字符串。"""
        result = standardize_identity("   ", self.identity_map)
        assert result == ""

    def test_single_identity_mapped(self):
        # type: () -> None
        """单个身份正确映射为标准化值。"""
        result = standardize_identity("记者", self.identity_map)
        assert result == ["媒体从业者"]

    def test_single_identity_with_whitespace(self):
        # type: () -> None
        """单个身份带前后空格时正确去除空格并映射。"""
        result = standardize_identity(" 记者 ", self.identity_map)
        assert result == ["媒体从业者"]

    def test_single_identity_unmapped_defaults_to_other(self):
        # type: () -> None
        """未在映射表中的身份默认映射为"其他"。"""
        result = standardize_identity("未知身份", self.identity_map)
        assert result == ["其他"]

    def test_multiple_identities_comma_separated(self):
        # type: () -> None
        """逗号分隔的多个身份正确映射并去重。"""
        result = standardize_identity("记者,律师", self.identity_map)
        assert set(result) == {"媒体从业者", "法律从业者"}

    def test_multiple_identities_with_spaces(self):
        # type: () -> None
        """逗号分隔的多个身份带空格时正确处理。"""
        result = standardize_identity("记者 , 律师 , 医生", self.identity_map)
        assert set(result) == {"媒体从业者", "法律从业者", "医疗从业者"}

    def test_multiple_identities_deduplication(self):
        # type: () -> None
        """多个身份映射到同一标准值时去重。"""
        # 构造映射：两个不同原始身份映射到同一标准身份
        identity_map = {"记者": "媒体", "编辑": "媒体", "律师": "法律"}
        result = standardize_identity("记者,编辑,律师", identity_map)
        assert set(result) == {"媒体", "法律"}
        # 去重后长度应为 2
        assert len(result) == 2

    def test_multiple_identities_with_unmapped(self):
        # type: () -> None
        """多个身份中包含未映射的身份时，未映射的默认为"其他"。"""
        result = standardize_identity("记者,未知身份", self.identity_map)
        assert set(result) == {"媒体从业者", "其他"}

    def test_multiple_identities_empty_items_filtered(self):
        # type: () -> None
        """逗号分隔中的空项被过滤。"""
        result = standardize_identity("记者,,律师,", self.identity_map)
        assert set(result) == {"媒体从业者", "法律从业者"}

    def test_list_input_converted_to_string(self):
        # type: () -> None
        """列表类型输入被转为字符串后处理。"""
        # 原始代码中 identity 可能是列表，str([...]) 会产生带方括号的字符串
        # 这里验证与原始行为一致
        result = standardize_identity(["记者"], self.identity_map)
        # str(["记者"]) => "['记者']"，不含逗号时走单值分支
        # "['记者']" 不在映射表中，应返回 ["其他"]
        assert result == ["其他"]


# --- load_identity_mapping 测试 ---

class TestLoadIdentityMapping(object):
    """load_identity_mapping 函数测试。"""

    def test_load_from_excel(self, tmp_project_root, monkeypatch):
        # type: (...) -> None
        """从 Excel 文件正确加载身份映射表。"""
        import pandas as pd

        monkeypatch.setenv("USER_PROFILE_ROOT", tmp_project_root)

        # 创建测试 Excel 文件
        excel_path = os.path.join(tmp_project_root, "final_stanterd.xlsx")
        df = pd.DataFrame({
            "原始身份": ["记者", "律师", "医生"],
            "最终身份": ["媒体从业者", "法律从业者", "医疗从业者"],
        })
        df.to_excel(excel_path, index=False, engine='openpyxl')

        result = load_identity_mapping()
        assert result == {
            "记者": "媒体从业者",
            "律师": "法律从业者",
            "医生": "医疗从业者",
        }

    def test_load_custom_filename(self, tmp_project_root, monkeypatch):
        # type: (...) -> None
        """支持自定义 Excel 文件名。"""
        import pandas as pd

        monkeypatch.setenv("USER_PROFILE_ROOT", tmp_project_root)

        excel_path = os.path.join(tmp_project_root, "custom_mapping.xlsx")
        df = pd.DataFrame({
            "原始身份": ["教师"],
            "最终身份": ["教育从业者"],
        })
        df.to_excel(excel_path, index=False, engine='openpyxl')

        result = load_identity_mapping("custom_mapping.xlsx")
        assert result == {"教师": "教育从业者"}

    def test_load_nonexistent_file_raises_error(self, tmp_project_root, monkeypatch):
        # type: (...) -> None
        """加载不存在的 Excel 文件时抛出 FileNotFoundError。"""
        monkeypatch.setenv("USER_PROFILE_ROOT", tmp_project_root)

        with pytest.raises(FileNotFoundError):
            load_identity_mapping("nonexistent.xlsx")
