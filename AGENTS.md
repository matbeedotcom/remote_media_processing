# Agent Instructions for RemoteMediaProcessing SDK

This document provides instructions and guidelines for AI agents contributing to the RemoteMediaProcessing SDK.

## Project Overview & Vision

The project is a Python-based SDK for building distributed audio/video/data processing pipelines. The key feature is the ability to transparently offload computationally intensive tasks to a remote execution service. Please review the `DevelopmentStrategyDocument.md` for the full vision and phased plan. The project is currently entering **Phase 4: Streaming, Synchronization, and Production Hardening**.

## Core Architecture Principles

The system has two main components:
1.  **`remotemedia` SDK**: The client-side Python package that developers use to build pipelines. 【F:FILE_STRUCTURE.md†L16-L17】
2.  **`remote_service`**: The server-side gRPC service that executes tasks remotely. This service is designed to run in a secure Docker container. 【F:FILE_STRUCTURE.md†L12-L13】

**CRITICAL ARCHITECTURAL CONSTRAINT:** The `remote_service` **MUST** use the processing nodes directly from the `remotemedia` SDK package. There should be no duplication of node logic. The `remotemedia` package is the single source of truth for all processing nodes. 【F:PHASE_3_PROJECT_TRACKING.md†L186-L191】

-   All communication between the client and server is done via gRPC. The protobuf definitions are in `remote_service/src/protos/`. 【F:GRPC_DOCKER_SYSTEM.md†L10-L11】
-   Security for remote code execution is a top priority. Changes to the sandboxing mechanism (`remote_service/src/sandbox.py`) must be carefully considered to avoid security vulnerabilities. 【F:DevelopmentStrategyDocument.md†L193-L194】

## Development Setup & Workflow

1.  **Environment:** Set up a Python 3.9+ virtual environment. Install dependencies using the provided `requirements` files:
    ```bash
    python -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt -r requirements-dev.txt -r requirements-ml.txt
    ```

2.  **Running the Remote Service:** For development and testing that involves remote execution, you need to run the `remote_service`.
    -   **For local development (recommended):**
        ```bash
        cd remote_service/
        ./scripts/run.sh # This runs the gRPC server locally
        ```
        【F:GRPC_DOCKER_SYSTEM.md†L132-L135】
    -   **Using Docker:**
        ```bash
        cd remote_service/
        ./scripts/build.sh # To build the docker image
        docker-compose up -d # To run the service
        ```
        【F:GRPC_DOCKER_SYSTEM.md†L137-L142】

## Coding & Style Guidelines

-   **Modularity**: Adhere to the existing modular structure. New nodes go in `remotemedia/nodes/` and should be in their own files if they are complex. New core functionalities should be placed in `remotemedia/core/`. 【F:FILE_STRUCTURE.md†L109-L113】
-   **Node Implementation**: All processing nodes must inherit from `remotemedia.core.node.Node`.
-   **Documentation**: Provide clear, inline documentation and docstrings for all new classes and methods.
-   **Dependencies**: The system for packaging user-defined dependencies (`remotemedia/packaging/`) uses AST analysis. Be mindful of this when modifying import logic. 【F:PROJECT_TRACKING.md†L62-L66】
-   **Error Handling**: Use the custom exceptions defined in `remotemedia.core.exceptions` where appropriate.

## Testing

-   **Comprehensive testing is mandatory.** All new features or bug fixes must be accompanied by tests.
-   The test suite is located in the `tests/` directory.
-   Run the full test suite using `pytest` from the project root:
    ```bash
    pytest
    ```
-   When adding new nodes or remote execution features, ensure you add integration tests that cover the full client-server interaction. Refer to `tests/test_cloudpickle_execution.py` and `tests/test_remote_code_execution.py` for examples. 【F:FILE_STRUCTURE.md†L80-L81】

## Git & Commit Instructions

-   Do not create new branches. Commit your changes to the main branch.
-   Write clear and descriptive commit messages.
-   If your changes are part of a larger phase (e.g., Phase 4), mention it in the commit message.
-   Ensure the working directory is clean (`git status` shows no uncommitted changes) before finishing your task.

## PR Message Instructions

-   The PR message should clearly summarize the changes and their purpose.
-   Reference the relevant project tracking documents (`PROJECT_TRACKING.md`, `PHASE_3_PROJECT_TRACKING.md`) if your changes address specific deliverables.
-   Explain the technical implementation details and any architectural decisions made.
-   If you modify any part of the remote execution or sandboxing, explicitly state what was changed and why, with a focus on the security implications.

## Citations Instructions

- If you browsed files or used terminal commands, you must add citations to your response where relevant. Citations reference file paths and terminal outputs with the following formats:
  1) `【F:<file_path>†L<line_start>(-L<line_end>)?】`
  - File path citations must start with `F:`. `file_path` is the exact file path of the file relative to the root of the repository that contains the relevant text.
  - `line_start` is the 1-indexed start line number of the relevant output within that file.
  2) `【<chunk_id>†L<line_start>(-L<line_end>)?】`
  - Where `chunk_id` is the chunk_id of the terminal output, `line_start` and `line_end` are the 1-indexed start and end line numbers of the relevant output within that chunk.
- Line ends are optional, and if not provided, line end is the same as line start, so only 1 line is cited.
- Do not cite completely empty lines inside the chunk, only cite lines that have content.
- Use file path citations that reference any code changes, documentation or files, and use terminal citations only for relevant terminal output. 