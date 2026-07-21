#!/usr/bin/env python3
"""
Validation script for Solar Irrigation integration.
This validates that all required files and structures are in place.
"""

import os
import json
import sys

def validate_hacs_json():
    """Validate hacs.json structure."""
    hacs_path = "/home/niklas/Development/Irrigation/hacs.json"
    
    if not os.path.exists(hacs_path):
        print("❌ hacs.json file missing")
        return False
    
    try:
        with open(hacs_path, 'r') as f:
            data = json.load(f)
        
        required_fields = ["name", "description", "version", "config_flow"]
        for field in required_fields:
            if field not in data:
                print(f"❌ Missing required field: {field}")
                return False
        
        print("✅ hacs.json validation passed")
        return True
    except Exception as e:
        print(f"❌ Error validating hacs.json: {e}")
        return False

def validate_integration_structure():
    """Validate integration structure."""
    # Check required files exist
    required_files = [
        "custom_components/solar_irrigation/__init__.py",
        "custom_components/solar_irrigation/coordinator.py", 
        "custom_components/solar_irrigation/sensor.py",
        "custom_components/solar_irrigation/manifest.json",
        "custom_components/solar_irrigation/progress.py"
    ]
    
    for file in required_files:
        path = f"/home/niklas/Development/Irrigation/{file}"
        if not os.path.exists(path):
            print(f"❌ Missing required file: {file}")
            return False
        print(f"✅ {file} exists")
    
    print("✅ Integration structure validation passed")
    return True

def validate_progress_system():
    """Validate progress reporting system."""
    # Check that progress.py exists and has the right structure
    progress_path = "/home/niklas/Development/Irrigation/custom_components/solar_irrigation/progress.py"
    
    if not os.path.exists(progress_path):
        print("❌ progress.py file missing")
        return False
    
    # Check that it contains the right elements
    with open(progress_path, 'r') as f:
        content = f.read()
    
    required_elements = ["SolarIrrigationProgress", "report_progress", "update_integration_status"]
    for element in required_elements:
        if element not in content:
            print(f"❌ Missing {element} from progress.py")
            return False
    
    print("✅ Progress system validation passed")
    return True

def main():
    """Main validation function."""
    print("🔍 Validating Solar Irrigation Integration (Phase 4)...")
    print("=" * 50)
    
    success = True
    success &= validate_hacs_json()
    print()
    success &= validate_integration_structure()
    print()
    success &= validate_progress_system()
    
    print()
    if success:
        print("🎉 ALL VALIDATIONS PASSED - Phase 4 complete!")
        return 0
    else:
        print("❌ SOME VALIDATIONS FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(main())