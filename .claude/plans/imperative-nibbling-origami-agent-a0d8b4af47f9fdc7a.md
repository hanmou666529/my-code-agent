# Executable Skill System -- Implementation Plan

## 1. Overview

Transform the current flat `skills.json` + `skill_matcher.py` + `skill_executor.py` pipeline into a full Executable Skill system where skills are `.skill.md` files containing YAML frontmatter (type signatures, structure requirements, eval cases) and a Python code block (executable logic). The system adds: a parser, a validator, a data model, an improved executor with sandboxed execution, a registry with hot reload, and a standalone Skills MCP server. The old `skills.json` format remains a backward-compatible fallback.

## 2. New Files (all under `src/my_code_agent/skills/`)

```
src/my_code_agent/skills/
  __init__.py          # Re-export key symbols
  models.py            # Dataclasses: SkillDefinition, TypeSignature, StructureRequirement, EvalCase, SkillLevel
  parser.py            # YAML frontmatter + code block parser
  validator.py         # Type signature / structure / safety / code block validators
  executor.py          # Sandboxed execution + output validation + eval runner
  registry.py          # Directory loading + hot reload watcher + index API
```

New MCP server:
```
src/my_code_agent/mcp/skills_server.py   # FastMCP server for skills
```

New tests:
```
tests/test_skills_parser.py
tests/test_skills_validator.py
tests/test_skills_executor.py
tests/test_skills_registry.py
tests/test_skills_server.py
```

New sample skill file:
```
.agent/skills/refactor-function.skill.md
```

## 3. Data Model (`skills/models.py`)

### 3.1 `SkillLevel` Enum

```python
class SkillLevel(Enum):
    L0 = "L0"   # Tool alias -- no code, just a name mapping
    L1 = "L1"   # Simple automation -- runs code block once
    L2 = "L2"   # Structured workflow -- code block + eval gating
    L3 = "L3"   # Full pipeline -- code block + eval + auto-distill candidate
```

### 3.2 `TypeSignature` Dataclass

```python
@dataclass
class TypeSignature:
    inputs: dict[str, str]        # {"file_path": "str", "function_name": "str"}
    outputs: dict[str, str]       # {"success": "bool", "changes": "list[str]"}
    required_fields: set[str]     # union of input keys (for validation)

    def validate_inputs(self, inputs: dict[str, Any]) -> ValidationResult:
        """Check that all required fields are present and types are coercible."""
```

Type coercion supports: `str`, `int`, `float`, `bool`, `list[str]`, `dict[str, Any]`. No arbitrary Python types -- these are plain string annotations.

### 3.3 `StructureRequirement` Dataclass

```python
@dataclass
class StructureRequirement:
    requires: str                 # Directory or file glob, e.g. "tests/"
    purpose: str                  # Why this is required
    optional: bool = False        # L2/L3 skills: non-existent dirs trigger warning, not failure

    def check(self, workspace: Path) -> CheckResult:
        """Return CheckResult with passed=True/False and message."""
```

### 3.4 `EvalCase` Dataclass

```python
@dataclass
class EvalCase:
    name: str
    inputs: dict[str, Any]
    assertions: list[str]         # Natural-language assertion strings
    expected_output: dict[str, Any] | None = None  # Optional typed expected output

    def run_assertions(self, result: SkillResult, workspace: Path) -> bool:
        """Evaluate assertions against the skill execution result."""
```

Assertions are evaluated by:
1. Simple string matching in output (`"file contains 'hello'"`).
2. File existence checks (`"file exists: tests/test_main.py"`).
3. Regex pattern matching (`"regex: r'def hello\('"`).
4. Import checker (`"no broken imports"` -- runs `ast.parse` on referenced files).

### 3.5 `SkillDefinition` Dataclass

```python
@dataclass
class SkillDefinition:
    name: str
    version: str
    level: SkillLevel
    description: str
    type_signature: TypeSignature
    structure_requirements: list[StructureRequirement]
    safety_constraints: list[str]
    eval_cases: list[EvalCase]
    code_block: str               # Python source code of the skill
    match_patterns: list[str]     # From old format, preserved for compatibility
    recommended_tools: list[str]  # From old format, preserved
    context_resources: list[str]  # From old format, preserved
    raw_frontmatter: dict         # Original YAML dict for introspection
    loaded_from: Path             # Where this skill was loaded from
```

### 3.6 `SkillResult` Dataclass

```python
@dataclass
class SkillResult:
    success: bool
    output: dict[str, Any]        # Skill execution return value
    stdout: str = ""              # Printed output captured during execution
    error: str = ""               # Exception message if failed
    eval_pass_rate: float = 0.0   # Fraction of eval cases passed
    eval_results: list[EvalResult] = field(default_factory=list)
    validation_issues: list[str] = field(default_factory=list)
```

### 3.7 `ValidationResult` / `CheckResult`

```python
@dataclass
class ValidationResult:
    pass_: bool
    checks: dict[str, bool]       # {"type_signature": True, "structure": False, ...}
    errors: list[str]

@dataclass
class CheckResult:
    passed: bool
    message: str
```

## 4. Parser (`skills/parser.py`)

### 4.1 `parse_skill_file(path: Path) -> SkillDefinition`

Main entry point. Steps:
1. Read file content.
2. Strip YAML frontmatter between `---` delimiters at the top.
3. Parse YAML into a dict using `yaml.safe_load`.
4. Extract all Python fenced code blocks (```python ... ```) as the executable code.
5. Build and return `SkillDefinition`.

### 4.2 Parsing logic

```python
def _extract_frontmatter(content: str) -> tuple[dict | None, str]:
    """Return (frontmatter_dict, code_content_without_frontmatter)."""
    if not content.startswith("---"):
        return None, content
    end_idx = content.index("---", 3)
    fm = yaml.safe_load(content[3:end_idx])
    return fm, content[end_idx+3:].lstrip("\n")

def _extract_code_blocks(content: str) -> str:
    """Extract the first ```python ... ``` block as skill code."""
    match = re.search(r"```python\s*\n(.*?)```", content, re.DOTALL)
    return match.group(1).strip() if match else ""
```

### 4.3 Field mapping

| Frontmatter field | SkillDefinition field | Default |
|---|---|---|
| `name` | `name` | Required |
| `version` | `version` | "0.0.0" |
| `level` | `level` | SkillLevel.L1 |
| `description` | `description` | "" |
| `type_signature.inputs` | `type_signature.inputs` | {} |
| `type_signature.outputs` | `type_signature.outputs` | {} |
| `structure_requirements[]` | `structure_requirements` | [] |
| `safety_constraints[]` | `safety_constraints` | [] |
| `eval_cases[]` | `eval_cases` | [] |
| Code block | `code_block` | "" |

### 4.4 Backward compatibility: old JSON format

```python
def parse_old_skill_json(skill_dict: dict, path: Path = Path("<json>")) -> SkillDefinition:
    """Convert legacy skills.json entry into a SkillDefinition."""
    # Map the flat JSON to SkillDefinition with empty code_block
    # code_block will be "", meaning this skill has no executable logic
    # The executor handles this as a "no-op" or falls back to LLM dispatch
```

## 5. Validator (`skills/validator.py`)

### 5.1 `validate_skill(skill: SkillDefinition, workspace: Path) -> ValidationResult`

Runs four validation passes:

#### Pass 1: Type Signature Validation

```python
def _validate_type_signature(sig: TypeSignature) -> bool:
    """Verify all types are valid Python type annotations."""
    valid_types = {"str", "int", "float", "bool", "list[str]", "dict[str, Any]",
                   "list", "dict", "Optional[str]", "List[str]", "Dict[str, Any]"}
    for typ in set(sig.inputs.values()) | set(sig.outputs.values()):
        if typ not in valid_types and not _is_valid_annotation(typ):
            return False
    return True
```

`_is_valid_annotation` uses `typing.get_type_hints` in a minimal eval to check if the annotation parses without error.

#### Pass 2: Structure Requirements Validation

```python
def _validate_structure_requirements(
    requirements: list[StructureRequirement], workspace: Path
) -> dict[str, bool]:
    results = {}
    for req in requirements:
        results[req.requires] = req.check(workspace).passed
    return results
```

#### Pass 3: Safety Constraint Validation

Map constraint strings to `SafetyGuard` rules:

| Constraint | Safety Rule |
|---|---|
| `no-delete-public-api` | No `search_replace` on public API files without `git_checkpoint` first |
| `preserve-signature` | Validate function signatures in modified files haven't changed |
| `no-format-changes` | No changes to formatting (whitespace-only diffs are errors) |
| `no-style-only-changes` | No style-only lint fixes without functional changes |
| `preserve-existing-tests` | New test files must not overwrite existing test files |

```python
def _validate_safety_constraints(constraints: list[str]) -> list[str]:
    """Return list of constraint names that are NOT recognized."""
    known = {"no-delete-public-api", "preserve-signature", "no-format-changes",
             "no-style-only-changes", "preserve-existing-tests"}
    return [c for c in constraints if c not in known]
```

Unknown constraints are flagged as warnings, not failures (allows extension).

#### Pass 4: Code Block Validation

```python
def _validate_code_block(code: str) -> ValidationResult:
    """Syntax check + AST analysis of the skill's Python code block."""
    try:
        ast.parse(code)
    except SyntaxError as e:
        return ValidationResult(False, {"syntax": False}, [f"Syntax error: {e}"])

    # AST analysis: check for disallowed operations
    tree = ast.parse(code)
    disallowed = _find_disallowed_operations(tree)
    if disallowed:
        return ValidationResult(False, {"semantics": False}, disallowed)

    return ValidationResult(True, {"syntax": True, "semantics": True}, [])
```

Disallowed operations in skill code:
- `os.system()` calls
- `__import__` usage
- `exec()` / `eval()` on arbitrary strings
- Direct socket creation
- Writing outside workspace (checked by verifying `Path` operations)

### 5.2 Public API

```python
def validate_skill(skill: SkillDefinition, workspace: Path) -> ValidationResult:
    checks = {}
    errors = []

    checks["type_signature"] = _validate_type_signature(skill.type_signature)
    if not checks["type_signature"]:
        errors.append("Invalid type signature annotations")

    struct_results = _validate_structure_requirements(skill.structure_requirements, workspace)
    checks["structure_requirements"] = all(struct_results.values())
    for path, ok in struct_results.items():
        if not ok:
            errors.append(f"Structure requirement not met: {path}")

    unknown = _validate_safety_constraints(skill.safety_constraints)
    checks["safety_constraints"] = len(unknown) == 0
    if unknown:
        errors.append(f"Unknown safety constraints: {unknown}")

    code_result = _validate_code_block(skill.code_block)
    checks.update(code_result.checks)
    errors.extend(code_result.errors)

    return ValidationResult(
        pass_=all(checks.values()),
        checks=checks,
        errors=errors,
    )
```

## 6. Executor (`skills/executor.py`)

### 6.1 Sandboxed Execution

Skill code runs in a restricted globals dict:

```python
SAFE_BUILTINS = {
    "abs": abs, "all": all, "any": any, "bin": bin, "bool": bool,
    "bytes": bytes, "callable": callable, "chr": chr, "compile": compile,
    "complex": complex, "delattr": delattr, "dict": dict, "dir": dir,
    "divmod": divmod, "enumerate": enumerate, "eval": eval,  # only on hardcoded strings
    "filter": filter, "float": float, "format": format, "frozenset": frozenset,
    "getattr": getattr, "hasattr": hasattr, "hash": hash, "hex": hex,
    "id": id, "input": input, "int": int, "isinstance": isinstance,
    "issubclass": issubclass, "iter": iter, "len": len, "list": list,
    "locals": locals, "map": map, "max": max, "min": min, "next": next,
    "object": object, "oct": oct, "open": open, "ord": ord, "pow": pow,
    "print": print, "range": range, "repr": repr, "reversed": reversed,
    "round": round, "set": set, "setattr": setattr, "slice": slice,
    "sorted": sorted, "str": str, "sum": sum, "super": super,
    "tuple": tuple, "type": type, "vars": vars, "zip": zip,
    "__builtins__": builtins.__dict__,
}
```

But `open` is overridden to only allow file operations within the workspace. And `exec` is removed from builtins.

Tool functions are injected into the skill code's globals:

```python
def _build_sandbox_globals(
    workspace: Path,
    tool_executor: Callable[[str, dict], str],
    skill_def: SkillDefinition,
) -> dict:
    """Build the globals dict for skill code execution."""
    sandbox = dict(SAFE_BUILTINS)

    # Inject workspace
    sandbox["_workspace"] = workspace

    # Inject tool executor (the agent's tool dispatch)
    sandbox["_tool"] = tool_executor

    # Inject safety guard
    from my_code_agent.safety import SafetyGuard
    sandbox["_safety"] = SafetyGuard(workspace)

    # Inject skill context
    sandbox["_skill"] = {
        "name": skill_def.name,
        "version": skill_def.version,
        "inputs": {},   # Will be populated from user input
    }

    # Inject helper functions
    sandbox["_read_file"] = lambda path: _safe_read(workspace, path)
    sandbox["_write_file"] = lambda path, content: _safe_write(workspace, path, content)
    sandbox["_search_replace"] = lambda path, old, new: _safe_search_replace(workspace, path, old, new)
    sandbox["_execute"] = lambda cmd: _safe_execute(workspace, cmd)
    sandbox["_list_dir"] = lambda path: _safe_listdir(workspace, path)
    sandbox["_print"] = lambda *args, **kwargs: _capture_print(*args, **kwargs)

    return sandbox
```

### 6.2 Execution Flow

```python
def execute_skill(
    skill: SkillDefinition,
    tool_executor: Callable[[str, dict], str],
    inputs: dict[str, Any],
    workspace: Path,
) -> SkillResult:
    """Execute a skill's code block with sandboxed globals.

    1. Validate type signature inputs.
    2. Check structure requirements.
    3. Execute code block in sandbox.
    4. Validate output against type signature.
    5. Run eval cases.
    6. Return structured result.
    """
```

Step-by-step:

```python
def execute_skill(
    skill: SkillDefinition,
    tool_executor: Callable[[str, dict], str],
    inputs: dict[str, Any],
    workspace: Path,
) -> SkillResult:
    # 1. Type validation
    type_check = skill.type_signature.validate_inputs(inputs)
    if not type_check.pass:
        return SkillResult(
            success=False,
            output={},
            error=f"Input validation failed: {type_check.errors}",
        )

    # 2. Structure check
    for req in skill.structure_requirements:
        check = req.check(workspace)
        if not check.passed:
            if not req.optional:
                return SkillResult(
                    success=False,
                    output={},
                    error=f"Structure requirement not met: {check.message}",
                )

    # 3. Execute code block
    sandbox = _build_sandbox_globals(workspace, tool_executor, skill)
    stdout_capture = _StdoutCapture()
    sandbox["_print"] = stdout_capture.capture_print

    try:
        exec_globals: dict = {}
        exec(compile(skill.code_block, "<skill>", "exec"), sandbox, exec_globals)
        result = exec_globals.get("_result", {})
    except Exception as e:
        return SkillResult(success=False, output={}, error=str(e))

    # 4. Output validation
    output_errors = []
    for field, expected_type in skill.type_signature.outputs.items():
        if field in result:
            if not _coerce_type(result[field], expected_type):
                output_errors.append(f"Output field '{field}' expected {expected_type}, got {type(result[field]).__name__}")
    if output_errors:
        return SkillResult(success=False, output=result, error="Output validation failed: " + "; ".join(output_errors))

    # 5. Run eval cases
    eval_results = []
    if skill.eval_cases:
        for case in skill.eval_cases:
            passed = case.run_assertions(
                SkillResult(success=True, output=result, stdout=stdout_capture.getvalue()),
                workspace,
            )
            eval_results.append(EvalResult(name=case.name, passed=passed))
        pass_rate = sum(1 for r in eval_results if r.passed) / len(eval_results) if eval_results else 0.0
    else:
        pass_rate = 1.0  # No eval cases = assume success

    return SkillResult(
        success=True,
        output=result,
        stdout=stdout_capture.getvalue(),
        eval_pass_rate=pass_rate,
        eval_results=eval_results,
    )
```

### 6.3 Output Coercion

```python
def _coerce_type(value: Any, target_type: str) -> bool:
    """Check if value can be coerced to the target type string."""
    if target_type == "str":
        return isinstance(value, (str, type(None)))
    if target_type == "bool":
        return isinstance(value, bool)
    if target_type == "int":
        return isinstance(value, (int, type(None)))
    if target_type == "float":
        return isinstance(value, (float, int, type(None)))
    if target_type in ("list[str]", "list"):
        return isinstance(value, (list, type(None)))
    if target_type in ("dict[str, Any]", "dict"):
        return isinstance(value, (dict, type(None)))
    return True  # Unknown type: allow through
```

## 7. Registry (`skills/registry.py`)

### 7.1 `SkillRegistry` Class

```python
class SkillRegistry:
    """Central registry for executable skills with hot reload support."""

    def __init__(self, skills_dir: Path, workspace: Path) -> None:
        self._skills_dir = skills_dir
        self._workspace = workspace
        self._skills: dict[str, SkillDefinition] = {}
        self._file_mtimes: dict[Path, float] = {}
        self._old_skills: list = []  # Legacy skills.json entries
        self._old_skills_path: Path | None = None

        self._load_all()

    def _load_all(self) -> None:
        """Load skills from .skill.md files and legacy JSON."""
        self._load_directory_skills()
        self._load_legacy_skills()

    def _load_directory_skills(self) -> None:
        """Scan skills_dir for .skill.md files and parse each."""
        if not self._skills_dir.exists():
            return
        for md_file in sorted(self._skills_dir.glob("*.skill.md")):
            try:
                skill = parse_skill_file(md_file)
                validation = validate_skill(skill, self._workspace)
                if validation.pass_:
                    self._skills[skill.name] = skill
                    self._file_mtimes[md_file] = md_file.stat().st_mtime
                else:
                    # Log but don't add -- invalid skills are silently skipped
                    pass
            except Exception:
                pass  # Corrupt skill file: skip

    def _load_legacy_skills(self) -> None:
        """Load old skills.json entries as placeholder SkillDefinitions."""
        from ..mcp.skill_matcher import load_skills as load_old_skills
        from .parser import parse_old_skill_json

        old_path = Path(os.environ.get("MCP_SKILLS_PATH", ".mcp/skills.json"))
        if old_path.exists():
            self._old_skills_path = old_path
            for skill_dict in load_old_skills(old_path):
                try:
                    skill_def = parse_old_skill_json(skill_dict, old_path)
                    self._old_skills.append(skill_def)
                except Exception:
                    pass

    # ---- Public API ----

    def get_skill(self, name: str) -> SkillDefinition | None:
        """Get a skill by name. Priority: .skill.md > legacy JSON."""
        if name in self._skills:
            return self._skills[name]
        for s in self._old_skills:
            if s.name == name:
                return s
        return None

    def list_skills(self) -> list[SkillDefinition]:
        """Return all registered skills."""
        return list(self._skills.values())

    def list_skill_names(self) -> list[str]:
        """Return names of all registered skills."""
        return list(self._skills.keys())

    def reload(self) -> int:
        """Reload all skills from disk. Return count of changed skills."""
        self._load_all()
        return len(self._skills)

    def has_changed(self) -> bool:
        """Check if any skill file has been modified since last load."""
        for md_file, old_mtime in list(self._file_mtimes.items()):
            if not md_file.exists():
                return True
            new_mtime = md_file.stat().st_mtime
            if new_mtime > old_mtime:
                return True
        return False

    def watch_loop(self, callback: Callable[[], None], interval: float = 1.0) -> None:
        """Blocking loop that calls callback when skill files change.
        Used by the MCP server for hot reload."""
        import time
        while True:
            time.sleep(interval)
            if self.has_changed():
                self.reload()
                callback()
```

### 7.2 Hot Reload Mechanism

The `watch_loop` runs in a background thread on the MCP server. On detection of a file change:
1. Re-parse the changed `.skill.md` file.
2. Re-validate it.
3. Replace or remove it from the registry dict.
4. Signal the callback (MCP server updates its internal skill list).

## 8. Skills MCP Server (`mcp/skills_server.py`)

### 8.1 Server Definition

```python
from mcp.server.fastmcp import FastMCP
from .skills.registry import SkillRegistry

mcp = FastMCP(name="skills", version="1.0.0")

# Initialize registry (loaded once at server startup)
_skills_registry: SkillRegistry | None = None

def _get_registry() -> SkillRegistry:
    global _skills_registry
    if _skills_registry is None:
        skills_dir = Path(os.environ.get("SKILLS_DIR", ".agent/skills"))
        workspace = Path(os.environ.get("WORKSPACE", ".")).resolve()
        _skills_registry = SkillRegistry(skills_dir, workspace)
    return _skills_registry

# ---- MCP Tools ----

@mcp.tool()
def execute_skill(name: str, inputs: dict[str, Any] = {}) -> str:
    """Execute a registered skill by name with the given inputs."""
    reg = _get_registry()
    skill = reg.get_skill(name)
    if skill is None:
        return f"Skill not found: {name}"
    result = execute_skill_fn(skill, inputs, reg._workspace)
    return _format_result(result)

@mcp.tool()
def validate_skill(name: str) -> str:
    """Validate a registered skill's definition."""
    reg = _get_registry()
    skill = reg.get_skill(name)
    if skill is None:
        return f"Skill not found: {name}"
    result = validate_skill_fn(skill, reg._workspace)
    return f"Validation {'passed' if result.pass_ else 'failed'}:\n" + "\n".join(result.errors) if result.errors else "All checks passed."

@mcp.tool()
def list_skills() -> str:
    """List all registered skills with their levels and descriptions."""
    reg = _get_registry()
    skills = reg.list_skills()
    if not skills:
        return "No skills registered."
    lines = [f"- {s.name} (v{s.version}, {s.level.value}): {s.description}" for s in skills]
    return "\n".join(lines)

@mcp.tool()
def run_evals(name: str) -> str:
    """Run all eval cases for a skill against the current workspace."""
    reg = _get_registry()
    skill = reg.get_skill(name)
    if skill is None:
        return f"Skill not found: {name}"
    if not skill.eval_cases:
        return f"No eval cases defined for skill: {name}"
    # Execute each eval case by running the skill with the case's inputs
    results = []
    for case in skill.eval_cases:
        skill_result = execute_skill_fn(skill, case.inputs, reg._workspace)
        results.append(f"  {case.name}: {'PASS' if skill_result.success else 'FAIL'}")
    return "\n".join(results)
```

### 8.2 Hot Reload Integration

```python
import threading

def _start_hot_reload(registry: SkillRegistry) -> None:
    """Start a background thread for skill file watching."""
    def _watcher():
        registry.watch_loop(interval=2.0)
    t = threading.Thread(target=_watcher, daemon=True)
    t.start()
```

### 8.3 Entry Point

```python
def main() -> None:
    mcp.run()

if __name__ == "__main__":
    main()
```

The server is invoked via the MCP config as:
```json
"skills": {
    "command": "python",
    "args": ["-m", "my_code_agent.mcp.skills_server"]
}
```

## 9. Backward Compatibility

### 9.1 Migration Path

The old `skills.json` format is loaded as a fallback. When a skill exists in BOTH formats (`.skill.md` and `skills.json`), the `.skill.md` version takes priority.

### 9.2 Updated `mcp/__init__.py`

```python
from .skills.parser import parse_skill_file, parse_old_skill_json
from .skills.validator import validate_skill
from .skills.executor import execute_skill as execute_skill_fn
from .skills.registry import SkillRegistry

# Keep old exports for backward compatibility
from .skill_matcher import match_skill, load_skills
from .skill_executor import execute_skill as legacy_execute_skill
```

### 9.3 Updated `agent.py` Integration

```python
# In CodingAgent.__init__:
if mcp_bridge is not None:
    from .skills.registry import SkillRegistry
    skills_path = Path(config.mcp_skills_path).parent / "skills"
    self._skill_registry = SkillRegistry(
        skills_path, config.workspace_path
    )
    # Use registry for skill lookup (supports both .skill.md and legacy JSON)
    self._skill_names = self._skill_registry.list_skill_names()
```

When a skill match is found, the agent:
1. Gets the `SkillDefinition` from the registry.
2. If `code_block` is empty (legacy skill), falls back to the old `execute_skill` behavior (linear step execution).
3. If `code_block` is non-empty, uses the new `execute_skill_fn` with sandboxed execution.

## 10. Implementation Sequence

### Phase 1: Data Model + Parser (2-3 hours)

1. Create `src/my_code_agent/skills/__init__.py`.
2. Write `src/my_code_agent/skills/models.py` -- all dataclasses.
3. Write `src/my_code_agent/skills/parser.py` -- YAML + code block extraction.
4. Write tests: `tests/test_skills_parser.py`.

### Phase 2: Validator (1-2 hours)

5. Write `src/my_code_agent/skills/validator.py` -- four validation passes.
6. Write tests: `tests/test_skills_validator.py`.

### Phase 3: Executor (3-4 hours)

7. Write `src/my_code_agent/skills/executor.py` -- sandboxed execution + output validation + eval runner.
8. Write tests: `tests/test_skills_executor.py`.
9. Create a sample `.agent/skills/refactor-function.skill.md`.

### Phase 4: Registry (1-2 hours)

10. Write `src/my_code_agent/skills/registry.py` -- directory loading + hot reload.
11. Write tests: `tests/test_skills_registry.py`.

### Phase 5: MCP Server (2-3 hours)

12. Write `src/my_code_agent/mcp/skills_server.py`.
13. Write tests: `tests/test_skills_server.py` (test tool registration, not the server itself).

### Phase 6: Integration (1-2 hours)

14. Update `src/my_code_agent/mcp/__init__.py` to re-export new symbols.
15. Update `src/my_code_agent/agent.py` to use the SkillRegistry.
16. Update `src/my_code_agent/config.py` to add `skills_dir` config field.

## 11. Sample Skill File

```markdown
---
name: refactor-function
version: "1.0"
level: L2
description: Safely refactor a specified function while preserving tests and imports.
type_signature:
  inputs:
    file_path: str
    function_name: str
    goal: str
  outputs:
    success: bool
    changes: list[str]
structure_requirements:
  - requires: "tests/"
    purpose: "Validate refactoring preserves existing tests"
    optional: true
safety_constraints:
  - no-delete-public-api
  - preserve-signature
eval_cases:
  - name: "rename simple function"
    inputs:
      file_path: "src/example.py"
      function_name: "greet"
      goal: "rename to hello"
    assertions:
      - "file contains 'def hello'"
      - "file does not contain 'def greet'"
  - name: "refactor with no changes"
    inputs:
      file_path: "src/example.py"
      function_name: "already_correct"
      goal: "no-op rename"
    assertions:
      - "no broken imports"
---
```python
import ast
from pathlib import Path

def _find_function_tree(source_code: str, func_name: str) -> ast.FunctionDef | None:
    tree = ast.parse(source_code)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            return node
    return None

def _check_imports_broken(file_path: str, old_name: str) -> bool:
    """Check if any imports reference old_name."""
    workspace = _workspace
    try:
        content = Path(file_path).read_text(encoding="utf8")
        return old_name + "(" in content
    except OSError:
        return False

# --- Main logic ---
workspace = _workspace
fp = Path(_skill["inputs"]["file_path"])
fn_name = _skill["inputs"]["function_name"]
goal = _skill["inputs"]["goal"]

# Read current content
content = fp.read_text(encoding="utf-8")

# Find function and replace name
tree = _find_function_tree(content, fn_name)
if tree is None:
    _result = {"success": False, "changes": [f"Function '{fn_name}' not found"]}
else:
    new_content = content.replace(f"def {fn_name}", f"def {goal}", 1)
    # Update imports
    new_content = new_content.replace(f"import {fn_name}", f"import {goal}", 1)
    fp.write_text(new_content, encoding="utf-8")
    _result = {"success": True, "changes": [f"Renamed '{fn_name}' to '{goal}'"]}
```
```

## 12. Test Structure

### `tests/test_skills_parser.py`

```python
# Fixtures:
#   - sample_skill_md: A temporary .skill.md file with valid YAML frontmatter + Python code block
#   - skill_with_no_code: Frontmatter only, no Python code block
#   - skill_with_multiple_code_blocks: Only the first ```python block is extracted
#   - old_format_skill: A dict matching the old skills.json structure

# Tests:
#   - test_parse_valid_skill: Checks all fields are correctly populated
#   - test_parse_missing_version_defaults: version defaults to "0.0.0"
#   - test_parse_missing_type_signature: type_signature defaults to empty dicts
#   - test_parse_missing_structure_requirements: structure_requirements defaults to []
#   - test_parse_missing_eval_cases: eval_cases defaults to []
#   - test_parse_no_code_block: code_block is empty string
#   - test_parse_multiple_code_blocks: only first ```python block is extracted
#   - test_parse_old_format_json: parse_old_skill_json converts correctly
#   - test_parse_invalid_yaml: raises ValueError
#   - test_parse_non_skill_md_file: works on any .md file
```

### `tests/test_skills_validator.py`

```python
# Fixtures:
#   - valid_skill: A SkillDefinition with valid type signature, empty structure reqs
#   - skill_with_structure_req: SkillDefinition requiring "tests/" directory
#   - skill_with_invalid_type: type_signature with "undefined_type_name"

# Tests:
#   - test_validate_all_pass: All checks pass
#   - test_validate_invalid_type_annotation: Fails on bad type annotation
#   - test_validate_missing_structure: Fails when required dir is absent
#   - test_validate_optional_structure_passes: Optional requirement missing is OK
#   - test_validate_unknown_safety_constraint: Warns but doesn't fail
#   - test_validate_syntax_error_in_code: Fails on invalid Python
#   - test_validate_disallowed_operation: Fails on os.system() in code block
#   - test_validate_empty_code_block: Passes (no code to validate)
```

### `tests/test_skills_executor.py`

```python
# Fixtures:
#   - mock_tool_executor: A MagicMock that returns controlled strings
#   - skill_with_code: A SkillDefinition with actual Python code
#   - workspace_with_tests: A tmp_path with src/ and tests/ dirs

# Tests:
#   - test_execute_success: Returns SkillResult with success=True
#   - test_execute_code_error: Returns SkillResult with error=exception message
#   - test_execute_output_validation_fail: Fails when output type doesn't match
#   - test_execute_input_validation_fail: Fails when inputs missing required field
#   - test_execute_structure_requirement_fail: Fails when required dir missing
#   - test_execute_eval_cases_pass: All eval cases pass, eval_pass_rate=1.0
#   - test_execute_eval_cases_fail: Some eval cases fail, eval_pass_rate < 1.0
#   - test_execute_no_eval_cases: eval_pass_rate defaults to 1.0
#   - test_execute_sandbox_isolation: Skill cannot access globals outside sandbox
```

### `tests/test_skills_registry.py`

```python
# Tests:
#   - test_load_skills_from_directory: Parses .skill.md files from a directory
#   - test_load_legacy_json: Loads old skills.json entries
#   - test_get_skill_by_name: Returns correct skill
#   - test_get_skill_not_found: Returns None
#   - test_list_skills: Returns all loaded skills
#   - test_has_changed_detects_modification: Returns True when file mtime changes
#   - test_reload: Re-parses all skill files
#   - test_priority_new_over_legacy: .skill.md takes priority over skills.json
#   - test_invalid_skill_skipped: Corrupt .skill.md is skipped, not crash
```

### `tests/test_skills_server.py`

```python
# Tests:
#   - test_list_skills_tool: Returns formatted skill list
#   - test_execute_skill_tool_not_found: Returns error for unknown skill
#   - test_validate_skill_tool_not_found: Returns error for unknown skill
#   - test_run_evals_no_eval_cases: Returns "No eval cases" message
#   - test_hot_reload_triggers_callback: watch_loop detects changes
```

## 13. Key Design Decisions

1. **Sandboxing approach**: `exec()` with restricted globals rather than subprocess. Simpler, faster, no IPC overhead. Safety is ensured by: (a) AST pre-validation to ban dangerous calls, (b) restricted builtins, (c) workspace-scoped file operations.

2. **YAML frontmatter**: Chosen over JSON for readability and comment support. `yaml.safe_load` is already a dependency.

3. **Code block extraction**: First ` ```python ` block is the skill code. Allows markdown documentation before and after the code.

4. **Backward compatibility**: `SkillDefinition` is a superset of the old skills.json format. `parse_old_skill_json` creates a SkillDefinition with empty `code_block`. The executor handles empty code blocks by falling back to the old step-based execution.

5. **Hot reload**: File mtime polling (simple, no inotify/fsevents dependency). Runs in daemon thread. The MCP server's tool handlers always read from the current registry dict snapshot.

6. **Eval assertions**: Natural language strings evaluated against the output/workspace, not strict schema matching. This allows skills to express quality checks without a formal assertion DSL.

7. **Type annotations in YAML**: Plain strings like `"str"`, `"list[str]"` rather than Python type objects. Keeps YAML portable and avoids import complexity. Coercion is checked at execution time.

## 14. Edge Cases and Error Handling

| Scenario | Handling |
|---|---|
| Missing `.agent/skills/` directory | Registry loads from legacy JSON only, prints warning |
| Corrupt `.skill.md` (bad YAML) | Skipped, logged as warning |
| Skill code raises during exec | Caught, returned as `SkillResult.error` |
| Skill code accesses outside workspace | `open` override raises `SafetyError` |
| Eval case references nonexistent file | Assertion evaluated as `False`, not a crash |
| Concurrent MCP calls | `SkillRegistry` dict is not thread-safe; each MCP tool call takes a snapshot via `list()` |
| Skill code has infinite loop | Not handled in Phase 2 (would need subprocess isolation). Documented as known limitation. |
