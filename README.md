# 🏗️ Oracle Trader v2.0

> **System Status:** Development (Planning Phase)  
> **Architecture:** Modular Multi-Process (HMM + PPO + cTrader Open API)

Oracle Trader v2.0 is an autonomous trading system designed for **high availability** and **exact parities** between training and execution environments. It utilizes a "Digital Twin" architecture where the prediction engine operates in a vacuum, entirely isolated from the execution reality, ensuring that the model's behavior in production mirrors its training performance.

## 🌟 Key Features

*   **Digital Twin Architecture**: The `Preditor` module maintains a virtual position state that perfectly mimics the training environment (`TradingEnv`), eliminating "drift" caused by broker constraints.
*   **HMM + PPO Core**: Combines **Hidden Markov Models** for regime detection with **Proximal Policy Optimization** for decision making.
*   **Broker Agnostic Core**: Logic is separated from execution. The `Connector` module abstracts the cTrader Open API.
*   **Resource Efficient**: Optimized to run 20+ models on an Oracle Cloud ARM VM (1GB RAM) using shared memory and optimized data structures.
*   **Semantic Actions**: Models output "Intent" (e.g., `LONG_STRONG`, `WAIT`) rather than raw orders, allowing the `Executor` to manage risk and lot sizing dynamically.

## 📚 Documentation Guide

Detailed documentation is available in the `docs/` directory. Use this guide to navigate the technical specifications:

| Document | Description | Target Audience |
| :--- | :--- | :--- |
| **[Project Structure](docs/ORACLE_V2_PROJECT_STRUCTURE.md)** | **START HERE.** Full overview of directories, modules, and architecture diagrams. | Developers, Architects |
| **[Technical Specification](docs/ORACLE_V2_SPECIFICATION_v1.1.md)** | The "Bible" of the project. detailed contracts, data formats, protocols, and sync logic. | Developers |
| **[High Availability Arch](docs/ARCH_V2_HIGH_AVAILABILITY_v1.1.md)** | Explains the "Digital Twin" concept, memory management, and how to run on 1GB RAM. | Architects, DevOps |
| **[Implementation Plan](docs/implementation_plan_v2.md)** | Step-by-step roadmap for building the v2 system, from Core to Orchestrator. | Project Managers, Devs |
| **[Training Notebook Spec](docs/oracle_v2_notebook_1.0_reorganization.md)** | Specification for the training environment and notebook reorganization. | Data Scientists |
| **[Infrastructure Guide](docs/guia_oracle_cloud_vm_arm.md)** | Setup guide for the Oracle Cloud ARM VM environment. | DevOps |
| **[Meta-Calibrator Spec](docs/meta_calibrador_spec_v1.0.md)** | (*Future Roadmap*) Specification for the meta-learning system for auto-calibration. | R&D |

## 📂 Project Structure Overview

```
oracle_v2/
├── core/                   # Shared kernels (Constants, Models, Features)
├── connector/              # Broker Interface (cTrader Open API)
├── preditor/               # "Brain": HMM + PPO + Virtual Position
├── executor/               # "Hands": Risk Checks + Order Execution
├── paper/                  # Simulation engine for benchmark
├── orchestrator/           # Lifecycle management
├── config/                 # System & Symbol configuration
└── models/                 # Trained model artifacts (.zip)
```

## 🚀 Getting Started

1.  **Read the [Project Structure](docs/ORACLE_V2_PROJECT_STRUCTURE.md)** to understand the modules.
2.  **Follow the [Implementation Plan](docs/implementation_plan_v2.md)** to set up the dev environment and start building the Core module.
3.  **Check the [Technical Spec](docs/ORACLE_V2_SPECIFICATION_v1.1.md)** for detailed API contracts between modules.

---
*Generated for Oracle Trader v2.0*
