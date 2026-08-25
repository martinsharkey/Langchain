#!/usr/bin/env python3
"""
V2.0 Architecture Validation Script

Validates that all services are properly structured and ready for deployment.
"""

import os
import sys
from pathlib import Path
import json

# Handle encoding on Windows
if sys.platform == "win32":
    os.environ["PYTHONIOENCODING"] = "utf-8"
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def check_directory_structure():
    """Check that all required directories exist."""
    print("🔍 Checking directory structure...")
    
    required_dirs = [
        "services/discovery-service",
        "services/discovery-service/app",
        "services/discovery-service/core",
        "services/discovery-service/tests",
        "services/optimization-service",
        "services/optimization-service/app",
        "services/optimization-service/core",
        "services/optimization-service/tests",
        "services/validation-service",
        "services/validation-service/app",
        "services/validation-service/core",
        "services/validation-service/tests",
        "shared",
        "shared/models",
    ]
    
    missing = []
    for dir_path in required_dirs:
        if not os.path.isdir(dir_path):
            missing.append(dir_path)
    
    if missing:
        print(f"  ❌ Missing directories: {missing}")
        return False
    
    print(f"  ✅ All {len(required_dirs)} required directories exist")
    return True


def check_required_files():
    """Check that all required files exist."""
    print("🔍 Checking required files...")
    
    required_files = {
        "services/discovery-service": [
            "Dockerfile",
            "requirements.txt",
            "app/main.py",
            "core/discovery_engine.py",
            "tests/test_discovery_engine.py"
        ],
        "services/optimization-service": [
            "Dockerfile",
            "requirements.txt",
            "app/main.py",
            "core/optimization_engine.py",
        ],
        "services/validation-service": [
            "Dockerfile",
            "requirements.txt",
            "app/main.py",
            "core/validation_engine.py",
        ],
        ".": [
            "docker-compose.yml",
            "nginx.conf",
            ".env.example",
            "README.md",
        ]
    }
    
    missing = []
    for base_dir, files in required_files.items():
        for file_name in files:
            file_path = os.path.join(base_dir, file_name) if base_dir != "." else file_name
            if not os.path.isfile(file_path):
                missing.append(file_path)
    
    if missing:
        print(f"  ❌ Missing files ({len(missing)}):")
        for f in missing:
            print(f"    - {f}")
        return False
    
    print(f"  ✅ All required files exist")
    return True


def check_docker_compose_syntax():
    """Check docker-compose.yml syntax."""
    print("🔍 Checking docker-compose.yml syntax...")
    
    try:
        import yaml
        with open("docker-compose.yml", "r") as f:
            yaml.safe_load(f)
        print("  ✅ docker-compose.yml is valid YAML")
        return True
    except ImportError:
        print("  ⚠️  PyYAML not installed, skipping syntax check")
        return True
    except Exception as e:
        print(f"  ❌ Invalid docker-compose.yml: {e}")
        return False


def check_dockerfile_structure():
    """Check that all Dockerfiles have required elements."""
    print("🔍 Checking Dockerfile structure...")
    
    required_elements = [
        "FROM",
        "WORKDIR",
        "COPY",
        "RUN pip install",
        "EXPOSE",
        "CMD"
    ]
    
    dockerfiles = [
        "services/discovery-service/Dockerfile",
        "services/optimization-service/Dockerfile",
        "services/validation-service/Dockerfile"
    ]
    
    all_valid = True
    for dockerfile_path in dockerfiles:
        with open(dockerfile_path, "r") as f:
            content = f.read()
        
        missing_elements = []
        for element in required_elements:
            if element not in content:
                missing_elements.append(element)
        
        if missing_elements:
            print(f"  ❌ {dockerfile_path} missing: {missing_elements}")
            all_valid = False
        else:
            print(f"  ✅ {dockerfile_path} valid")
    
    return all_valid


def check_requirements_files():
    """Check that all requirements.txt files exist and have dependencies."""
    print("🔍 Checking requirements.txt files...")
    
    requirements_paths = [
        "services/discovery-service/requirements.txt",
        "services/optimization-service/requirements.txt",
        "services/validation-service/requirements.txt"
    ]
    
    all_valid = True
    for req_path in requirements_paths:
        if not os.path.isfile(req_path):
            print(f"  ❌ Missing {req_path}")
            all_valid = False
            continue
        
        with open(req_path, "r") as f:
            content = f.read().strip()
        
        if not content:
            print(f"  ❌ {req_path} is empty")
            all_valid = False
        else:
            lines = [l for l in content.split('\n') if l.strip() and not l.startswith('#')]
            print(f"  ✅ {req_path} has {len(lines)} dependencies")
    
    return all_valid


def check_python_syntax():
    """Check Python files for syntax errors."""
    print("🔍 Checking Python file syntax...")
    
    python_files = [
        "services/discovery-service/app/main.py",
        "services/discovery-service/core/discovery_engine.py",
        "services/optimization-service/app/main.py",
        "services/optimization-service/core/optimization_engine.py",
        "services/validation-service/app/main.py",
        "services/validation-service/core/validation_engine.py",
    ]
    
    all_valid = True
    for py_file in python_files:
        try:
            with open(py_file, "r") as f:
                compile(f.read(), py_file, "exec")
            print(f"  ✅ {py_file}")
        except SyntaxError as e:
            print(f"  ❌ {py_file}: {e}")
            all_valid = False
    
    return all_valid


def main():
    """Run all validation checks."""
    print("\n" + "="*60)
    print("  V2.0 Architecture Validation")
    print("="*60 + "\n")
    
    checks = [
        ("Directory Structure", check_directory_structure),
        ("Required Files", check_required_files),
        ("Docker Compose", check_docker_compose_syntax),
        ("Dockerfile Structure", check_dockerfile_structure),
        ("Requirements Files", check_requirements_files),
        ("Python Syntax", check_python_syntax),
    ]
    
    results = []
    for check_name, check_func in checks:
        try:
            result = check_func()
            results.append((check_name, result))
        except Exception as e:
            print(f"  ⚠️  {check_name} check failed: {e}")
            results.append((check_name, False))
        print()
    
    # Summary
    print("="*60)
    print("  Validation Summary")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for check_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {check_name}")
    
    print(f"\n  Total: {passed}/{total} checks passed")
    
    if passed == total:
        print("\n  🎉 Architecture validation SUCCESSFUL!")
        print("  Phase 1 is ready for deployment.\n")
        return 0
    else:
        print(f"\n  ⚠️  {total - passed} check(s) failed. Please fix issues.\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
