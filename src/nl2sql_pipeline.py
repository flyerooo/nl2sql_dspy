"""
NL2SQL-IR 完整流程
====================

这个模块整合了从自然语言问题到 SQL 查询的完整流程:
1. 候选实体提取 (SimpleCandidateExtractor)
2. 问题解构为中间表示 (ClauseDeconstructor)
3. 中间表示编译为 SQL (SQLCompiler)
"""

import dspy
import json
import json5
from pathlib import Path
from typing import Dict, List, Optional, Any
from pydantic import BaseModel

from src.sql_compiler import SQLCompiler
from .text_to_ir import TextToIR_Pydantic_Complete
from .ir_models import NL2SQL_IR
from .llm_config import configure_azure_openai


class EntityMapLoader:
    """加载并管理语义层配置(entity_map.json5)"""
    
    def __init__(self, entity_map_path: Optional[Path] = None):
        if entity_map_path is None:
            entity_map_path = Path(__file__).parent.parent / "entity_map.json5"
        
        self.entity_map_path = Path(entity_map_path)
        self.semantic_layer = self._load()
    
    def _load(self) -> dict:
        """从文件加载语义层"""
        if not self.entity_map_path.exists():
            raise FileNotFoundError(f"语义层文件不存在: {self.entity_map_path}")
        
        with open(self.entity_map_path, "r", encoding="utf-8") as f:
            return json5.load(f)
    
    def get_candidate_metrics(self) -> List[str]:
        """获取所有候选指标"""
        entities = self.semantic_layer.get("entities", {})
        metrics = []
        
        for name, entity_def in entities.items():
            # 指标通常是需要聚合的、或者带有 expression 的实体
            if "expression" in entity_def or entity_def.get("type") == "metric":
                metrics.append(name)
        
        return metrics
    
    def get_candidate_attributes(self) -> List[str]:
        """获取所有候选属性"""
        entities = self.semantic_layer.get("entities", {})
        attributes = []
        
        for name, entity_def in entities.items():
            # 属性通常是可以用于过滤、分组的简单列
            if "table" in entity_def and "column" in entity_def:
                attributes.append(name)
        
        return attributes
    
    def get_attribute_enum_values(self) -> Dict[str, List[str]]:
        """获取属性的枚举值"""
        return self.semantic_layer.get("enum_values", {})


class SimpleCandidateExtractor:
    """
    简化版的候选实体提取器
    
    基于关键词匹配来筛选候选实体。
    可以替换为更复杂的实现(向量检索、LLM理解等)。
    """
    
    def __init__(self, entity_map_loader: EntityMapLoader):
        self.entity_map_loader = entity_map_loader
        self.all_metrics = entity_map_loader.get_candidate_metrics()
        self.all_attributes = entity_map_loader.get_candidate_attributes()
        self.enum_values = entity_map_loader.get_attribute_enum_values()
    
    def extract_candidates(
        self, 
        question: str,
        max_metrics: int = 10,
        max_attributes: int = 15
    ) -> Dict[str, Any]:
        """
        基于关键词匹配提取候选实体
        
        Args:
            question: 用户问题
            max_metrics: 最大返回指标数量
            max_attributes: 最大返回属性数量
        
        Returns:
            包含候选指标、属性和枚举值的字典
        """
        # 简单的关键词匹配(可以替换为更复杂的语义匹配)
        question_lower = question.lower()
        
        # 匹配指标
        candidate_metrics = []
        for metric in self.all_metrics:
            if self._fuzzy_match(metric, question_lower):
                candidate_metrics.append(metric)
        
        # 如果匹配太少,返回所有指标
        if len(candidate_metrics) < 2:
            candidate_metrics = self.all_metrics[:max_metrics]
        
        # 匹配属性
        candidate_attributes = []
        for attr in self.all_attributes:
            if self._fuzzy_match(attr, question_lower):
                candidate_attributes.append(attr)
        
        # 如果匹配太少,返回所有属性
        if len(candidate_attributes) < 2:
            candidate_attributes = self.all_attributes[:max_attributes]
        
        # 只返回相关的枚举值
        relevant_enum_values = {
            attr: values 
            for attr, values in self.enum_values.items()
            if attr in candidate_attributes
        }
        
        return {
            "metrics": candidate_metrics,
            "attributes": candidate_attributes,
            "enum_values": relevant_enum_values
        }
    
    def _fuzzy_match(self, entity: str, question: str) -> bool:
        """简单的模糊匹配:检查实体的任意子串是否在问题中"""
        entity_lower = entity.lower()
        
        # 完全匹配
        if entity_lower in question:
            return True
        
        # 检查实体的每个"词"(由下划线分隔)
        for part in entity_lower.split('_'):
            if len(part) >= 2 and part in question:
                return True
        
        return False


class NL2SQLPipeline:
    """
    完整的 NL2SQL 流程
    ====================
    
    将自然语言问题转换为可执行的 SQL 查询。
    
    流程:
    1. 加载语义层 (entity_map.json5)
    2. 提取候选实体 (SimpleCandidateExtractor)
    3. 将问题解构为 IR (TextToIR_Pydantic_Complete)
    4. 将 IR 编译为 SQL (SQLCompiler)
    """
    
    def __init__(
        self, 
        entity_map_path: Optional[Path] = None,
        use_simple_extractor: bool = True
    ):
        """
        Args:
            entity_map_path: 语义层配置文件路径
            use_simple_extractor: 是否使用简化版候选提取器
                                 (False时需要提供自定义实现)
        """
        self.entity_map_loader = EntityMapLoader(entity_map_path)
        
        if use_simple_extractor:
            self.candidate_extractor = SimpleCandidateExtractor(self.entity_map_loader)
        else:
            # 需要手动设置 self.candidate_extractor 为自定义实现
            raise NotImplementedError("请提供自定义的候选提取器实现")
        
        # 初始化 IR 生成器 (DSPy模块)
        self.ir_generator = TextToIR_Pydantic_Complete()
        
        # 初始化 SQL 编译器
        self.sql_compiler = SQLCompiler(self.entity_map_loader.semantic_layer)
    
    def execute(
        self, 
        question: str,
        return_ir: bool = False,
        verbose: bool = True
    ) -> Dict[str, Any]:
        """
        执行完整的 NL2SQL 流程
        
        Args:
            question: 用户的自然语言问题
            return_ir: 是否在结果中返回中间表示(IR)
            verbose: 是否打印详细日志
        
        Returns:
            包含 SQL 和可选的 IR 的字典
        """
        if verbose:
            print(f"\n{'='*60}")
            print(f"问题: {question}")
            print(f"{'='*60}")
        
        # 步骤1: 提取候选实体
        if verbose:
            print("\n[步骤 1/3] 提取候选实体...")
        
        candidates = self.candidate_extractor.extract_candidates(question)
        
        if verbose:
            print(f"  候选指标 ({len(candidates['metrics'])}): {candidates['metrics'][:5]}...")
            print(f"  候选属性 ({len(candidates['attributes'])}): {candidates['attributes'][:5]}...")
        
        # 步骤2: 生成中间表示(IR)
        if verbose:
            print("\n[步骤 2/3] 生成中间表示 (IR)...")
        
        result = self.ir_generator(
            nl_query=question,
            candidate_metrics=candidates["metrics"],
            candidate_attributes=candidates["attributes"],
            attribute_enum_values=candidates["enum_values"]
        )
        
        ir: NL2SQL_IR = result.ir
        
        if verbose:
            print(f"  Intent: {ir.intent}")
            print(f"  Projections: {len(ir.projections)}")
            print(f"  Filters: {'✓' if ir.filters else '✗'}")
            print(f"  Group By: {len(ir.group_by)}")
            print(f"  Having: {'✓' if ir.having else '✗'}")
        
        # 步骤3: 编译为 SQL
        if verbose:
            print("\n[步骤 3/3] 编译为 SQL...")
        
        # 将 Pydantic 模型转换为字典供编译器使用
        ir_dict = json.loads(ir.model_dump_json())
        
        try:
            sql = self.sql_compiler.compile(ir_dict)
            
            if verbose:
                print("\n✅ SQL 生成成功!")
                print(f"\n{sql}")
        
        except Exception as e:
            if verbose:
                print(f"\n❌ SQL 编译失败: {e}")
            raise
        
        # 准备返回结果
        result_dict = {
            "question": question,
            "sql": sql,
            "status": "success"
        }
        
        if return_ir:
            result_dict["ir"] = ir_dict
        
        return result_dict


def main():
    """示例用法"""
    
    print("初始化 NL2SQL 流程...")
    
    # 配置 DSPy LLM (使用 Azure OpenAI)
    print("配置 Azure OpenAI LLM...")
    lm = configure_azure_openai()
    print(f"✓ LLM 配置完成\n")
    
    # 初始化流程
    pipeline = NL2SQLPipeline()
    
    # 测试问题
    test_questions = [
        "查询上个月中国区销售额最高的5个产品",
        "有多少客户来自美国?",
        "各地区的平均订单金额是多少?"
    ]
    
    for question in test_questions:
        try:
            result = pipeline.execute(
                question=question,
                return_ir=True,
                verbose=True
            )
            
            print("\n" + "="*60)
            
        except Exception as e:
            print(f"处理失败: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
