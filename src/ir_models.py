"""
IR 数据模型定义
================

定义中间表示(Intermediate Representation)的所有 Pydantic 模型。
这些模型是 NL2SQL 系统的"单一事实来源"。
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Union, Any


# ==============================================================================
# 基础 IR 组件
# ==============================================================================

class ProjectionItem(BaseModel):
    """代表一个 SELECT 项 (实体或聚合)"""
    type: Literal["entity", "aggregation"] = "entity"
    entity: str
    op: Optional[Literal["SUM", "COUNT", "AVG", "MAX", "MIN"]] = None
    alias: Optional[str] = None


class GroupByItem(BaseModel):
    """代表一个 GROUP BY 项"""
    entity: str


class OrderByItem(BaseModel):
    """代表一个 ORDER BY 项"""
    field: str
    direction: Literal["ASC", "DESC"] = "ASC"


class FilterCondition(BaseModel):
    """代表一个单独的过滤条件 (e.g., 'region = China')"""
    entity: str
    op: str = Field(..., examples=["EQUAL", "NOT_EQUAL", "GREATER_THAN", "IN", "LAST_MONTH"])
    value: Optional[Any] = None


class FilterGroup(BaseModel):
    """
    代表一个逻辑组 (AND/OR)，它可以嵌套其他组或条件。
    这是我们的递归结构。
    """
    operator: Literal["AND", "OR"] = "AND"
    conditions: List[Union["FilterGroup", FilterCondition]]

    # Pydantic v2 会自动处理 'FilterGroup' 的前向引用
    # 对于 Pydantic v1, 你可能需要 `FilterGroup.update_forward_refs()`


# ==============================================================================
# 中间状态模型
# ==============================================================================

class DeconstructedClauses(BaseModel):
    """
    阶段一 (Deconstructor) 的输出。
    包含所有扁平字段 + 待处理的 filter/having 字符串。
    """
    intent: Optional[str] = Field(
        None,
        description="用户的主要意图 (e.g., 'get_data_list', 'get_aggregation')"
    )
    projections: List[ProjectionItem] = Field(default_factory=list)
    group_by: List[GroupByItem] = Field(default_factory=list)
    order_by: List[OrderByItem] = Field(default_factory=list)
    limit: Optional[int] = None
    offset: Optional[int] = None

    filter_nl_string: Optional[str] = Field(
        None,
        description="所有 WHERE 过滤条件的自然语言描述 (e.g., 'last month AND region is China')"
    )
    having_nl_string: Optional[str] = Field(
        None,
        description="所有 HAVING 过滤条件的自然语言描述 (e.g., 'total_sales > 1000')"
    )


# ==============================================================================
# 最终 IR 模型
# ==============================================================================

class NL2SQL_IR(BaseModel):
    """
    代表最终的、完整的 IR 对象。
    所有字段都是结构化的。
    """
    intent: Optional[str] = None
    projections: List[ProjectionItem] = Field(default_factory=list)
    filters: Optional[FilterGroup] = None
    having: Optional[FilterGroup] = None
    group_by: List[GroupByItem] = Field(default_factory=list)
    order_by: List[OrderByItem] = Field(default_factory=list)
    limit: Optional[int] = None
    offset: Optional[int] = None

    class Config:
        # Pydantic v1 的配置方式
        # anystr_strip_whitespace = True
        # Pydantic v2 的配置方式
        str_strip_whitespace = True
