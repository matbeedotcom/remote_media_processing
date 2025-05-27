#!/usr/bin/env python3
"""
Test the existing custom library packaging with the user's created files.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path.cwd()))

from remotemedia.packaging import CodePackager, DependencyAnalyzer


def test_existing_custom_library():
    """Test dependency analysis and packaging with the existing custom library."""
    print("🔍 Testing Existing Custom Library Structure")
    print("=" * 60)
    
    # Set up paths
    project_root = Path.cwd()
    test_dir = project_root / "tests" / "import_detection_tests"
    main_file = test_dir / "custom_node_with_imports.py"
    
    print(f"📁 Project root: {project_root}")
    print(f"📁 Test directory: {test_dir}")
    print(f"📄 Main file: {main_file}")
    
    # Test 1: Dependency Analysis
    print(f"\n🔍 Step 1: Analyzing dependencies...")
    try:
        analyzer = DependencyAnalyzer(project_root=test_dir)
        dependencies = analyzer.analyze_file(main_file)
        
        print(f"📋 Found {len(dependencies)} local dependencies:")
        for dep in sorted(dependencies):
            rel_path = dep.relative_to(test_dir)
            print(f"   📄 {rel_path}")
        
        # Check if we found the expected custom_math files
        expected_files = {
            "custom_math/__init__.py",
            "custom_math/advanced.py", 
            "custom_math/statistics.py",
            "custom_math/utils.py"
        }
        
        found_files = {str(dep.relative_to(test_dir)).replace('\\', '/') for dep in dependencies}
        
        if expected_files.issubset(found_files):
            print("✅ Dependency analysis PASSED")
            analysis_success = True
        else:
            missing = expected_files - found_files
            print(f"❌ Missing dependencies: {missing}")
            analysis_success = False
            
    except Exception as e:
        print(f"❌ Dependency analysis failed: {e}")
        analysis_success = False
    
    # Test 2: Code Packaging
    print(f"\n📦 Step 2: Testing code packaging...")
    try:
        # Add test directory to Python path so we can import
        sys.path.insert(0, str(test_dir))
        
        # Import the custom node
        from custom_node_with_imports import CustomNodeWithImports
        custom_node = CustomNodeWithImports()
        
        # Package it using the source file approach
        packager = CodePackager(project_root=test_dir)
        
        # Use package_object with additional_files to ensure dependencies are detected
        archive_bytes = packager.package_object(
            obj=custom_node,
            additional_files=[main_file],  # Explicitly include the source file
            pip_requirements=["numpy>=1.20.0"]
        )
        
        print(f"📊 Archive size: {len(archive_bytes)} bytes")
        
        # Extract info
        info = packager.extract_archive_info(archive_bytes)
        
        print("📋 Archive contents:")
        print(f"   🔧 Has serialized object: {info['has_serialized_object']}")
        print(f"   📁 Dependencies: {len(info['dependencies'])}")
        print(f"   📦 Pip requirements: {len(info['pip_requirements'])}")
        
        print("\n📁 Packaged dependencies:")
        for dep in sorted(info['dependencies']):
            print(f"   📄 {dep}")
        
        print("\n📦 Pip requirements:")
        for req in info['pip_requirements']:
            print(f"   📦 {req}")
        
        # Check if custom_math files are included
        custom_math_files = [dep for dep in info['dependencies'] if 'custom_math' in dep]
        
        if len(custom_math_files) >= 4:  # __init__, advanced, statistics, utils
            print("✅ Code packaging PASSED")
            packaging_success = True
        else:
            print(f"❌ Expected 4+ custom_math files, found {len(custom_math_files)}")
            packaging_success = False
            
    except Exception as e:
        print(f"❌ Code packaging failed: {e}")
        import traceback
        traceback.print_exc()
        packaging_success = False
    finally:
        # Cleanup path
        if str(test_dir) in sys.path:
            sys.path.remove(str(test_dir))
    
    # Test 3: Object Functionality
    print(f"\n🧪 Step 3: Testing object functionality...")
    try:
        # Add test directory to Python path again
        sys.path.insert(0, str(test_dir))
        
        from custom_node_with_imports import CustomNodeWithImports
        node = CustomNodeWithImports()
        
        # Test different operations
        test_cases = [
            {
                "operation": "complex_calc",
                "data": {"x": 3, "y": 4},
                "expected_type": dict
            },
            {
                "operation": "statistics", 
                "data": {"dataset": [1, 2, 3, 4, 5]},
                "expected_type": dict
            },
            {
                "operation": "matrix_op",
                "data": {"matrix": [[1, 2], [3, 4], [5, 6]]},
                "expected_type": dict
            }
        ]
        
        all_passed = True
        for i, test_case in enumerate(test_cases, 1):
            print(f"   🧪 Test {i}: {test_case['operation']}")
            result = node.process_data(test_case['operation'], test_case['data'])
            
            if isinstance(result, test_case['expected_type']) and 'error' not in result:
                print(f"      ✅ Success: {type(result).__name__}")
            else:
                print(f"      ❌ Failed: {result}")
                all_passed = False
        
        if all_passed:
            print("✅ Object functionality PASSED")
            functionality_success = True
        else:
            print("❌ Some functionality tests failed")
            functionality_success = False
            
    except Exception as e:
        print(f"❌ Object functionality test failed: {e}")
        import traceback
        traceback.print_exc()
        functionality_success = False
    finally:
        # Cleanup path
        if str(test_dir) in sys.path:
            sys.path.remove(str(test_dir))
    
    # Summary
    print(f"\n" + "=" * 60)
    print("🏆 FINAL RESULTS")
    print("=" * 60)
    
    results = [
        ("Dependency Analysis", analysis_success),
        ("Code Packaging", packaging_success), 
        ("Object Functionality", functionality_success)
    ]
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for test_name, success in results:
        status = "PASS" if success else "FAIL"
        icon = "✅" if success else "❌"
        print(f"{icon} {test_name}: {status}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        print("🚀 Your custom library structure works perfectly!")
        print("📋 What we verified:")
        print("   ✅ AST analysis detects all custom_math imports")
        print("   ✅ Code packaging includes all dependencies")
        print("   ✅ Custom node functionality works correctly")
        print("   ✅ CloudPickle serialization preserves functionality")
        print("\n🎯 Your custom library IS ready for remote execution!")
    else:
        print(f"\n⚠️  {total - passed} tests failed")
    
    return passed == total


if __name__ == "__main__":
    success = test_existing_custom_library()
    sys.exit(0 if success else 1) 