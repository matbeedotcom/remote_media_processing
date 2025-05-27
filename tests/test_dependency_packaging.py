#!/usr/bin/env python3
"""
Test AST-based dependency analysis and code packaging.
This demonstrates the Phase 3 Code & Dependency Packager functionality.
"""

import sys
import tempfile
import zipfile
from pathlib import Path
import io

# Add project root to path
sys.path.insert(0, str(Path.cwd()))

from remotemedia.packaging import DependencyAnalyzer, CodePackager


def create_test_files():
    """Create test files to demonstrate dependency analysis."""
    
    # Create a temporary directory structure
    temp_dir = Path(tempfile.mkdtemp())
    
    # Create main module
    main_file = temp_dir / "main_module.py"
    main_file.write_text("""
# Main module that imports local dependencies
from utils.helper import HelperClass
from data_processor import DataProcessor
import math

class MainProcessor:
    def __init__(self):
        self.helper = HelperClass()
        self.processor = DataProcessor()
    
    def process(self, data):
        processed = self.processor.process_data(data)
        return self.helper.format_result(processed)
""")
    
    # Create utils package
    utils_dir = temp_dir / "utils"
    utils_dir.mkdir()
    
    utils_init = utils_dir / "__init__.py"
    utils_init.write_text("# Utils package")
    
    helper_file = utils_dir / "helper.py"
    helper_file.write_text("""
# Helper module
from .formatter import format_output

class HelperClass:
    def format_result(self, data):
        return format_output(data)
""")
    
    formatter_file = utils_dir / "formatter.py"
    formatter_file.write_text("""
# Formatter module
def format_output(data):
    return f"Formatted: {data}"
""")
    
    # Create data processor module
    data_processor_file = temp_dir / "data_processor.py"
    data_processor_file.write_text("""
# Data processor module
import json

class DataProcessor:
    def process_data(self, data):
        if isinstance(data, str):
            return data.upper()
        return str(data)
""")
    
    return temp_dir, main_file


def test_dependency_analysis():
    """Test AST-based dependency analysis."""
    print("🔍 Testing AST-based Dependency Analysis")
    print("=" * 50)
    
    # Create test files
    temp_dir, main_file = create_test_files()
    
    try:
        # Initialize analyzer
        analyzer = DependencyAnalyzer(project_root=temp_dir)
        
        # Analyze main file
        print(f"📁 Analyzing: {main_file.relative_to(temp_dir)}")
        dependencies = analyzer.analyze_file(main_file)
        
        print(f"📋 Found {len(dependencies)} local dependencies:")
        for dep in sorted(dependencies):
            rel_path = dep.relative_to(temp_dir)
            print(f"   📄 {rel_path}")
        
        # Expected dependencies
        expected_files = {
            "utils/__init__.py",
            "utils/helper.py", 
            "utils/formatter.py",
            "data_processor.py"
        }
        
        # Convert Windows paths to forward slashes for comparison
        found_files = {str(dep.relative_to(temp_dir)).replace('\\', '/') for dep in dependencies}
        
        if expected_files.issubset(found_files):
            print("✅ Dependency analysis PASSED - all expected dependencies found")
            return True
        else:
            missing = expected_files - found_files
            print(f"❌ Dependency analysis FAILED - missing: {missing}")
            return False
            
    except Exception as e:
        print(f"❌ Dependency analysis failed: {e}")
        return False
    finally:
        # Cleanup
        import shutil
        shutil.rmtree(temp_dir)


def test_code_packaging():
    """Test complete code packaging with dependencies."""
    print("\n📦 Testing Code Packaging with Dependencies")
    print("=" * 50)
    
    # Create test files
    temp_dir, main_file = create_test_files()
    
    try:
        # Create a test class to package
        sys.path.insert(0, str(temp_dir))
        
        # Import and create an instance
        from main_module import MainProcessor
        processor = MainProcessor()
        
        # Initialize packager
        packager = CodePackager(project_root=temp_dir)
        
        # Package the object
        print(f"📦 Packaging object: {type(processor).__name__}")
        archive_bytes = packager.package_object(
            obj=processor,
            pip_requirements=["numpy>=1.20.0", "requests>=2.25.0"],
            exclude_patterns=["*.pyc", "__pycache__/*"]
        )
        
        print(f"📊 Archive size: {len(archive_bytes)} bytes")
        
        # Extract and examine archive
        info = packager.extract_archive_info(archive_bytes)
        
        print("📋 Archive contents:")
        print(f"   📄 Manifest version: {info['version']}")
        print(f"   🔧 Has serialized object: {info['has_serialized_object']}")
        print(f"   📦 Pip requirements: {len(info['pip_requirements'])}")
        print(f"   📁 Dependencies: {len(info['dependencies'])}")
        
        print("\n📁 Packaged dependencies:")
        for dep in sorted(info['dependencies']):
            print(f"   📄 {dep}")
        
        print("\n📦 Pip requirements:")
        for req in info['pip_requirements']:
            print(f"   📦 {req}")
        
        # Verify archive structure
        archive_buffer = io.BytesIO(archive_bytes)
        
        with zipfile.ZipFile(archive_buffer, 'r') as zf:
            files = zf.namelist()
            
            required_files = ["manifest.json", "serialized_object.pkl", "requirements.txt"]
            missing_files = [f for f in required_files if f not in files]
            
            if not missing_files:
                print("✅ Code packaging PASSED - all required files present")
                return True
            else:
                print(f"❌ Code packaging FAILED - missing files: {missing_files}")
                return False
        
    except Exception as e:
        print(f"❌ Code packaging failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Cleanup
        import shutil
        shutil.rmtree(temp_dir)
        if str(temp_dir) in sys.path:
            sys.path.remove(str(temp_dir))


def test_file_packaging():
    """Test packaging Python files without object serialization."""
    print("\n📁 Testing File-based Packaging")
    print("=" * 50)
    
    # Create test files
    temp_dir, main_file = create_test_files()
    
    try:
        # Initialize packager
        packager = CodePackager(project_root=temp_dir)
        
        # Package files
        print(f"📦 Packaging files from: {temp_dir}")
        archive_bytes = packager.package_files(
            entry_files=[main_file],
            pip_requirements=["scipy>=1.5.0"],
            exclude_patterns=["*.pyc"]
        )
        
        print(f"📊 Archive size: {len(archive_bytes)} bytes")
        
        # Extract and examine archive
        info = packager.extract_archive_info(archive_bytes)
        
        print("📋 Archive contents:")
        print(f"   📄 Manifest version: {info['version']}")
        print(f"   🔧 Has serialized object: {info['has_serialized_object']}")
        print(f"   📁 Entry files: {len(info['entry_files'])}")
        print(f"   📁 Dependencies: {len(info['dependencies'])}")
        
        if not info['has_serialized_object'] and len(info['dependencies']) > 0:
            print("✅ File packaging PASSED - dependencies detected without object serialization")
            return True
        else:
            print("❌ File packaging FAILED - unexpected archive structure")
            return False
        
    except Exception as e:
        print(f"❌ File packaging failed: {e}")
        return False
    finally:
        # Cleanup
        import shutil
        shutil.rmtree(temp_dir)


def main():
    """Run all dependency packaging tests."""
    print("🚀 RemoteMedia Dependency Packaging Test")
    print("=" * 60)
    print("Testing Phase 3 Code & Dependency Packager with AST analysis")
    print("=" * 60)
    
    tests = [
        ("AST Dependency Analysis", test_dependency_analysis),
        ("Code Packaging", test_code_packaging),
        ("File Packaging", test_file_packaging),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("🏆 FINAL RESULTS")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "PASS" if result else "FAIL"
        icon = "✅" if result else "❌"
        print(f"{icon} {test_name}: {status}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL DEPENDENCY PACKAGING TESTS PASSED!")
        print("🚀 AST-based dependency analysis is working!")
        print("📋 What we demonstrated:")
        print("   ✅ AST analysis for detecting local Python file dependencies")
        print("   ✅ Recursive dependency resolution")
        print("   ✅ Code packaging with CloudPickle serialization")
        print("   ✅ Archive creation with manifest and requirements")
        print("   ✅ File-based packaging without object serialization")
        print("\n🎯 Phase 3 Code & Dependency Packager is now complete!")
    else:
        print(f"\n⚠️  {total - passed} tests failed")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 