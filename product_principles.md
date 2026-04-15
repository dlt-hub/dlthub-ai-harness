# dltHub Product Principles

### Context

We want to leverage product principles to enable fast product and design decisions and consistently work towards our vision of a developer- and agent-friendly libraries and platform. We also use the product principles for our external positioning (see [dltHub Product Messaging Alignment](https://www.notion.so/dltHub-Product-Messaging-Alignment-3199fb8e23cf80ffa36ddad8e77cfaa7?pvs=21)). Some of the examples mentioned below are still a part of our vision or roadmap.

### **1. Transparent, declarative, and context-aware by design**

dltHub is code-first and declarative where possible, and avoids black-box abstractions. Pipelines, sources, and workflows are represented as code that can be inspected, customized, and extended. Context does not live only in prompts: it flows through the library and platform from the source as metadata, schemas, annotations, traces, and semantics.

This is important for AI because agents perform best when they operate within explicit, inspectable systems and when every tool in the stack can understand, enrich, and pass context forward. Semantics begin capturing documentation at the data source and compounds as data moves from ingestion / transformation through runtime. This avoids “black holes” where information is lost or downstream tools no longer understand upstream intent.

**In practice**

- Verified sources and AI toolkits are distributed as plain code and are designed to be customized.
- Pipeline observability from development (dlt dashboard) to maintenance stage (dltHub pipeline observability)
- Agents and users can initialize a pipeline and directly inspect and modify the generated project.
- Source definitions, schema information, and runtime metadata inform downstream steps - data quality can be maintained from the source.
- Logs, traces, and execution metadata remain available for inspection and reasoning.
- Agents can perform much of their work using metadata, without requiring direct access to sensitive data.

### **2. Modular libraries and composable architecture**

dltHub is built from modular libraries and discrete platform capabilities, not from a single monolithic system. This gives agents reusable primitives and gives developers flexibility in how they assemble workflows.

This helps AI agents because high-quality systems are more likely to emerge from composition of proven building blocks than from generating every component from first principles. It also reflects the reality that there is no one-size-fits-all data platform: users and agents should be able to use the parts of dltHub they need and integrate them with the wider ecosystem. The modular design helps steer agents toward platform-native best practices instead of ad hoc implementations.

**In practice**

- Most workflows can be expressed by decorating regular Python functions.
- Sources and resources are standard Python iterators, including async and parallel variants.
- The platform integrates with the surrounding ecosystem and allows users to adopt only the components they need. (examples: dltHub supports different destinations, supports marimo and Streamlit for data apps, leverages Ibis; future plan for “bring your own data plane)
- The modular structure of dlt and dltHub libraries helps agents produce maintainable code by reusing existing capabilities instead of recreating them.
- Agents are guided to use built-in dlt and dltHub capabilities (e.g. authentication, REST client) rather than reimplementing common patterns.

### **3. Built-in guardrails and agent control via human-in-the-loop**

An AI-native data platform must ensure that AI-assisted development remains observable, controllable, and safe. dltHub is designed for iterative development, where developers can inspect intermediate results, guide the next step, and validate outcomes continuously.

The challenge with agentic coding is not only producing an initial implementation, but ensuring that the result is maintainable, secure, aligned with best practices, and easy to review and verify. This requires both human oversight and product guardrails.

**In practice - examples:**

- AI workbench workflows provide clear entry point instructions and structure for agents.
- AI workbenhc toolkits are designed for iterative development with clear checkpoints for human review (e.g. local development → code review → local test run with a small sample → inspect pipeline → prepare for deployment → deploy)
- Developers can inspect generated code, outputs, logs, and traces throughout the process - AI agents are instructed to stop and ask users for input at predefined points in the development process (e.g. run ingestion pipeline first on a sample of data before doing the full load).
- Deterministic tooling is used where probabilistic approaches are not reliable enough, such as secrets handling (e.g. CLI provides redacted secrets command).
- Data and metadata are separated so that agents can do most of their work using metadata, without unnecessary access to sensitive data.
- Isolated and ephemeral workspace sandboxes.