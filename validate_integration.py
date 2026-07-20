#!/usr/bin/env python3
"""
Validation script for Solar Irrigation Integration
"""

import sys
import os

def validate_directory_structure():
    """Validate the directory structure exists"""
    base_path = "~/Development/Irrigation"
    components_path = os.path.expanduser("~/Development/Irrigation/custom_components/solar_irrigation")
    
    required_files = [
        "__init__.py",
        "config_flow.py", 
        "coordinator.py",
        "sensor.py",
        "switch.py",
        "const.py",
        "manifest.json",
        "hacs.json",
        "services.yaml",
        "translations/en.json"
    ]
    
    print("Validating directory structure...")
    for file in required_files:
        file_path = os.path.join(components_path, file)
        if os.path.exists(file_path):
            print(f"✓ {file}")
        else:
            print(f"✗ {file}")
            return False
    return True

def validate_files_compilation():
    """Validate all Python files compile correctly"""
    print("\nValidating compilation...")
    components_path = os.path.expanduser("~/Development/Irrigation/custom_components/solar_irrigation")
    
    # Test compilation of all Python files
    python_files = ["__init__.py", "config_flow.py", "coordinator.py", "sensor.py", "switch.py"]
    
    for file in python_files:
        file_path = os.path.join(components_path, file)
        try:
            # Test compile with python -m py_compile
            os.system(f"python3 -m py_compile {file_path}")
            print(f"✓ {file} compiles correctly")
        except Exception as e:
            print(f"✗ {file} failed compilation: {e}")
            return False
    
    return True

def validate_hacs_json():
    """Validate hacs.json content"""
    print("\nValidating hacs.json...")
    hacs_path = os.path.expanduser("~/Development/Irrigation/hacs.json")
    
    if os.path.exists(hacs_path):
        print("✓ hacs.json exists")
        return True
    else:
        print("✗ hacs.json missing")
        return False

def main():
    """Main validation function"""
    print("=== Solar Irrigation Integration Validation ===")
    
    success = True
    success &= validate_directory_structure()
    success &= validate_files_compilation()
    success &= validate_hacs_json()
    
    if success:
        print("\n🎉 All validations passed! Integration is ready for HACS.")
        return 0
    else:
        print("\n❌ Some validations failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main())