"""
兼容层 (已弃用)
==================

此文件保留用于向后兼容。新代码应该从以下模块导入:
- ir_models: IR 数据模型
- ir_parsers: DSPy 解析器模块  
- text_to_ir: 主流程
"""

import warnings

# 从新模块重新导出所有内容
from .ir_models import (
    ProjectionItem,
    GroupByItem,
    OrderByItem,
    FilterCondition,
    FilterGroup,
    DeconstructedClauses,
    NL2SQL_IR
)

from .ir_parsers import (
    ClauseDeconstructor,
    FilterParser,
    HavingParser
)

from .text_to_ir import TextToIR_Pydantic_Complete

# 显示弃用警告
warnings.warn(
    "直接从 clause_deconstructor 导入已弃用。"
    "请从 ir_models, ir_parsers, 或 text_to_ir 导入。",
    DeprecationWarning,
    stacklevel=2
)

__all__ = [
    # IR 模型
    'ProjectionItem',
    'GroupByItem',
    'OrderByItem',
    'FilterCondition',
    'FilterGroup',
    'DeconstructedClauses',
    'NL2SQL_IR',
    # 解析器
    'ClauseDeconstructor',
    'FilterParser',
    'HavingParser',
    # 主流程
    'TextToIR_Pydantic_Complete'
]
