"""
端到端测试脚本
==================

测试从自然语言问题到 SQL 的完整流程
"""

import sys
from pathlib import Path

from src.llm_config import configure_azure_openai
from src.nl2sql_pipeline import NL2SQLPipeline

# 添加 src 目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))



def setup_llm():
    """配置 LLM (Azure OpenAI)"""
    print("配置 Azure OpenAI LLM...")
    lm = configure_azure_openai()
    print("✓ LLM 配置完成\n")
    return lm


def test_basic_queries():
    """测试基本查询"""
    print("="*80)
    print("测试 1: 基本查询")
    print("="*80)
    
    pipeline = NL2SQLPipeline()
    
    test_cases = [
        {
            "question": "查询所有产品的名称",
            "expected_keywords": ["SELECT", "product", "name"]
        },
        {
            "question": "有多少客户来自中国?",
            "expected_keywords": ["COUNT", "customers", "region", "中国"]
        },
        {
            "question": "列出VIP客户的名称",
            "expected_keywords": ["SELECT", "customer", "name", "VIP"]
        }
    ]
    
    for i, case in enumerate(test_cases, 1):
        print(f"\n测试用例 1.{i}: {case['question']}")
        print("-" * 80)
        
        try:
            result = pipeline.execute(
                question=case["question"],
                return_ir=True,
                verbose=False
            )
            
            sql = result["sql"]
            print(f"✓ SQL 生成成功")
            print(f"\n{sql}\n")
            
            # 简单验证
            sql_upper = sql.upper()
            found = [kw for kw in case["expected_keywords"] if kw.upper() in sql_upper]
            print(f"验证: 找到关键词 {found}/{len(case['expected_keywords'])}")
            
        except Exception as e:
            print(f"✗ 失败: {e}")


def test_aggregation_queries():
    """测试聚合查询"""
    print("\n" + "="*80)
    print("测试 2: 聚合查询")
    print("="*80)
    
    pipeline = NL2SQLPipeline()
    
    test_cases = [
        "每个地区的客户数量",
        "销售额最高的3个产品",
        "各产品类别的平均价格"
    ]
    
    for i, question in enumerate(test_cases, 1):
        print(f"\n测试用例 2.{i}: {question}")
        print("-" * 80)
        
        try:
            result = pipeline.execute(
                question=question,
                verbose=False
            )
            
            print(f"✓ SQL 生成成功")
            print(f"\n{result['sql']}\n")
            
        except Exception as e:
            print(f"✗ 失败: {e}")


def test_complex_queries():
    """测试复杂查询"""
    print("\n" + "="*80)
    print("测试 3: 复杂查询(带过滤、分组、排序)")
    print("="*80)
    
    pipeline = NL2SQLPipeline()
    
    test_cases = [
        "查询中国区销售额最高的5个产品",
        "VIP客户在电子产品类别的总消费金额,按金额降序排列",
        "2024年各地区的订单数量,只显示订单数超过100的地区"
    ]
    
    for i, question in enumerate(test_cases, 1):
        print(f"\n测试用例 3.{i}: {question}")
        print("-" * 80)
        
        try:
            result = pipeline.execute(
                question=question,
                return_ir=True,
                verbose=False
            )
            
            print(f"✓ SQL 生成成功")
            print(f"\n{result['sql']}\n")
            
            # 显示 IR 结构
            ir = result["ir"]
            print("IR 摘要:")
            print(f"  - Projections: {len(ir.get('projections', []))}")
            print(f"  - Filters: {'✓' if ir.get('filters') else '✗'}")
            print(f"  - Group By: {len(ir.get('group_by', []))}")
            print(f"  - Order By: {len(ir.get('order_by', []))}")
            print(f"  - Limit: {ir.get('limit', 'N/A')}")
            
        except Exception as e:
            print(f"✗ 失败: {e}")
            import traceback
            traceback.print_exc()


def test_error_handling():
    """测试错误处理"""
    print("\n" + "="*80)
    print("测试 4: 错误处理")
    print("="*80)
    
    pipeline = NL2SQLPipeline()
    
    # 这些问题可能会导致错误(实体不存在、逻辑不清晰等)
    edge_cases = [
        "查询所有幻觉实体",  # 不存在的实体
        "给我看看",  # 意图不明确
        "帮我分析一下",  # 太模糊
    ]
    
    for i, question in enumerate(edge_cases, 1):
        print(f"\n边界用例 4.{i}: {question}")
        print("-" * 80)
        
        try:
            result = pipeline.execute(
                question=question,
                verbose=False
            )
            
            print(f"结果: {result['status']}")
            if result['status'] == 'success':
                print(f"\n{result['sql']}\n")
            
        except Exception as e:
            print(f"✗ 预期的错误: {type(e).__name__}: {e}")


def run_all_tests():
    """运行所有测试"""
    print("\n" + "█"*80)
    print("█" + " "*30 + "NL2SQL 端到端测试" + " "*30 + "█")
    print("█"*80 + "\n")
    
    # 设置 LLM
    setup_llm()
    
    # 运行测试
    try:
        test_basic_queries()
        test_aggregation_queries()
        test_complex_queries()
        test_error_handling()
        
        print("\n" + "="*80)
        print("所有测试完成!")
        print("="*80 + "\n")
        
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    run_all_tests()
