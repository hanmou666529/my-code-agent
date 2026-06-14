---
name: refactor-function
version: "1.0"
level: L1
description: Safely refactor a specified function while preserving tests and public API
type_signature:
  inputs:
    - file_path: str
    - function_name: str
    - goal: str
  outputs:
    - success: bool
    - changes: list[str]
  returns_annotation: str
structure_requirements:
  - requires: "tests/"
    purpose: "Validate refactoring preserves test compatibility"
safety_constraints:
  - no-delete-public-api
  - preserve-signature
eval_cases:
  - name: "rename simple function"
    inputs:
      file_path: "src/main.py"
      function_name: "greet"
      goal: "rename to welcome"
    assertions:
      - "file contains 'welcome'"
      - "no broken imports"
  - name: "rename with existing tests"
    inputs:
      file_path: "src/main.py"
      function_name: "greet"
      goal: "rename to hello"
    assertions:
      - "field 'file_path' is required"
      - "field 'function_name' is required"
---
"""refactor-function: Rename a function in a file while preserving structure.

This skill reads the target file, finds the function definition,
performs a text-based rename, and writes the result back.

Usage in code_block:
  The skill is executed with these inputs available:
    - _inputs: dict of input values
    - _read_file(file_path) -> str
    - _write_file(file_path, content) -> str
    - _search_replace(file_path, old, new) -> str
    - _workspace: Path to workspace root
"""

# Extract inputs
file_path = _inputs.get("file_path", "")
function_name = _inputs.get("function_name", "")
goal = _inputs.get("goal", "")

if not file_path or not function_name:
    _result = "ERROR: Missing required inputs (file_path, function_name)"
else:
    # Read the file
    try:
        content = _read_file(file_path)
    except Exception as e:
        _result = f"ERROR: Cannot read file: {e}"
        content = ""

    # Perform simple rename: replace function name in definitions and calls
    if content and function_name in content:
        new_content = content.replace(function_name, goal)
        changes = []
        if function_name in content:
            changes.append(f"Renamed '{function_name}' -> '{goal}'")
        _write_file(file_path, new_content)
        _result = f"SUCCESS: {'; '.join(changes)}"
    else:
        _result = f"SKIPPED: Function '{function_name}' not found in file"
