"""
Text-to-IR 主流程
==================

整合三阶段解析器，完成从自然语言到结构化 IR 的转换。
"""

import dspy
import json
from .ir_models import NL2SQL_IR
from .ir_parsers import (
    ClauseDeconstructor,
    FilterParser,
    HavingParser
)


class TextToIR_Pydantic_Complete(dspy.Module):
    """
    使用三阶段 Pydantic TypedPredictor 流水线将 NL 转换为最终的 NL2SQL_IR。

    此版本接受预先筛选的候选实体和枚举值，以提高准确性。
    
    流程:
    1. ClauseDeconstructor - 提取主要子句和 NL 过滤字符串
    2. FilterParser (条件) - 解析 WHERE 条件为结构化 FilterGroup
    3. HavingParser (条件) - 解析 HAVING 条件为结构化 FilterGroup
    4. 组装最终的 NL2SQL_IR 对象
    """

    def __init__(self):
        super().__init__()
        self.deconstructor = ClauseDeconstructor()
        self.filter_parser = FilterParser()
        self.having_parser = HavingParser()

    def forward(self, nl_query, candidate_metrics, candidate_attributes, attribute_enum_values):

        # 将输入转换为字符串，以便安全地传递给 LLM
        metrics_str = json.dumps(candidate_metrics)
        attributes_str = json.dumps(candidate_attributes)
        enums_str = json.dumps(attribute_enum_values)

        # --- 阶段一: LLM 调用 #1 (总是执行) ---
        deconstructed_clauses = self.deconstructor(
            nl_query=nl_query,
            candidate_metrics=metrics_str,
            candidate_attributes=attributes_str,
            attribute_enum_values=enums_str
        )

        # --- 阶段二: LLM 调用 #2 (有条件) ---
        parsed_filter_group = None
        if deconstructed_clauses.filter_nl_string:
            try:
                parsed_filter_group = self.filter_parser(
                    filter_nl_string=deconstructed_clauses.filter_nl_string,
                    candidate_attributes=attributes_str,
                    attribute_enum_values=enums_str
                )
            except Exception as e:
                print(f"[Filter parsing failed]: {e}")
                # 在真实的 DSPy 程序中, 你可以在这里 dspy.Assert()
                # 来触发自动化的 few-shot 优化
                pass

        # --- 阶段三: LLM 调用 #3 (有条件) ---
        parsed_having_group = None
        if deconstructed_clauses.having_nl_string:
            try:
                # 提取别名作为上下文
                aliases = [
                    p.alias for p in deconstructed_clauses.projections
                    if p.alias
                ]
                aliases_str = json.dumps(aliases)

                parsed_having_group = self.having_parser(
                    having_nl_string=deconstructed_clauses.having_nl_string,
                    projection_aliases=aliases_str,
                    candidate_metrics=metrics_str,
                    candidate_attributes=attributes_str,
                    attribute_enum_values=enums_str
                )
            except Exception as e:
                print(f"[Having parsing failed]: {e}")
                pass

        # --- 组装: 确定性的 Python 代码 ---
        # 我们在这里组装最终的、完整的 IR Pydantic 对象
        final_ir = NL2SQL_IR(
            intent=deconstructed_clauses.intent,
            projections=deconstructed_clauses.projections,
            filters=parsed_filter_group,
            having=parsed_having_group,
            group_by=deconstructed_clauses.group_by,
            order_by=deconstructed_clauses.order_by,
            limit=deconstructed_clauses.limit,
            offset=deconstructed_clauses.offset
        )

        return dspy.Prediction(ir=final_ir)
