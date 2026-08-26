#!/usr/bin/env python3
"""
Pre-commit Hook Validation Script

Enforces file placement rules defined in WORKSPACE_RULES.md
Prevents rogue files from being committed to the repository.

Usage:
  python tools/pre-commit-validate.py

This script is automatically called by pre-commit hooks before commits.
"""

import os
import sys
import re
from pathlib import Path
from typing import List, Tuple

# Configuration
ROOT_ALLOWED_FILES = {
    ".env",
    ".env.example",
    ".flake8",
    ".gitignore",
    ".pre-commit-config.yaml",
    "AGENTS.md",
    "langchain-workspace.code-workspace",
    "Makefile",
    "pyproject.toml",
    "pytest.ini",
    "README.md",
    "requirements.txt",
    "requirements-dev.txt",
    "WORKSPACE_RULES.md",
    "CONTRIBUTING.md",
    "PROFESSIONAL_RESTRUCTURING_PLAN.md",
}

# Forbidden patterns at root
FORBIDDEN_PATTERNS = [
    r"\.py$",  # Python files
    r"\.png$",  # Images
    r"\.jpg$",
    r"\.jpeg$",
    r"\.gif$",
    r"\.json$",  # JSON (except config)
    r"\.log$",  # Logs
    r"\.csv$",  # CSV
]

# Allowed directories for specific file types
ALLOWED_LOCATIONS = {
    "python": ["src/", "services/", "tests/", "tools/"],
    "images": ["docs/images/", "architecture/diagrams/"],
    "json": ["tests/fixtures/", "data/"],
    "scripts": ["tools/", "scripts/", "infrastructure/"],
}

class PreCommitValidator:
    """Validates file placement according to WORKSPACE_RULES.md"""
    
    def __init__(self):
        self.repo_root = self._find_repo_root()
        self.errors = []
    
    def _find_repo_root(self) -> Path:
        """Find git repository root."""
        current = Path.cwd()
        while current != current.parent:
            if (current / ".git").exists():
                return current
            current = current.parent
        return Path.cwd()
    
    def validate_root_files(self) -> bool:
        """Check for forbidden files at root."""
        violations = []
        
        for file_path in self.repo_root.glob("*"):
            if file_path.is_dir():
                continue
            
            filename = file_path.name
            
            # Check if file is allowed
            if filename not in ROOT_ALLOWED_FILES:
                # Check if it matches forbidden pattern
                for pattern in FORBIDDEN_PATTERNS:
                    if re.search(pattern, filename):
                        violations.append(
                            f"❌ Forbidden file at root: {filename}\n"
                            f"   → See WORKSPACE_RULES.md for proper location"
                        )
                        break
        
        if violations:
            self.errors.extend(violations)
            return False
        return True
    
    def validate_python_files(self) -> bool:
        """Validate Python files are in correct locations."""
        violations = []
        
        for py_file in self.repo_root.glob("*.py"):
            if py_file.name not in ["setup.py", "conftest.py"]:
                violations.append(
                    f"❌ Python file at root: {py_file.name}\n"
                    f"   → Move to: src/ or services/"
                )
        
        if violations:
            self.errors.extend(violations)
            return False
        return True
    
    def validate_module_structure(self) -> bool:
        """Validate module structure has required files."""
        violations = []
        
        # Check src/ subdirectories have __init__.py
        for module_dir in (self.repo_root / "src").glob("*/"):
            if module_dir.is_dir() and not (module_dir / "__init__.py").exists():
                violations.append(
                    f"❌ Missing __init__.py in module: {module_dir.name}\n"
                    f"   → Create: src/{module_dir.name}/__init__.py"
                )
        
        # Check services have required structure
        for service_dir in (self.repo_root / "services").glob("*/"):
            if not service_dir.is_dir():
                continue
            
            required_files = [
                "app/__init__.py",
                "core/__init__.py",
                "models/__init__.py",
                "Dockerfile",
                "requirements.txt",
            ]
            
            for req_file in required_files:
                if not (service_dir / req_file).exists():
                    violations.append(
                        f"❌ Missing required file in service: {req_file}\n"
                        f"   → Create: services/{service_dir.name}/{req_file}"
                    )
        
        if violations:
            self.errors.extend(violations)
            return False
        return True
    
    def validate_test_files(self) -> bool:
        """Validate test files are in tests/ directory."""
        violations = []
        
        for test_file in self.repo_root.glob("test_*.py"):
            violations.append(
                f"❌ Test file at root: {test_file.name}\n"
                f"   → Move to: tests/unit/ or tests/integration/"
            )
        
        if violations:
            self.errors.extend(violations)
            return False
        return True
    
    def validate_image_files(self) -> bool:
        """Validate image files are in docs/images/."""
        violations = []
        
        for img_file in self.repo_root.glob("*.png"):
            violations.append(
                f"❌ Image file at root: {img_file.name}\n"
                f"   → Move to: docs/images/"
            )
        
        for img_file in self.repo_root.glob("*.jpg"):
            violations.append(
                f"❌ Image file at root: {img_file.name}\n"
                f"   → Move to: docs/images/"
            )
        
        if violations:
            self.errors.extend(violations)
            return False
        return True
    
    def run_validation(self) -> bool:
        """Run all validations."""
        all_valid = True
        
        all_valid &= self.validate_root_files()
        all_valid &= self.validate_python_files()
        all_valid &= self.validate_module_structure()
        all_valid &= self.validate_test_files()
        all_valid &= self.validate_image_files()
        
        return all_valid
    
    def print_results(self):
        """Print validation results."""
        if not self.errors:
            print("✅ All files pass WORKSPACE_RULES.md validation!")
            return True
        
        print("\n" + "=" * 70)
        print("❌ WORKSPACE_RULES.md VIOLATIONS DETECTED")
        print("=" * 70 + "\n")
        
        for error in self.errors:
            print(error)
            print()
        
        print("\n" + "=" * 70)
        print("See WORKSPACE_RULES.md for detailed file placement rules")
        print("=" * 70 + "\n")
        
        return False


def main():
    """Main entry point."""
    validator = PreCommitValidator()
    
    print("🔍 Validating workspace structure...")
    print()
    
    if validator.run_validation():
        validator.print_results()
        return 0
    else:
        validator.print_results()
        return 1


if __name__ == "__main__":
    sys.exit(main())
