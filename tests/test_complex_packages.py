"""Test more complex pip packages with dependencies."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from remotemedia.core.node import RemoteExecutorConfig
from remotemedia.remote.proxy_client import RemoteProxyClient


class ComplexPackageTests:
    """Test packages with multiple dependencies."""
    
    def test_matplotlib(self) -> dict:
        """Test matplotlib for plotting (requires numpy)."""
        import matplotlib
        matplotlib.use('Agg')  # Use non-interactive backend
        import matplotlib.pyplot as plt
        import numpy as np
        
        # Create a simple plot
        x = np.linspace(0, 10, 100)
        y = np.sin(x)
        
        fig, ax = plt.subplots()
        ax.plot(x, y)
        ax.set_title('Sine Wave')
        
        # Save to bytes
        import io
        import base64
        buf = io.BytesIO()
        fig.savefig(buf, format='png')
        buf.seek(0)
        img_base64 = base64.b64encode(buf.read()).decode()
        
        return {
            "matplotlib_version": matplotlib.__version__,
            "backend": matplotlib.get_backend(),
            "plot_size": f"{fig.get_figwidth()}x{fig.get_figheight()}",
            "image_preview": img_base64[:50] + "..."
        }
    
    def test_pillow(self) -> dict:
        """Test PIL/Pillow for image processing."""
        from PIL import Image, ImageDraw, ImageFont
        import io
        import base64
        
        # Create a new image
        img = Image.new('RGB', (200, 100), color='white')
        draw = ImageDraw.Draw(img)
        
        # Draw some shapes
        draw.rectangle([10, 10, 50, 50], fill='red')
        draw.ellipse([60, 10, 100, 50], fill='blue')
        draw.text((10, 60), "Hello PIL!", fill='black')
        
        # Convert to base64
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        img_base64 = base64.b64encode(buf.read()).decode()
        
        return {
            "image_size": img.size,
            "image_mode": img.mode,
            "image_format": img.format,
            "base64_preview": img_base64[:50] + "..."
        }
    
    def test_httpx(self) -> dict:
        """Test httpx for HTTP requests."""
        import httpx
        
        # Make a simple request
        with httpx.Client() as client:
            response = client.get("https://httpbin.org/json")
            
        return {
            "status_code": response.status_code,
            "response_type": str(type(response)),
            "json_keys": list(response.json().keys()) if response.status_code == 200 else [],
            "httpx_version": httpx.__version__
        }
    
    def test_pyyaml(self) -> dict:
        """Test PyYAML for YAML processing."""
        import yaml
        
        # Sample YAML data
        yaml_str = """
        name: Test Config
        version: 1.0
        features:
          - authentication
          - logging
          - caching
        settings:
          debug: true
          port: 8080
        """
        
        # Parse YAML
        data = yaml.safe_load(yaml_str)
        
        # Convert back to YAML
        yaml_output = yaml.dump(data, default_flow_style=False)
        
        return {
            "parsed_data": data,
            "yaml_output_length": len(yaml_output),
            "yaml_version": yaml.__version__
        }
    
    def test_jinja2(self) -> dict:
        """Test Jinja2 template engine."""
        from jinja2 import Template
        
        # Create a template
        template_str = """
        Hello {{ name }}!
        {% for item in items %}
        - {{ item }}
        {% endfor %}
        Total items: {{ items|length }}
        """
        
        template = Template(template_str)
        rendered = template.render(name="World", items=["foo", "bar", "baz"])
        
        return {
            "rendered_output": rendered.strip(),
            "template_length": len(template_str),
            "rendered_length": len(rendered)
        }


async def test_package(package_name: str, test_method_name: str):
    """Test a single package installation and usage."""
    print(f"\n{'='*60}")
    print(f"Testing: {package_name}")
    print('='*60)
    
    # Some packages need additional dependencies
    packages = [package_name]
    if package_name == "matplotlib":
        packages.extend(["numpy", "pyparsing", "python-dateutil"])
    
    config = RemoteExecutorConfig(
        host="localhost", 
        port=50052, 
        ssl_enabled=False,
        pip_packages=packages
    )
    
    try:
        async with RemoteProxyClient(config) as client:
            tests = ComplexPackageTests()
            remote_tests = await client.create_proxy(tests)
            
            print(f"Installing {package_name} on remote server...")
            method = getattr(remote_tests, test_method_name)
            result = await method()
            
            print(f"✅ Success! {package_name} was installed and used.")
            print(f"Result: {result}")
            return True
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all package tests."""
    print("\nTESTING COMPLEX PIP PACKAGES WITH DEPENDENCIES")
    print("=" * 80)
    print("Testing packages that have multiple dependencies\n")
    
    # Define tests
    tests = [
        ("matplotlib", "test_matplotlib"),
        ("pillow", "test_pillow"),
        ("httpx", "test_httpx"),
        ("pyyaml", "test_pyyaml"),
        ("jinja2", "test_jinja2"),
    ]
    
    success_count = 0
    total_count = len(tests)
    
    for package, method in tests:
        if await test_package(package, method):
            success_count += 1
        
        await asyncio.sleep(0.5)  # Small delay between tests
    
    print(f"\n{'='*80}")
    print(f"SUMMARY: {success_count}/{total_count} tests passed")
    print('='*80)
    
    if success_count == total_count:
        print("✅ All complex package tests passed!")
    else:
        print("⚠️  Some tests failed. Check the errors above.")


if __name__ == "__main__":
    asyncio.run(main())