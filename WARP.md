# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

NL2SQL-IR is a Text-to-SQL system using an Intermediate Representation (IR) architecture combined with DSPy framework. It converts natural language questions to SQL through a three-stage pipeline:
1. **Candidate Entity Extraction** - Identifies relevant metrics and attributes
2. **IR Generation** - Uses LLM to construct structured intermediate representation
3. **SQL Compilation** - Deterministically compiles IR to SQL with automatic JOIN path resolution

## Common Commands

### Installation
```pwsh
pip install dspy-ai pydantic json5
```

### Run Main Pipeline
```pwsh
cd src
python nl2sql_pipeline.py
```

### Run Tests
```pwsh
cd tests
python test_pipeline.py
```

### Run Individual Test Functions
Open `tests/test_pipeline.py` and execute specific test functions:
- `test_basic_queries()` - Basic SELECT and WHERE queries
- `test_aggregation_queries()` - GROUP BY and aggregation functions
- `test_complex_queries()` - Multi-clause queries with filters, ordering, limits
- `test_error_handling()` - Edge cases and error scenarios

## Architecture

### Three-Stage Pipeline Design

The system decouples LLM understanding from SQL generation through a structured IR:

**Stage 1: ClauseDeconstructor** (`clause_deconstructor.py`)
- Uses `dspy.TypedPredictor` to parse NL query into `DeconstructedClauses` Pydantic model
- Extracts: projections, group_by, order_by, limit, offset
- Defers complex parsing by outputting NL strings for filters/having

**Stage 2: FilterParser** (conditional)
- Parses `filter_nl_string` into recursive `FilterGroup` structure
- Supports nested AND/OR conditions, comparison operators (EQUAL, IN, LIKE, etc.)
- Uses `attribute_enum_values` for value normalization (e.g., "中国区" → "中国")

**Stage 3: HavingParser** (conditional)
- Similar to FilterParser but operates on aggregated results
- References projection aliases from Stage 1

**Final Assembly**: `TextToIR_Pydantic_Complete` combines all stages into `NL2SQL_IR` Pydantic model

### Semantic Layer Architecture

**Entity Map** (`entity_map.json5`):
- **entities**: Maps business concepts to physical tables/columns
  - `attribute`: Simple columns (product_name, region)
  - `metric`: Computed expressions (sales_amount = quantity × unit_price)
- **foreign_keys**: Defines table relationships for automatic JOIN generation
- **enum_values**: Valid values for attributes to aid LLM normalization

**SQL Compiler** (`sql_compiler.py`):
- Collects all entities referenced in IR
- Uses BFS graph traversal on foreign_keys to compute minimal JOIN path
- Resolves entities to physical SQL (e.g., `product_name` → `t1.name`)
- Generates complete SQL with automatic table aliasing

### Key Data Structures

**NL2SQL_IR** (final IR):
```python
{
  "intent": str,
  "projections": [{"entity": str, "op": str, "alias": str}],
  "filters": FilterGroup,  # Recursive: {operator: AND/OR, conditions: [...]}
  "group_by": [{"entity": str}],
  "having": FilterGroup,
  "order_by": [{"field": str, "direction": ASC/DESC}],
  "limit": int,
  "offset": int
}
```

### DSPy Integration

- Uses `dspy.TypedPredictor` with Pydantic models for type-safe LLM outputs
- Automatic JSON validation and retry on parsing failures
- Supports optimization with `BootstrapFewShot` for few-shot learning
- Configure LLM in pipeline scripts before execution

## LLM Configuration

Before running any scripts, configure DSPy with your LLM in the main file or test script:

**Option 1: OpenAI**
```python
gpt4_turbo = dspy.OpenAI(
    model='gpt-4-1106-preview',
    api_key='YOUR_API_KEY',
    max_tokens=4096
)
dspy.settings.configure(lm=gpt4_turbo)
```

**Option 2: Local Ollama** (default in examples)
```python
ollama_lm = dspy.OllamaLocal(
    model='llama3',
    max_tokens=4096
)
dspy.settings.configure(lm=ollama_lm)
```

## Entity Map Configuration

When modifying `entity_map.json5`:
1. Define all business entities in `entities` section
2. Add foreign key relationships in `foreign_keys` for automatic JOIN support
3. Update `enum_values` for attributes with constrained value sets
4. Test with sample queries to verify entity resolution

Entity types:
- **attribute**: Use for filterable/groupable columns (region, product_name)
- **metric**: Use for computed/aggregated values (sales_amount, customer_count)

## Supported SQL Features

✅ **Supported**:
- SELECT projections (simple columns, aggregations: SUM, COUNT, AVG, MAX, MIN)
- WHERE filters (comparisons, IN, LIKE, IS NULL, nested AND/OR)
- GROUP BY, HAVING, ORDER BY, LIMIT, OFFSET
- Automatic JOIN calculation from foreign_keys

❌ **Not Supported** (requires extension):
- Subqueries, window functions, CTEs, UNION, CASE statements

## Candidate Entity Extraction

The pipeline uses `SimpleCandidateExtractor` for keyword-based entity matching:
- Fuzzy matches entity names against the user question
- Filters relevant metrics and attributes from `entity_map.json5`
- Provides enum values for candidate attributes to aid LLM normalization
- Suitable for most use cases; can be replaced with more sophisticated retrieval systems if needed

## File Organization

```
nl2sql_dspy/
├── entity_map.json5              # Semantic layer configuration
├── src/
│   ├── clause_deconstructor.py   # Stage 1-3: IR generation (DSPy modules)
│   ├── sql_compiler.py           # IR → SQL compiler with JOIN resolution
│   └── nl2sql_pipeline.py        # End-to-end pipeline orchestration
├── tests/
│   └── test_pipeline.py          # Integration tests
└── data/
    ├── entity_map_example.json5  # Example configurations
    └── intermediate_representation.json5
```

## Development Notes

- **TypedPredictor**: Always use with Pydantic models for type-safe LLM outputs
- **FilterGroup recursion**: Pydantic v2 handles forward references automatically
- **JOIN algorithm**: BFS graph traversal finds minimal spanning tree of required tables
- **Security**: Current SQL compiler is prototype-level; use parameterized queries for production
- **Error handling**: Filter/Having parsing failures are caught but IR is still returned
- **Optimization**: Use DSPy's `BootstrapFewShot` optimizer to improve LLM accuracy with few-shot examples

## Extending the System

**Adding new operators**:
1. Add operator to Pydantic models in `clause_deconstructor.py`
2. Implement operator mapping in `sql_compiler.py::_map_operator()`
3. Update tests

**Adding new tables**:
1. Define entities in `entity_map.json5`
2. Add foreign_keys for relationships
3. Update enum_values if needed
4. Verify with test queries

**Improving LLM performance**:
- Prepare training dataset of (question, expected_ir) pairs
- Use DSPy optimizers: `BootstrapFewShot`, `MIPRO`
- Monitor LLM calls with `dspy.inspect_history()`
