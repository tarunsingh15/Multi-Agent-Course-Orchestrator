# Multi-Agent-Course-Orchestrator

A production-grade event-driven, multi-agent AI orchestration microservices platform that autonomously generates grounded, structured educational courses from raw unstructured documents using RAG and LLM-as-a-Judge evaluation.

Moving beyond simple zero-shot prompts, this system implements an Orchestrator-Worker architecture. A central routing agent delegates complex cognitive tasks to specialized sub-agents (Blueprint Planning, RAG-assisted Lesson Writing, and Quiz Extraction). To ensure enterprise-level reliability and prevent hallucinations, the pipeline integrates an 'LLM-as-a-Judge' Evaluator agent that strictly verifies all generated content against the source material before state commits. Built with Python, FastAPI, and containerized for Google Cloud Platform.

**Key Capabilities:**

- **Agentic Orchestration**: A central state-manager that dynamically routes tasks to specialized cognitive worker agents.

- **RAG-Grounded Generation**: Utilizes Retrieval-Augmented Generation to ensure all course content is strictly fact-based and tied to the uploaded source documents.

- **Automated Quality Assurance**: Features an independent Evaluator API utilizing the Reflexion/Critic pattern to detect and reject LLM hallucinations.

- **Asynchronous Event-Driven Backend**: Decoupled FastAPI and Node.js services communicating via state updates to handle heavy document parsing and long-running generation tasks without blocking the UI.

https://github.com/user-attachments/assets/2e3e330e-bba5-4dc1-b88e-ee628118a302

