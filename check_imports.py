import sys
import subprocess
import re

def get_packages_from_requirements(filename):
    packages = []
    with open(filename, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            # Remove version specifiers
            # Split on any of: ==, >=, <=, >, <, ~=, !=
            parts = re.split(r'==|>=|<=|>|<|~=|!=', line, 1)
            pkg = parts[0].strip()
            # Remove any extra whitespace or comments
            pkg = pkg.split('#')[0].strip()
            if pkg:
                packages.append(pkg)
    return packages

def check_import(package):
    try:
        __import__(package)
        return True, None
    except ImportError as e:
        return False, str(e)

def main():
    req_file = 'requirements.txt'
    try:
        packages = get_packages_from_requirements(req_file)
    except FileNotFoundError:
        print(f"ERROR: {req_file} not found.")
        sys.exit(1)
    
    missing = []
    for pkg in packages:
        success, error = check_import(pkg)
        if not success:
            missing.append((pkg, error))
    
    if missing:
        print("MISSING PACKAGES:")
        for pkg, error in missing:
            print(f"  {pkg}: {error}")
        sys.exit(1)
    else:
        print("All required packages are installed.")
        sys.exit(0)

if __name__ == '__main__':
    main()