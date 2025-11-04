import dspy
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Literal, Union, Any
import json


# ==============================================================================
# == 步骤 0: 定义 Pydantic 模型 (IR 的“单一事实来源”)
# ==============================================================================
# 此处 Pydantic v2 (或 v1.10+) 对于处理 Union["FilterGroup", ...] 的
# 前向引用 (ForwardRef) 非常重要。

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


# --- 阶段一 (Deconstructor) 的输出模型 ---

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


# --- 最终 IR 模型 (我们希望得到的最终产品) ---

class ChatBI_IR(BaseModel):
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


# ==============================================================================
# == 步骤 1: 阶段一 (ClauseDeconstructor) 模块
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
# == 步骤 2: 阶段二 (FilterParser) 模块
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
# == 步骤 3: 阶段三 (HavingParser) 模块
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


# ==============================================================================
# == 步骤 4: 主模块 (TextToIR_Pydantic_Complete)
# ==============================================================================

class TextToIR_Pydantic_Complete(dspy.Module):
    """
    (完整版)
    使用三阶段 Pydantic TypedPredictor 流水线将 NL 转换为最终的 ChatBI_IR

    此版本接受预先筛选的候选实体和枚举值，以提高准确性。
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
        final_ir = ChatBI_IR(
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


# ==============================================================================
# == 步骤 5: 示例用法
# ==============================================================================

if __name__ == "__main__":

    print("正在初始化 Text-to-IR 系统...")

    # --- 1. 配置 DSPy (取消注释并替换为你的 LLM) ---

    # 示例: 配置 OpenAI
    # gpt4_turbo = dspy.OpenAI(
    #     model='gpt-4-1106-preview',
    #     api_key='YOUR_API_KEY',
    #     max_tokens=4096
    # )
    # dspy.settings.configure(lm=gpt4_turbo)

    # 示例: 配置本地 Ollama (例如 llama3)
    ollama_lm = dspy.OllamaLocal(
        model='llama3',
        max_tokens=4096
    )
    dspy.settings.configure(lm=ollama_lm)

    # 确保 DSPy  settings 至少有一个 LLM
    if dspy.settings.lm is None:
        print("!!! DSPy LLM 未配置 !!!")
        print("请在 'if __name__ == \"__main__\":' 块中配置 dspy.settings.configure(lm=...)")
        # 退出前创建一个虚拟的 LLM 以便 Pydantic 仍能加载
        # dspy.settings.configure(lm=dspy.HFClientVLLM(model="meta-llama/Llama-2-7b-hf", port=80, url="http://localhost"))
        # exit(1) # 在实际使用中应该退出
        pass  # 允许其继续用于演示

    # --- 2. 准备输入数据 ---

    query = (
        "查询上个月中国区销售额最高的5个产品，"
        "要求这些产品的总销售额必须大于10000，"
        "跳过前2个结果"
    )

    # 你的相似性算法提供的候选集
    metrics = ['sales_amount', 'customer_count', 'avg_price']
    attributes = ['region', 'product_name', 'order_date', 'customer_level']
    enums = {
        'region': ['中国', '美国', '日本', '欧洲'],
        'customer_level': ['VIP', '普通']
    }

    print(f"输入查询: {query}\n")
    print(f"候选指标: {metrics}")
    print(f"候选属性: {attributes}")
    print(f"枚举值: {enums}\n")

    # --- 3. 实例化并运行程序 ---

    try:
        text_to_ir = TextToIR_Pydantic_Complete()

        # 运行流水线
        result = text_to_ir(
            nl_query=query,
            candidate_metrics=metrics,
            candidate_attributes=attributes,
            attribute_enum_values=enums
        )

        # --- 4. 查看结果 ---

        print("---" * 20)
        print("✅ 成功生成 IR!")
        print("---" * 20)

        # 使用 .model_dump_json() 获取格式化的 JSON 输出
        print(result.ir.model_dump_json(indent=2))

        # 你也可以直接访问 Pydantic 对象
        # print(f"\n提取的 Intent: {result.ir.intent}")
        # if result.ir.filters:
        #     print(f"提取的 Filter 条件数量: {len(result.ir.filters.conditions)}")

    except Exception as e:
        print("\n---" * 20)
        print(f"❌ 程序运行出错: {e}")
        print("这通常发生在：")
        print("1. dspy.settings.lm 未配置或配置错误 (例如 API 密钥无效)。")
        print("2. LLM 返回了无法被 Pydantic (即使在重试后) 解析的无效结构。")
        print("   (对于像 Llama3 这样的小模型，这可能需要 few-shot 优化)")
        print("---" * 20)