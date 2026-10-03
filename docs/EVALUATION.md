# Academic Evaluation Mapping (AD23731)

This document explicitly maps the features and deliverables of the **AGENTTRADE** project to the evaluation criteria for **Foundations of Agentic AI - AD23731 (Rajalakshmi Engineering College)**.

---

## Project Review 1

### 1. Problem Statement and Business case
**Problem:** Single LLM chatbots often hallucinate financial news or leap from weak evidence to generating high-risk trading orders. 
**Business Case:** Provide a safer, controlled stock-research tool that separates retrieval, analysis, critique, and deterministic risk, requiring explicit Human-In-The-Loop (HITL) approval before executing paper trades.

### 2. User and stakeholder analysis
- **Users:** Finance students, academic researchers, and retail trading enthusiasts who need verifiable, cited stock research.
- **Stakeholders:** Academic evaluators assessing agentic architectures, and users expecting transparent reasoning without automated financial risk.

### 3. Proposed Agentic AI Solution
A multi-agent architecture incorporating an Analyst, Bull case generator, Bear case generator, and a Critic Judge. The system uses a bounded reflection process (one correction pass) to ensure accuracy and risk compliance before presenting the final output.

### 4. Dataset/Knowledge Source Identification
- **Knowledge Sources:** Live Yahoo Finance price history, statistics, and recent headlines. 
- **Datasets:** A frozen, seeded synthetic classroom corpus (Qdrant) for reproducible benchmark testing across different retrieval modes.

### 5. Selection of Tools/Frameworks
- **Orchestration:** n8n (replaces LangGraph/CrewAI for visual node-based workflow execution).
- **Models:** Ollama (Qwen2.5 7B for Analyst/Critic, Qwen2.5 3B for Retrieval/Debate).
- **Database/RAG:** Qdrant (Vector store) and SQLite (Relational ledger).
- **API/Backend:** FastAPI (Python).

### 6. Agent workflow and orchestration design
n8n routes a user request through three retrieval modes (None, Fixed, Agentic). The Agentic route allows the retrieval agent to autonomously query Qdrant. The evidence is passed to the Analyst, Bull, and Bear agents. Their outputs are evaluated by the Critic Judge, triggering a single bounded correction pass to prevent unconstrained loop execution.

### 7. Project Plan and Milestones
- **Phase 1 (Review 1):** Architecture design, tool selection, Qdrant evidence corpus generation.
- **Phase 2 (Review 2):** n8n orchestration implementation, tool integration, RAG setup, baseline evaluation script.
- **Phase 3 (End Sem):** Full FastAPI dashboard integration, Alpaca paper API deployment, final testing and technical report completion.

---

## Project Review 2

### 1. Functional prototype
The FastAPI dashboard is fully functional, capable of detecting stock tickers from natural language, executing the n8n multi-agent workflow, and rendering the final buy/hold/sell decisions with plain-language summaries.

### 2. Agent orchestration workflow implementation
The n8n workflow (`workflows/research.json`) is fully implemented, handling conditional routing, tool execution, parallel debate generation, and sequential critic evaluation.

### 3. Tool integrations
- **Qdrant Tool:** The retrieval agent autonomously queries the Qdrant database using Nomic embeddings.
- **Alpaca API:** Integrated for secure, paper-only order execution after dashboard approval.

### 4. Agentic RAG implementation
The system supports "Agentic RAG", where the model is provided with the Qdrant tool and dynamically formulates query terms based on the user's prompt, pulling relevant evidence cards (prices, news, stats).

### 5. Memory and state management
- **Short-term state:** Managed within the n8n workflow execution memory.
- **Long-term memory:** Stored externally in Qdrant (evidence) and SQLite (proposal ledger, order receipt IDs).

### 6. Preliminary evaluation results
A custom evaluation pipeline (`app/evaluate.py`) runs a 25-question benchmark across both models (Qwen and Llama) and all three retrieval modes, measuring latency, citation presence, and label accuracy.

### 7. Comparison with baseline solution
The system explicitly compares its Agentic RAG mode against two baselines: "No RAG" (relying only on model weights) and "Fixed RAG" (hardcoded top-3 retrieval).

---

## End Sem Project Viva-voce

### 1. Fully functional Agentic AI application
The AGENTTRADE application is complete, featuring natural language input, automated multi-agent research, risk boundary checks, and a Human-in-the-Loop approval dashboard.

### 2. End-to-end deployment/demo
The system can be deployed locally using Docker Compose (for FastAPI and Qdrant) alongside native n8n and Ollama, providing a complete end-to-end demonstration environment.

### 3. Source code repository
The repository includes all necessary Dockerfiles, Python requirements, n8n workflow JSON exports, and synthetic data generation scripts for immediate reproduction.

### 4. Technical report
The comprehensive architecture, capabilities, threats to validity, and evaluation methodologies are documented in the main `REPORT.md`.
