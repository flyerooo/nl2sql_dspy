import json
import re
import json5
from collections import defaultdict
from pathlib import Path

class SQLCompiler:
    """
    一个将 IR (中间表示) 和语义层编译为 SQL 的原型编译器。
    
    警告：这是一个原型，不安全，没有做 SQL 注入防护。
    生产环境必须使用参数化查询。
    """

    def __init__(self, semantic_layer: dict):
        self.entities = semantic_layer["entities"]
        self.foreign_keys = semantic_layer["foreign_keys"]
        self.table_aliases = {}
        self.join_path = [] # 将存储 (fk_definition, from_table, to_table)
        self.required_tables = set()

    def compile(self, ir: dict) -> str:
        """主编译方法"""
        self.table_aliases = {}
        self.join_path = []
        self.required_tables = set()

        # 1. 收集所有需要的实体
        all_entities = self._collect_all_entities(ir)

        # 2. 查找所有必需的表
        self.required_tables = self._find_required_tables(all_entities)

        # 3. 自动计算 JOIN 路径 (核心)
        self.join_path = self._build_join_path(self.required_tables)
        
        # 4. 生成表别名 (例如: {'products': 't1', 'orders': 't2'})
        all_tables_in_path = self.required_tables.union(
            set(fk['from_table'] for fk in self.join_path)
        ).union(
            set(fk['to_table'] for fk in self.join_path)
        )
        self.table_aliases = {table: f"t{i+1}" for i, table in enumerate(all_tables_in_path)}
        
        # 5. 生成 SQL 的各个子句
        select_clause = self._build_select(ir.get("projections", []))
        from_join_clause = self._build_from_join(all_tables_in_path)
        where_clause = self._build_where(ir.get("filters"))
        group_by_clause = self._build_group_by(ir.get("group_by", []))
        having_clause = self._build_having(ir.get("having")) # 类似 _build_where
        order_by_clause = self._build_order_by(ir.get("order_by", []))
        limit_offset_clause = self._build_limit_offset(ir)

        # 6. 组装 SQL
        sql_parts = [
            select_clause,
            from_join_clause,
            where_clause,
            group_by_clause,
            having_clause,
            order_by_clause,
            limit_offset_clause
        ]
        
        return "\n".join(filter(None, sql_parts)) + ";"

    # --- 收集和解析 (Steps 1, 2) ---

    def _collect_all_entities(self, ir: dict) -> set:
        """递归收集 IR 中提到的所有实体"""
        entities = set()
        for p in ir.get("projections", []):
            entities.add(p["entity"])
            
        if ir.get("filters"):
            self._collect_entities_from_filter(ir["filters"], entities)
            
        for g in ir.get("group_by", []):
            entities.add(g["entity"])
            
        for o in ir.get("order_by", []):
            # order_by 的 'field' 可能是别名，也可能是实体
            if o["field"] in self.entities:
                 entities.add(o["field"])
                 
        if ir.get("having"):
             # 假设 having 的 entity_alias 是别名，但如果它也是实体...
             self._collect_entities_from_filter(ir["having"], entities)

        return entities

    def _collect_entities_from_filter(self, node: dict, entities: set):
        """递归遍历 filters/having 树"""
        if "conditions" in node:
            for cond in node["conditions"]:
                self._collect_entities_from_filter(cond, entities)
        elif "entity" in node:
            entities.add(node["entity"])
        elif "entity_alias" in node:
            # 别名可能与实体同名
            if node["entity_alias"] in self.entities:
                entities.add(node["entity_alias"])


    def _find_required_tables(self, entities: set) -> set:
        """根据实体查找所需的物理表"""
        tables = set()
        for entity_name in entities:
            if entity_name not in self.entities:
                # 警告：实体未在语义层中定义（可能是别名）
                continue
            
            entity_def = self.entities[entity_name]
            if "table" in entity_def:
                tables.add(entity_def["table"])
            elif "tables_needed" in entity_def:
                tables.update(entity_def["tables_needed"])
        return tables

    # --- JOIN 逻辑 (Step 3) ---

    def _build_join_path(self, required_tables: set) -> list:
        """
        [核心逻辑 - 简化版]
        构建一个连接所有 required_tables 的 JOIN 路径。
        这是一个图遍历问题（寻找最小生成树）。
        
        这个简化版使用 BFS 查找连接所有表的边。
        """
        if not required_tables:
            return []

        # 1. 构建图 (邻接表)
        graph = defaultdict(list)
        for fk in self.foreign_keys:
            graph[fk["from_table"]].append((fk["to_table"], fk))
            graph[fk["to_table"]].append((fk["from_table"], fk))

        # 2. BFS 寻找连接所有表的路径
        join_edges = []
        tables_to_find = set(required_tables)
        
        start_table = list(tables_to_find)[0]
        tables_to_find.remove(start_table)
        
        queue = [start_table]
        visited = {start_table}
        
        while queue and tables_to_find:
            current_table = queue.pop(0)
            
            for neighbor, fk_def in graph[current_table]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
                    
                    # 检查这个 FK 是否是我们需要的（连接两个方向）
                    # (这是一个简化的检查，实际可能更复杂)
                    if fk_def["from_table"] == current_table and fk_def["to_table"] == neighbor:
                        join_edges.append(fk_def)
                    elif fk_def["to_table"] == current_table and fk_def["from_table"] == neighbor:
                        join_edges.append(fk_def)
                        
                    if neighbor in tables_to_find:
                        tables_to_find.remove(neighbor)

        # TODO: 检查 tables_to_find 是否为空，否则意味着无法连接所有表
        return join_edges

    # --- 实体解析 (Helper) ---

    def _resolve_entity(self, entity_name: str) -> str:
        """将语义实体（如 'product_name'）解析为物理 SQL（如 't1.product_name'）"""
        if entity_name not in self.entities:
            raise ValueError(f"实体 '{entity_name}' 未在语义层中定义。")
            
        entity_def = self.entities[entity_name]
        
        if "table" in entity_def:
            # 简单列
            table_name = entity_def["table"]
            alias = self.table_aliases[table_name]
            return f"{alias}.{entity_def['column']}"
        
        elif "expression" in entity_def:
            # 复杂表达式
            expression = entity_def["expression"]
            # 用别名替换表达式中的物理表名
            # 例如: "order_items.quantity * order_items.unit_price"
            # -> "t2.quantity * t2.unit_price"
            for table_name in entity_def["tables_needed"]:
                alias = self.table_aliases[table_name]
                expression = re.sub(r'\b' + re.escape(table_name) + r'\.', f"{alias}.", expression)
            return expression

    def _resolve_field_or_alias(self, field_name: str) -> str:
        """用于 ORDER BY，字段可能是实体也可能是别名"""
        if field_name in self.entities:
            return self._resolve_entity(field_name)
        else:
            # 假设是 SELECT 中的别名，直接返回
            # 警告：不安全，未检查别名是否合法
            return f'"{field_name}"' # 使用引号以防万一

    # --- SQL 子句生成 (Steps 5, 6) ---

    def _build_select(self, projections: list) -> str:
        if not projections:
            return "SELECT *"
            
        select_parts = []
        for p in projections:
            resolved_entity = self._resolve_entity(p["entity"])
            
            if p.get("type") == "aggregation":
                part = f"{p['op']}({resolved_entity})"
            else: # type == "entity"
                part = resolved_entity
                
            if "alias" in p:
                part += f" AS \"{p['alias']}\""
                
            select_parts.append(part)
            
        return "SELECT " + ", ".join(select_parts)

    def _build_from_join(self, all_tables: set) -> str:
        """构建 FROM 和 INNER JOIN 子句"""
        if not all_tables:
            return ""
            
        # 选择一个根表 (例如，在 join_path 中最常出现的表)
        # 简化：就选第一个必需的表
        root_table = list(self.required_tables)[0]
        from_clause = f"FROM {root_table} {self.table_aliases[root_table]}"
        
        join_clauses = []
        joined_tables = {root_table}

        # 使用我们计算的 join_path
        # TODO: 这是一个简化的 JOIN 逻辑，未处理复杂的树形 JOIN
        for fk in self.join_path:
            # 确定方向
            if fk["from_table"] in joined_tables and fk["to_table"] not in joined_tables:
                from_alias = self.table_aliases[fk["from_table"]]
                to_table = fk["to_table"]
                to_alias = self.table_aliases[to_table]
                on_clause = f"{from_alias}.{fk['from_column']} = {to_alias}.{fk['to_column']}"
                joined_tables.add(to_table)
            elif fk["to_table"] in joined_tables and fk["from_table"] not in joined_tables:
                from_alias = self.table_aliases[fk["to_table"]]
                to_table = fk["from_table"]
                to_alias = self.table_aliases[to_table]
                on_clause = f"{from_alias}.{fk['to_column']} = {to_alias}.{fk['from_column']}"
                joined_tables.add(to_table)
            else:
                # 两个表都已连接，或者都未连接（需要更复杂的树逻辑）
                continue
                
            join_clauses.append(f"INNER JOIN {to_table} {to_alias} ON {on_clause}")

        return from_clause + "\n" + "\n".join(join_clauses)


    def _build_where(self, filters: dict) -> str:
        if not filters:
            return ""
        
        where_str = self._build_filter_node(filters)
        return f"WHERE {where_str}"
    
    def _build_having(self, having: dict) -> str:
        if not having:
            return ""
        
        # 'entity_alias' 替换为 'entity' 供 _build_filter_node 使用
        # 这是一个 hack，更好的方法是让 _build_filter_node 处理两种情况
        having_str = json.dumps(having).replace("entity_alias", "entity")
        having_node = json.loads(having_str)
        
        # 假设 having 中的 'entity' 都是别名
        having_str = self._build_filter_node(having_node, is_having=True)
        return f"HAVING {having_str}"

    def _build_filter_node(self, node: dict, is_having=False) -> str:
        """递归构建 WHERE / HAVING 的条件树"""
        if "operator" in node:
            # 逻辑节点 (AND / OR)
            conditions = [self._build_filter_node(cond, is_having) for cond in node.get("conditions", [])]
            return f"({' ' + node['operator'] + ' '.join(conditions)})"
        else:
            # 叶节点 (比较)
            if is_having:
                # 在 HAVING 中，'entity' 只是一个别名
                resolved_entity = f"\"{node['entity']}\""
            else:
                resolved_entity = self._resolve_entity(node["entity"])
                
            op = self._map_operator(node["op"])
            val = self._format_value(node["value"])
            
            # TODO: 处理 'LAST_MONTH' 等语义操作符
            if op == "IN":
                return f"{resolved_entity} IN {val}"
            else:
                return f"{resolved_entity} {op} {val}"

    def _map_operator(self, op: str) -> str:
        """将 IR 操作符映射到 SQL 操作符"""
        mapping = {
            "EQUAL": "=",
            "NOT_EQUAL": "!=",
            "GREATER_THAN": ">",
            "LESS_THAN": "<",
            "GTE": ">=",
            "LTE": "<=",
            "IN": "IN",
            "CONTAINS": "LIKE"
            # TODO: 添加 'LAST_MONTH', 'THIS_YEAR' 等语义操作符
        }
        if op not in mapping:
            raise ValueError(f"不支持的操作符: {op}")
        return mapping[op]

    def _format_value(self, value) -> str:
        """
        格式化 SQL 值（并进行基本的安全处理）。
        警告：不安全！生产环境必须用参数化查询。
        """
        if isinstance(value, str):
            # 粗略的清理
            safe_value = value.replace("'", "''")
            return f"'{safe_value}'"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, list):
            return f"({', '.join(self._format_value(v) for v in value)})"
        return "NULL" # 默认

    def _build_group_by(self, group_by: list) -> str:
        if not group_by:
            return ""
        
        parts = [self._resolve_entity(g["entity"]) for g in group_by]
        return "GROUP BY " + ", ".join(parts)

    def _build_order_by(self, order_by: list) -> str:
        if not order_by:
            return ""
            
        parts = []
        for o in order_by:
            resolved_field = self._resolve_field_or_alias(o["field"])
            direction = o.get("direction", "ASC")
            parts.append(f"{resolved_field} {direction}")
            
        return "ORDER BY " + ", ".join(parts)

    def _build_limit_offset(self, ir: dict) -> str:
        parts = []
        if "limit" in ir:
            parts.append(f"LIMIT {int(ir['limit'])}")
        if "offset" in ir:
            parts.append(f"OFFSET {int(ir['offset'])}")
        return "\n".join(parts)


# 示例 IR: “上个月，中国区销售额最高的 5 个产品是什么，以及它们的总销售额？”
# (注意：'LAST_MONTH' 并未在此原型中实现，我们用 'GTE' 替代)
IR_QUERY = {
  "projections": [
    { "type": "entity", "entity": "product_name" },
    { 
      "type": "aggregation", 
      "op": "SUM", 
      "entity": "sales_amount", 
      "alias": "total_sales" 
    }
  ],
  "filters": {
    "operator": "AND",
    "conditions": [
      {
        "entity": "region", 
        "op": "EQUAL", 
        "value": "中国"
      },
      {
        "entity": "order_date", 
        "op": "GTE", 
        "value": "2025-09-01" # 假设我们手动替换了 'LAST_MONTH'
      }
    ]
  },
  "group_by": [
    { "entity": "product_name" }
  ],
  "order_by": [
    { "field": "total_sales", "direction": "DESC" }
  ],
  "limit": 5
}

# --- 辅助函数：从文件加载语义层 ---
def load_semantic_layer(entity_map_path: str = None) -> dict:
    """从 entity_map.json5 文件加载语义层"""
    if entity_map_path is None:
        # 默认路径：项目根目录
        entity_map_path = Path(__file__).parent.parent / "entity_map.json5"
    
    if isinstance(entity_map_path, str):
        entity_map_path = Path(entity_map_path)
    
    if not entity_map_path.exists():
        raise FileNotFoundError(f"语义层文件不存在: {entity_map_path}")
    
    with open(entity_map_path, "r", encoding="utf-8") as f:
        return json5.load(f)


# --- 示例 IR 和执行代码（主程序入口）---
if __name__ == "__main__":
    print("--- 正在编译 SQL ---")
    
    # 1. 加载语义层
    try:
        SEMANTIC_LAYER = load_semantic_layer()
        print(f"✓ 已加载语义层，包含 {len(SEMANTIC_LAYER.get('entities', {}))} 个实体")
    except Exception as e:
        print(f"❌ 加载语义层失败: {e}")
        exit(1)
    
    # 2. 初始化编译器
    compiler = SQLCompiler(SEMANTIC_LAYER)
    
    # 3. 编译 IR
    try:
        sql = compiler.compile(IR_QUERY)
        print("\n--- 编译结果 ---")
        print(sql)

        print("\n--- 编译器内部状态 (调试用) ---")
        print(f"必需的表: {compiler.required_tables}")
        print(f"表别名: {json.dumps(compiler.table_aliases, indent=2, ensure_ascii=False)}")
        print(f"JOIN 路径: {json.dumps(compiler.join_path, indent=2, ensure_ascii=False)}")

    except Exception as e:
        print(f"编译失败: {e}")
        import traceback
        traceback.print_exc()