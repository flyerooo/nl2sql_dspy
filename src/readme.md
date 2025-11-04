Text-to-SQL 项目。

使用中间表示（Intermediate Representation, IR）。 此IR，需要平衡两大挑战：

表达力（Expressiveness）：能捕捉到自然语言中的模糊性、上下文和复杂意图。

可转换性（Convertibility）：能被确定性地、准确地转换为结构化的 SQL 查询。
这个 IR 结构的设计目标是覆盖绝大多数的分析查询（Analytical Queries）和商业智能（BI）场景。

它支持的 SQL 语法非常丰富，但它通过“语义层”和“编译器”这个架构，巧妙地将最复杂、最容易出错的部分（如 JOIN 逻辑）从 IR 中抽象出去了。

这个 IR 结构的设计目标是覆盖绝大多数的分析查询（Analytical Queries）和商业智能（BI）场景。

它支持的 SQL 语法非常丰富，但它通过“语义层”和“编译器”这个架构，巧妙地将最复杂、最容易出错的部分（如 JOIN 逻辑）从 IR 中抽象出去了。

以下是这个 IR 结构所支持（或要求编译器支持）的 SQL 语法：

1. SELECT 子句
列投影 (Column Projections)：

"projections": [{"entity": "product_name"}]

-> SELECT t1.product_name

聚合函数 (Aggregations)：

"projections": [{"op": "SUM", "entity": "sales_amount"}]

-> SELECT SUM(t2.quantity * t2.unit_price)

(支持 SUM, COUNT, AVG, MAX, MIN, COUNT(DISTINCT ...))

计算字段 (Computed Expressions)：

这是由“语义层”定义的，例如 "sales_amount" 被映射到 order_items.quantity * order_items.unit_price。

-> SELECT ... t2.quantity * t2.unit_price ...

别名 (Aliases)：

"projections": [{"...": "...", "alias": "total_sales"}]

-> SELECT SUM(...) AS total_sales

2. FROM 与 JOIN 子句
这是该架构最强大的地方。IR 本身不定义 FROM 或 JOIN，它只定义需要哪些实体。您的 IR-to-SQL 编译器会：

检查 IR 中所有被引用的 entity (来自 projections, filters 等)。

在“语义层”中查找这些 entity 对应的物理表。

根据“语义层”中定义的 foreign_keys，自动计算出最小必需的 JOIN 路径。

示例：如果 IR 需要 product_name (来自 products 表) 和 region (来自 customers 表)。

编译器行为：会自动查找到 products -> order_items -> orders -> customers 的 JOIN 路径。

支持的 SQL：

FROM table1

INNER JOIN table2 ON t1.key = t2.key

LEFT JOIN ... (如果编译器逻辑支持，例如，在"可选"实体时)

3. WHERE 子句
基本比较：

{"entity": "region", "op": "EQUAL", "value": "中国"}

-> WHERE t4.region = '中国'

(支持 EQUAL, NOT_EQUAL, GREATER_THAN, LESS_THAN, GTE, LTE)

IN / NOT IN 列表：

{"entity": "region", "op": "IN", "value": ["中国", "美国"]}

-> WHERE t4.region IN ('中国', '美国')

IS NULL / IS NOT NULL：

{"entity": "customer_name", "op": "IS_NULL"}

-> WHERE t4.name IS NULL

LIKE 语句：

{"entity": "product_name", "op": "CONTAINS", "value": "电脑"}

-> WHERE t1.product_name LIKE '%电脑%'

复杂逻辑 (AND / OR)：

"filters": {"operator": "AND", "conditions": [...]}

-> WHERE (...) AND (...)

嵌套逻辑：

filters 结构的递归性允许 A AND (B OR C)。

-> WHERE (t1.col_a > 10) AND (t2.col_b = 'X' OR t2.col_c = 'Y')

语义操作符：

{"entity": "order_date", "op": "LAST_MONTH"}

-> 编译器会将其转换为 WHERE t3.order_date BETWEEN '2025-09-01' AND '2025-09-30'

4. GROUP BY 子句
按实体分组：

"group_by": [{"entity": "product_name"}]

-> GROUP BY t1.product_name

5. HAVING 子句
对聚合结果进行过滤：

"having": {"conditions": [{"entity_alias": "total_sales", "op": "GREATER_THAN", "value": 1000}]}

-> HAVING total_sales > 1000

(支持与 WHERE 类似的 AND/OR 嵌套逻辑)

6. ORDER BY 子句
按实体或别名排序：

"order_by": [{"field": "total_sales", "direction": "DESC"}]

-> ORDER BY total_sales DESC

多字段排序：

"order_by": [{"field": "region"}, {"field": "total_sales", "direction": "DESC"}]

-> ORDER BY t4.region ASC, total_sales DESC

7. LIMIT 与 OFFSET 子句
分页：

"limit": 10, "offset": 20

-> LIMIT 10 OFFSET 20

(编译器需要处理 SQL 方言，例如 SQL Server 的 OFFSET ... FETCH NEXT ... 或 Oracle 的语法)

总结：支持什么，不支持什么
这个 IR 结构非常适合：

S-P-J-G-H-O-L 结构的查询（Select, Project, Join, Group, Having, Order, Limit）。

几乎所有的 BI 报表、仪表盘数据和常见的分析问题。

这个 IR 结构没有（或需要重大扩展才能）支持的高级 SQL 语法：

子查询 (Subqueries)：例如 WHERE customer_id IN (SELECT id FROM ...)。IR 中的 value 字段目前只支持字面量。

窗口函数 (Window Functions)：例如 ROW_NUMBER() OVER (PARTITION BY ...)。

公用表表达式 (CTEs)：例如 WITH revenue AS (...) SELECT ... FROM revenue。

UNION / INTERSECT / EXCEPT：合并多个查询结果集。

CASE 语句：SELECT CASE WHEN ... THEN ... ELSE ... END。
这个 IR 结构需要是一个极佳的“甜点位”，它覆盖 80-90% 的业务查询需求，同时通过“语义层”和“编译器”的设计保持了极高的鲁棒性和可维护性。
直接让 LLM 生成 SQL 字符串（Direct-to-SQL）虽然简单，但非常不可靠。它容易出错（语法错误、表名/列名幻觉）、难以调试，且有安全风险。

因此，一个分层的、类似“语义槽位填充”的 JSON 结构被公认为是目前最健壮和可维护的方案。

最佳实践：分层的“语义意图”IR
这种结构的核心思想是**“解耦”**：

LLM 的工作：理解自然语言的“意图”，并填充到对应的“语义槽位”中。它不需要知道表如何 JOIN，也不需要完美记忆列名。

IR to SQL 编译器：获取这个充满“意图”的 IR，然后根据数据库的 Schema（表结构、外键关系），智能地“编译”成最终的 SQL。

