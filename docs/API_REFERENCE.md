# RemoteMedia SDK API Reference

## Core Components

### RemoteExecutorConfig

Configuration for remote execution of nodes and objects.

```python
from remotemedia.core.node import RemoteExecutorConfig

config = RemoteExecutorConfig(
    host="localhost",                    # Remote server hostname
    port=50052,                          # Remote server port
    protocol="grpc",                     # Communication protocol (currently only grpc)
    auth_token=None,                     # Optional authentication token
    timeout=30.0,                        # Request timeout in seconds
    max_retries=3,                       # Maximum retry attempts
    ssl_enabled=False,                   # Enable SSL/TLS encryption
    pip_packages=None                    # List of pip packages to install
)
```

#### Parameters

- **host** (str): Hostname or IP address of the remote execution server
- **port** (int): Port number for the remote server (default: 50052)
- **protocol** (str): Communication protocol, currently only "grpc" is supported
- **auth_token** (str, optional): Authentication token for secure connections
- **timeout** (float): Maximum time to wait for a response in seconds (default: 30.0)
- **max_retries** (int): Number of retry attempts for failed requests (default: 3)
- **ssl_enabled** (bool): Whether to use SSL/TLS for secure connections (default: False)
- **pip_packages** (List[str], optional): List of pip packages to install on the remote server

#### Pip Packages Feature

The `pip_packages` parameter allows you to specify Python packages that should be installed on the remote server before executing your code:

```python
config = RemoteExecutorConfig(
    host="localhost",
    port=50052,
    pip_packages=[
        "numpy",                # Basic package
        "pandas>=1.3.0",        # With version specification
        "scipy",                # Scientific computing
        "beautifulsoup4",       # Web scraping
        "pillow",               # Image processing
        "qrcode[pil]",          # Package with extras
        "matplotlib",           # Plotting
        "requests",             # HTTP requests
    ]
)
```

**Features:**
- Packages are installed in an isolated virtual environment per session
- Supports version specifications (e.g., `"numpy>=1.21.0"`)
- Supports packages with extras (e.g., `"qrcode[pil]"`)
- Dependencies are automatically resolved
- Installation happens once when creating the proxy
- Clear error messages if installation fails

### RemoteProxyClient

Client for creating transparent proxies of Python objects for remote execution.

```python
from remotemedia.remote import RemoteProxyClient

async with RemoteProxyClient(config) as client:
    # Create a proxy for any Python object
    local_obj = MyClass()
    remote_obj = await client.create_proxy(local_obj)
    
    # Use the remote object transparently
    result = await remote_obj.method(arg1, arg2)
```

#### Methods

##### create_proxy(obj, serialization_format="pickle")

Creates a remote proxy for a Python object.

**Parameters:**
- **obj**: Any serializable Python object
- **serialization_format** (str): Serialization format ("pickle" or "json")

**Returns:**
- RemoteProxy: A proxy object that forwards all method calls to the remote server

**Example:**
```python
class DataProcessor:
    def __init__(self):
        self.cache = {}
    
    def process(self, data):
        import numpy as np  # This will work if numpy is in pip_packages
        return np.mean(data)

config = RemoteExecutorConfig(
    host="localhost",
    port=50052,
    pip_packages=["numpy"]
)

async with RemoteProxyClient(config) as client:
    processor = DataProcessor()
    remote_processor = await client.create_proxy(processor)
    
    # numpy is now available on the remote server
    result = await remote_processor.process([1, 2, 3, 4, 5])
```

### RemoteProxy

The proxy object returned by `create_proxy()`. All attribute access and method calls are transparently forwarded to the remote server.

#### Supported Operations

- **Method calls**: `await remote_obj.method(args)`
- **Property access**: `await remote_obj.property`
- **Async methods**: `await remote_obj.async_method()`
- **Generators**: Return generator proxies for streaming
- **Keyword arguments**: `await remote_obj.method(a=1, b=2)`

## Server-Side Components

### Virtual Environment Management

When pip packages are specified, the server:

1. Creates a virtual environment in the sandbox directory
2. Installs packages using `pip install` in the venv
3. Adds the site-packages directory to `sys.path`
4. Isolates dependencies between different sessions

### Installation Process

```python
# Server-side installation (automatic)
venv_path = os.path.join(sandbox_path, "venv")
python -m venv {venv_path}
{venv_path}/bin/pip install {package}
sys.path.insert(0, "{venv_path}/lib/python{version}/site-packages")
```

## Examples

### Basic Usage with Pip Packages

```python
from remotemedia.core.node import RemoteExecutorConfig
from remotemedia.remote import RemoteProxyClient

# Configure with required packages
config = RemoteExecutorConfig(
    host="localhost",
    port=50052,
    pip_packages=["requests", "beautifulsoup4"]
)

class WebScraper:
    def get_title(self, url):
        import requests
        from bs4 import BeautifulSoup
        
        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        return soup.title.string if soup.title else "No title found"

async def main():
    async with RemoteProxyClient(config) as client:
        scraper = WebScraper()
        remote_scraper = await client.create_proxy(scraper)
        
        # Packages are installed automatically
        title = await remote_scraper.get_title("https://example.com")
        print(f"Page title: {title}")

asyncio.run(main())
```

### Scientific Computing

```python
config = RemoteExecutorConfig(
    host="localhost",
    port=50052,
    pip_packages=["numpy", "scipy", "pandas", "matplotlib"]
)

class ScientificProcessor:
    def analyze_data(self, data_points):
        import numpy as np
        import pandas as pd
        from scipy import stats
        
        df = pd.DataFrame(data_points)
        return {
            "mean": df.mean().to_dict(),
            "std": df.std().to_dict(),
            "correlation": df.corr().to_dict(),
            "normality_test": {
                col: stats.shapiro(df[col])[1] 
                for col in df.columns
            }
        }
```

### Machine Learning

```python
config = RemoteExecutorConfig(
    host="localhost",
    port=50052,
    pip_packages=[
        "scikit-learn",
        "numpy",
        "pandas",
        "joblib"
    ]
)

class MLProcessor:
    def train_model(self, X, y):
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.model_selection import cross_val_score
        
        model = RandomForestClassifier(n_estimators=100)
        scores = cross_val_score(model, X, y, cv=5)
        model.fit(X, y)
        
        return {
            "cv_scores": scores.tolist(),
            "mean_score": scores.mean(),
            "model_params": model.get_params()
        }
```

## Error Handling

### Package Installation Errors

If a package fails to install, you'll get a clear error message:

```python
# If package doesn't exist
RemoteExecutionError: No module named 'nonexistent_package'

# If installation fails
ERROR: Failed to install invalid-package: ...
```

### Best Practices

1. **Specify exact versions** for reproducibility:
   ```python
   pip_packages=["numpy==1.21.0", "pandas==1.3.0"]
   ```

2. **Group related packages** to minimize installation time:
   ```python
   pip_packages=["scipy", "numpy", "matplotlib"]  # Install together
   ```

3. **Use package extras** when needed:
   ```python
   pip_packages=["qrcode[pil]", "requests[socks]"]
   ```

4. **Test locally first** to ensure packages are compatible

5. **Consider package size** - large packages like TensorFlow may take time to install

## Limitations

- Packages are installed per session (not globally on server)
- Binary dependencies must be available in the Docker container
- Some packages requiring system libraries may not work
- Installation happens synchronously during proxy creation
- Virtual environments are cleaned up when sessions end