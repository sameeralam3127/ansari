# A.N.S.A.R.I.

**Advanced Native Scripting for Automated Resource Integration**

[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

> **Ansari** (Arabic: _Ansar_) means "The Helper."

ANSARI is a Python-native DevOps utility designed to bridge the gap between complex infrastructure and the engineers who manage it. It provides a unified, human-centric interface for resource orchestration, health auditing, and automated workflows.

---

## ✨ Key Features

- **Native Resource Integration:** Seamlessly interacts with Cloud APIs (AWS, GCP, Azure) and Kubernetes without heavy wrapper overhead.
- **Intelligent Auditing:** Don't just see logs—get context. Ansari interprets resource states to tell you _why_ things are failing.
- **Extensible Module Architecture:** Easily add new "Support Modules" for your specific stack.
- **Beautiful CLI:** Powered by `Typer` and `Rich` for a terminal experience that is as readable as it is functional.

## 🚀 Quick Start

### Installation

Ensure you have [Poetry](https://python-poetry.org/) installed:

```bash
git clone [https://github.com/your-username/ansari.git](https://github.com/your-username/ansari.git)
cd ansari
poetry install
```

### Usage

Run the main helper to see available commands:

```bash
ansari --help
```

Check the health of a specific resource:

```bash
ansari check --resource eks-cluster-01
```

## 📂 Project Structure

- `ansari/core/`: The "Brain" – handles internal logic and configuration.
- `ansari/modules/`: The "Hands" – contains integrations for AWS, K8s, Terraform, etc.
- `ansari/main.py`: The "Voice" – the CLI interface you interact with.

## 🛠 Built With

- **Python 3.11+** - The foundation.
- **Typer** - For building the CLI.
- **Rich** - For beautiful terminal formatting and progress bars.
- **Pydantic** - For rock-solid data validation.

## 🤝 Contributing

We welcome "Helpers" from all backgrounds! If you'd like to add a new module or improve the core:

1. Fork the Project.
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`).
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`).
4. Push to the Branch (`git push origin feature/AmazingFeature`).
5. Open a Pull Request.

---
