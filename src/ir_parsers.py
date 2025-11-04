"""
IR 解析器模块
==============

包含三个 DSPy 模块，负责将自然语言解析为结构化的 IR:
1. ClauseDeconstructor - 分解主要子句
2. FilterParser - 解析 WHERE 条件
3. HavingParser - 解析 HAVING 条件
"""

import dspy
from .ir_models import (
    DeconstructedClauses,
    FilterGroup
)


# ==============================================================================
# 阶段一: 主子句解构
# ==============================================================================

class DeconstructQueryTypedSignature(dspy.Signature):
    """
    将自然语言查询分解为其主要的语义条款。

    *** 关键指令 ***
    你必须严格地、且仅能从提供的 "candidate_metrics" 和 "candidate_attributes"
    列表中选择实体。

    使用 "attribute_enum_values" 来帮助识别过滤器中的值。
    """

    nl_query = dspy.InputField(desc="用户的自然语言查询。")
    candidate_metrics = dspy.InputField(desc="待选的指标列表 (e.g., ['sales_amount', 'customer_count'])")
    candidate_attributes = dspy.InputField(desc="待选的属性列表 (e.g., ['region', 'product_name'])")
    attribute_enum_values = dspy.InputField(
        desc="属性及其待选枚举值的 JSON 字典 (e.g., \"{'region': ['中国', '美国']}\")"
    )

    # 输出模型 (DeconstructedClauses) 保证类型安全
    clauses: DeconstructedClauses = dspy.OutputField()


class ClauseDeconstructor(dspy.Module):
    """
    一个 dspy.Module，它安全地将 NL 查询分解为 DeconstructedClauses。
    它在内部使用 TypedPredictor 来确保输出始终是一个有效的 Pydantic 对象，
    自动处理 JSON 验证和重试。
    """

    def __init__(self):
        super().__init__()
        # 使用 TypedPredictor 来保证输出与 Pydantic 模型匹配
        self.predictor = dspy.TypedPredictor(DeconstructQueryTypedSignature)

    def forward(self, nl_query, candidate_metrics, candidate_attributes, attribute_enum_values) -> DeconstructedClauses:
        result = self.predictor(
            nl_query=nl_query,
            candidate_metrics=candidate_metrics,
            candidate_attributes=candidate_attributes,
            attribute_enum_values=attribute_enum_values
        )

        # result.clauses 保证是一个有效的 DeconstructedClauses Pydantic 对象
        return result.clauses


# ==============================================================================
# 阶段二: WHERE 条件解析
# ==============================================================================

class ParseFilterTypedSignature(dspy.Signature):
    """
    将 WHERE 过滤器的自然语言字符串解析为结构化的、嵌套的 FilterGroup JSON。

    *** 关键指令 ***
    你必须严格地、且仅能从 "candidate_attributes" 中选择实体。
    使用 "attribute_enum_values" 来识别和规范化值 (e.g., '中国区' -> '中国')。
    """

    filter_nl_string = dspy.InputField(desc="自然语言过滤器字符串。")
    candidate_attributes = dspy.InputField(desc="待选的属性列表。")
    attribute_enum_values = dspy.InputField(desc="属性及其待选枚举值的 JSON 字典。")

    filter_structure: FilterGroup = dspy.OutputField(
        desc="一个有效的 FilterGroup Pydantic 模型。"
    )


class FilterParser(dspy.Module):
    """
    一个 dspy.Module，它安全地将 NL 过滤器字符串解析为
    一个递归的、结构化的 FilterGroup Pydantic 对象。
    """

    def __init__(self):
        super().__init__()
        self.parser = dspy.TypedPredictor(ParseFilterTypedSignature)

    def forward(self, filter_nl_string, candidate_attributes, attribute_enum_values) -> FilterGroup:
        result = self.parser(
            filter_nl_string=filter_nl_string,
            candidate_attributes=candidate_attributes,
            attribute_enum_values=attribute_enum_values
        )
        return result.filter_structure


# ==============================================================================
# 阶段三: HAVING 条件解析
# ==============================================================================

class ParseHavingTypedSignature(dspy.Signature):
    """
    将 HAVING 过滤器的自然语言字符串解析为结构化的 FilterGroup JSON。

    *** 关键指令 ***
    HAVING 条件优先应用于 'projection_aliases' (聚合的别名)。
    如果别名中没有，再从 'candidate_metrics' 或 'candidate_attributes' 中查找。
    """

    having_nl_string = dspy.InputField(desc="自然语言 HAVING 过滤器字符串。")

    projection_aliases = dspy.InputField(desc="可用于 HAVING 的聚合别名列表。")
    candidate_metrics = dspy.InputField(desc="待选的指标列表。")
    candidate_attributes = dspy.InputField(desc="待选的属性列表。")
    attribute_enum_values = dspy.InputField(desc="属性及其待选枚举值的 JSON 字典。")

    having_structure: FilterGroup = dspy.OutputField(
        desc="一个有效的 FilterGroup Pydantic 模型。"
    )


class HavingParser(dspy.Module):
    """
    一个 dspy.Module，它安全地将 NL having 字符串解析为
    一个递归的、结构化的 FilterGroup Pydantic 对象。
    """

    def __init__(self):
        super().__init__()
        self.parser = dspy.TypedPredictor(ParseHavingTypedSignature)

    def forward(self, having_nl_string, projection_aliases, candidate_metrics, candidate_attributes,
                attribute_enum_values) -> FilterGroup:
        result = self.parser(
            having_nl_string=having_nl_string,
            projection_aliases=projection_aliases,
            candidate_metrics=candidate_metrics,
            candidate_attributes=candidate_attributes,
            attribute_enum_values=attribute_enum_values
        )
        # 注意: TypedPredictor 返回的是一个 Prediction 对象，
        # 我们需要访问 .having_structure 属性
        return result.having_structure
