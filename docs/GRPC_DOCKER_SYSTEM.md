# gRPC-Enabled Docker System for Remote Execution

This document provides a comprehensive overview of the gRPC-enabled Docker system created for the RemoteMedia SDK's remote execution capabilities.

## System Overview

The remote execution system enables the RemoteMedia SDK to offload computationally intensive processing nodes to a secure, containerized service. This system is designed for Phase 2 of the development roadmap and provides the foundation for Phase 3's user-defined code execution.

## Architecture Components

### 1. gRPC Protocol Definitions

**Location**: `remote_service/protos/`

- **`execution.proto`**: Main service definition with 5 core RPC methods:
  - `ExecuteNode`: Execute predefined SDK nodes
  - `ExecuteCustomTask`: Execute user-defined code (Phase 3)
  - `StreamExecute`: Bidirectional streaming for real-time processing
  - `GetStatus`: Service health and metrics
  - `ListNodes`: Available SDK nodes discovery

- **`types.proto`**: Common data types and enumerations:
  - Execution status and service status enums
  - Execution options and metrics
  - Resource limits and security policies
  - Error details and health information

### 2. Remote Execution Service (Docker)

**Location**: `remote_service/`

#### Core Components:

- **`src/server.py`**: Main gRPC server implementation
  - Async gRPC servicer with comprehensive error handling
  - Health check integration
  - Graceful shutdown support
  - Request metrics and session management

- **`src/executor.py`**: Task execution engine
  - SDK node registry and instantiation
  - Serialization/deserialization handling
  - Memory and performance tracking
  - Extensible for Phase 3 custom code execution

- **`src/sandbox.py`**: Security sandbox manager
  - Multiple sandboxing technologies (bubblewrap, firejail, docker)
  - Resource limits enforcement
  - Network and filesystem isolation
  - Temporary workspace management

- **`src/config.py`**: Service configuration management
  - Environment variable integration
  - Validation and type checking
  - Security policy configuration

#### Docker Infrastructure:

- **`Dockerfile`**: Multi-stage build for security and efficiency
  - Builder stage for gRPC code generation
  - Runtime stage with minimal attack surface
  - Non-root user execution
  - Security tools (bubblewrap, firejail)

- **`docker-compose.yml`**: Development environment
  - Service orchestration
  - Optional monitoring (Prometheus, Grafana)
  - Session storage (Redis)
  - Volume mounts for development

- **`requirements.txt`**: Service dependencies
  - gRPC and async support
  - Security and monitoring tools
  - ML libraries for SDK node execution

### 3. Client-Side Integration

**Location**: `remotemedia/remote/`

- **`client.py`**: Remote execution client
  - Async gRPC client implementation
  - Connection management with retry logic
  - Serialization format negotiation
  - Error handling and timeout management
  - Context manager support for resource cleanup

### 4. Development and Deployment Tools

**Location**: `remote_service/scripts/`

- **`build.sh`**: Docker image build script
  - Automated gRPC code generation
  - Multi-architecture support
  - Image tagging and verification

- **`run.sh`**: Local development script
  - Environment setup
  - Dependency checking
  - Development mode configuration

### 5. Configuration and Monitoring

**Location**: `remote_service/config/`

- **`logging.yaml`**: Structured logging configuration
  - Multiple output formats (standard, detailed, JSON)
  - Log rotation and error separation
  - Component-specific log levels

## Security Features

### Multi-Layer Sandboxing

1. **Process-Level Isolation**:
   - Linux namespaces and cgroups
   - Capability dropping
   - Seccomp filters

2. **Container Isolation**:
   - Read-only filesystems
   - Network isolation
   - Resource limits

3. **Application-Level Security**:
   - Module import restrictions
   - Code validation
   - Execution timeouts

### Resource Management

- **Memory Limits**: Configurable per-task memory allocation
- **CPU Limits**: CPU usage percentage controls
- **Time Limits**: Execution timeout enforcement
- **Network Controls**: Optional network access with domain filtering
- **Filesystem Controls**: Restricted file system access

## Development Workflow

### Local Development

```bash
cd remote_service
./scripts/run.sh
```

### Docker Development

```bash
cd remote_service
./scripts/build.sh
docker-compose up -d
```

### Production Deployment

```bash
cd remote_service
./scripts/build.sh
docker run -p 50051:50051 remotemedia/execution-service:latest
```

## Integration with Main SDK

### Pipeline Integration

The main SDK's Pipeline class will be enhanced to:

1. Detect nodes with `RemoteExecutorConfig`
2. Establish gRPC connections to remote services
3. Serialize data and send execution requests
4. Handle responses and integrate results back into the pipeline

### Example Usage

```python
from remotemedia import Pipeline, RemoteExecutorConfig
from remotemedia.nodes import AudioTransform

# Configure remote execution
remote_config = RemoteExecutorConfig(
    host="localhost",
    port=50051,
    protocol="grpc",
    timeout=30.0
)

# Create pipeline with remote node
pipeline = Pipeline()
pipeline.add_node(AudioTransform(
    sample_rate=44100,
    remote_config=remote_config
))

# Process data (automatically uses remote execution)
result = pipeline.process(audio_data)
```

## Monitoring and Observability

### Metrics Collection

- Request counts and success rates
- Execution times and resource usage
- Active session tracking
- Error rates and types

### Health Monitoring

- Service health checks
- Resource utilization monitoring
- Sandbox status verification
- Connection pool health

### Logging

- Structured logging with multiple formats
- Request tracing and correlation
- Error tracking with stack traces
- Performance metrics logging

## Phase 2 vs Phase 3 Capabilities

### Phase 2 (Current Implementation)

- ✅ SDK node remote execution
- ✅ gRPC communication protocol
- ✅ Docker containerization
- ✅ Basic sandboxing
- ✅ Resource limits
- ✅ Health monitoring

### Phase 3 (Future Enhancement)

- ⏳ User-defined code execution
- ⏳ Dynamic dependency installation
- ⏳ Enhanced sandboxing (microVMs)
- ⏳ Code packaging and distribution
- ⏳ Advanced resource management

## Testing Strategy

### Unit Tests

- Individual component testing
- Mock gRPC services
- Sandbox functionality verification

### Integration Tests

- End-to-end pipeline execution
- Client-server communication
- Error handling scenarios

### Performance Tests

- Load testing with multiple concurrent requests
- Resource usage verification
- Latency and throughput measurement

## Deployment Considerations

### Production Requirements

- Container orchestration (Kubernetes recommended)
- Load balancing for multiple service instances
- Persistent storage for logs and metrics
- Network security (TLS, VPN)
- Monitoring and alerting infrastructure

### Scaling

- Horizontal scaling with multiple service instances
- Load balancing based on resource utilization
- Auto-scaling based on request volume
- Resource pool management

## Security Considerations

### Network Security

- TLS encryption for gRPC communication
- Network segmentation
- Firewall rules and access controls

### Container Security

- Regular base image updates
- Vulnerability scanning
- Runtime security monitoring
- Secrets management

### Code Execution Security

- Input validation and sanitization
- Output size limits
- Execution environment isolation
- Audit logging

## Future Enhancements

### Phase 3 Preparation

- Code packaging framework
- Dependency management system
- Enhanced sandboxing with microVMs
- User authentication and authorization

### Performance Optimizations

- Connection pooling
- Request batching
- Caching mechanisms
- Optimized serialization

### Operational Features

- Blue-green deployments
- Circuit breakers
- Rate limiting
- Request queuing

This gRPC-enabled Docker system provides a robust foundation for remote execution capabilities while maintaining security, performance, and scalability requirements. 