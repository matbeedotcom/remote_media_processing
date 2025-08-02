"""Test various external pip packages in remote execution."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from remotemedia.core.node import RemoteExecutorConfig
from remotemedia.remote.proxy_client import RemoteProxyClient


class ExternalPackageTests:
    """Test various external packages that are not typically pre-installed."""
    
    def test_beautifulsoup(self, html: str) -> dict:
        """Test BeautifulSoup4 for HTML parsing."""
        from bs4 import BeautifulSoup
        
        soup = BeautifulSoup(html, 'html.parser')
        return {
            "title": soup.title.string if soup.title else None,
            "links": [a.get('href') for a in soup.find_all('a')][:5],
            "paragraphs": len(soup.find_all('p'))
        }
    
    def test_faker(self) -> dict:
        """Test Faker for generating fake data."""
        from faker import Faker
        
        fake = Faker()
        return {
            "name": fake.name(),
            "email": fake.email(),
            "address": fake.address(),
            "company": fake.company(),
            "job": fake.job()
        }
    
    def test_python_dotenv(self) -> dict:
        """Test python-dotenv functionality."""
        from dotenv import dotenv_values
        import tempfile
        
        # Create a temporary .env file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write("TEST_VAR=hello_world\n")
            f.write("API_KEY=secret123\n")
            temp_path = f.name
        
        # Load the values
        config = dotenv_values(temp_path)
        
        # Clean up
        os.unlink(temp_path)
        
        return {
            "loaded_vars": dict(config),
            "test_var": config.get("TEST_VAR"),
            "api_key": config.get("API_KEY")
        }
    
    def test_pytz(self) -> dict:
        """Test pytz for timezone operations."""
        import pytz
        from datetime import datetime
        
        utc = pytz.UTC
        eastern = pytz.timezone('US/Eastern')
        tokyo = pytz.timezone('Asia/Tokyo')
        
        now_utc = datetime.now(utc)
        now_eastern = now_utc.astimezone(eastern)
        now_tokyo = now_utc.astimezone(tokyo)
        
        return {
            "utc_time": now_utc.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "eastern_time": now_eastern.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "tokyo_time": now_tokyo.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "available_timezones": len(pytz.all_timezones)
        }
    
    def test_markdown(self) -> dict:
        """Test markdown to HTML conversion."""
        import markdown
        
        md_text = """
# Hello World

This is a **bold** text and this is *italic*.

- Item 1
- Item 2
- Item 3

[Link to Google](https://google.com)
"""
        
        html = markdown.markdown(md_text)
        return {
            "original_length": len(md_text),
            "html_length": len(html),
            "html_preview": html[:200] + "..." if len(html) > 200 else html
        }
    
    def test_qrcode(self, data: str) -> dict:
        """Test QR code generation."""
        import qrcode
        import io
        import base64
        
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(data)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to base64
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        img_str = base64.b64encode(buffer.getvalue()).decode()
        
        return {
            "data": data,
            "qr_version": qr.version,
            "qr_size": f"{img.size[0]}x{img.size[1]}",
            "base64_preview": img_str[:50] + "..."
        }
    
    def test_emoji(self) -> dict:
        """Test emoji package."""
        import emoji
        
        text_with_emoji = "Python is :snake: and I :heart: it! :rocket:"
        emojized = emoji.emojize(text_with_emoji)
        demojized = emoji.demojize("Python is 🐍 and I ❤️ it! 🚀")
        
        return {
            "original": text_with_emoji,
            "emojized": emojized,
            "demojized": demojized,
            "emoji_count": emoji.emoji_count(emojized)
        }


async def test_package(package_name: str, test_method_name: str, *args):
    """Test a single package installation and usage."""
    print(f"\n{'='*60}")
    print(f"Testing: {package_name}")
    print('='*60)
    
    config = RemoteExecutorConfig(
        host="localhost", 
        port=50052, 
        ssl_enabled=False,
        pip_packages=[package_name]
    )
    
    try:
        async with RemoteProxyClient(config) as client:
            tests = ExternalPackageTests()
            remote_tests = await client.create_proxy(tests)
            
            print(f"Installing {package_name} on remote server...")
            method = getattr(remote_tests, test_method_name)
            result = await method(*args)
            
            print(f"✅ Success! {package_name} was installed and used.")
            print(f"Result: {result}")
            return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


async def main():
    """Run all package tests."""
    print("\nTESTING EXTERNAL PIP PACKAGE INSTALLATION")
    print("=" * 80)
    print("Testing packages that are NOT pre-installed in conda environment\n")
    
    # Define tests with their required packages
    tests = [
        ("beautifulsoup4", "test_beautifulsoup", "<html><head><title>Test Page</title></head><body><p>Hello</p><a href='#'>Link</a></body></html>"),
        ("faker", "test_faker"),
        ("python-dotenv", "test_python_dotenv"),
        ("pytz", "test_pytz"),
        ("markdown", "test_markdown"),
        ("qrcode[pil]", "test_qrcode", "https://github.com"),
        ("emoji", "test_emoji"),
    ]
    
    success_count = 0
    total_count = len(tests)
    
    for test_params in tests:
        package = test_params[0]
        method = test_params[1]
        args = test_params[2:] if len(test_params) > 2 else []
        
        if await test_package(package, method, *args):
            success_count += 1
        
        await asyncio.sleep(0.5)  # Small delay between tests
    
    print(f"\n{'='*80}")
    print(f"SUMMARY: {success_count}/{total_count} tests passed")
    print('='*80)
    
    if success_count == total_count:
        print("✅ All tests passed! Pip package installation is working correctly.")
    else:
        print("⚠️  Some tests failed. Check the errors above.")


if __name__ == "__main__":
    asyncio.run(main())