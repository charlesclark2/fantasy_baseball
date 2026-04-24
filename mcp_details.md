# Agentic Engineering Enablement

This document makes the case for enabling agentic AI tooling — specifically Snowflake Cortex Code and Claude Code — for data engineering and analytics teams. It covers what agentic engineering is, why it matters for our domain, the evidence base behind it, concrete use cases, a rollout strategy, and the full technical and security architecture for a safe enterprise deployment.

---

## Table of Contents


**Part I — Understanding Agentic Engineering**
1. [What is Agentic Engineering?](#1-what-is-agentic-engineering)
2. [How a coding agent works](#2-how-a-coding-agent-works)
3. [Product overview: Claude Code and Snowflake Cortex Code](#3-product-overview-claude-code-and-snowflake-cortex-code)

**Part II — The case for adoption**
4. [Research evidence and industry adoption](#4-research-evidence-and-industry-adoption)
5. [Agentic engineering use cases in data](#5-agentic-engineering-use-cases-in-data)
6. [Why MCP fits Data Engineering and Analytics roles](#6-why-mcp-fits-data-engineering-and-analytics-roles)
7. [Benefits of MCP-enabled LLM clients](#7-benefits-of-mcp-enabled-llm-clients)

**Part III — Strategy and options**
8. [Enablement overview: strategy, use cases, and rollout](#8-enablement-overview-strategy-use-cases-and-rollout)
9. [Cost and licensing](#9-cost-and-licensing)

**Part IV — Implementation and security**
10. [Setup: Snowflake MCP and dbt MCP in Claude Code](#10-setup-snowflake-mcp-and-dbt-mcp-in-claude-code)
11. [Extending to Snowflake Cortex Code](#11-extending-to-snowflake-cortex-code)
12. [Building a custom enterprise MCP server with FastMCP](#12-building-a-custom-enterprise-mcp-server-with-fastmcp)
13. [Corporate security considerations](#13-corporate-security-considerations)
14. [EC2-based development environments (CyberArk)](#14-ec2-based-development-environments-cyberark)
15. [Requirements to delivery: Plan Spec and the AI-assisted SDLC](#15-requirements-to-delivery-plan-spec-and-the-ai-assisted-sdlc)
16. [Agentic engineering in CI/CD](#16-agentic-engineering-in-cicd)
17. [Best practices for agentic engineering](#17-best-practices-for-agentic-engineering)

---

## 1. What is Agentic Engineering?

### Agentic AI vs. autocomplete

Most engineers have encountered AI code assistants in their simplest form: a model that predicts the next few tokens and inserts a suggestion inline. That is useful, but it is not agentic. **Agentic engineering** is the practice of using AI systems that reason across multiple steps — reading files, querying databases, running tools, evaluating results, correcting errors — and produce finished work with minimal manual interruption at each step.

The distinction matters because the bottleneck in data engineering is rarely typing speed. It is reasoning: understanding what a source table contains, tracing why a number changed, designing a fact table that conforms to an enterprise dimension, writing tests that actually catch the right edge cases. An agentic assistant can hold the full context of a problem, call the tools needed to gather evidence, and reason toward a solution — the same cognitive loop a senior engineer runs, but available on demand.

### Agentic engineering vs. "vibe coding"

A term that has emerged in the industry — "vibe coding" — describes the opposite of disciplined agentic engineering. In ["The Agentic Engineering Playbook"](https://kotrotsos.medium.com/the-agentic-engineering-playbook-546ad65f0cc5), Marco Kotrotsos (drawing on Peter Steinberger's experience building OpenClaw largely solo in approximately three months, discussed on the Lex Fridman podcast) contrasts the two approaches directly: vibe coding is unstructured prompting where the engineer hopes the model figures out the solution independently; agentic engineering is the deliberate, intentional guidance of AI agents toward predetermined outcomes.

Arnaud Gelas extends this framing in ["The Agentic Engineering Manifesto: Six Values for a Post-Agile World"](https://medium.com/@arnaud.gelas/the-agentic-engineering-manifesto-six-values-for-a-post-agile-world-ec5c9f20bf6f), defining agentic engineering as "the discipline of architecting environments and feedback loops where autonomous agents can safely plan, execute, and verify work under human oversight." This is a distinct practice from AI engineering, prompt engineering, and AI-assisted coding — it requires its own principles, governance patterns, and definition of done.

The separation matters in enterprise contexts. An unstructured "just ask the AI" approach may produce working output in a demo, but fails at scale because it lacks reproducibility, auditability, and guardrails. Agentic engineering treats the agent as a capable but supervised system — one that operates within defined boundaries, produces verifiable evidence of its work, and remains under human governance throughout.

### MCP as the access-scoping mechanism

For agentic AI to be safe in an enterprise environment, it must be impossible for the agent to exceed the access it was explicitly granted. The **Model Context Protocol (MCP)**, an open standard published by Anthropic in November 2024, is the mechanism that enforces those boundaries.

MCP defines a structured interface between an LLM client and external systems. Instead of giving an AI agent unrestricted access to a database or file system, MCP exposes a curated set of named tools — each with a defined schema and permission scope. The agent can only call the tools that have been configured; it cannot construct arbitrary operations outside that set. In the context of this deployment:

- **Snowflake MCP** exposes `SELECT`, `DESCRIBE`, `SHOW`, and `USE` — read-only data access. No writes, no DDL, no admin operations.
- **dbt MCP** exposes model listing, lineage traversal, and column details from the local project manifest — no ability to build, run, or test models.
- The **LLM client** (Claude Code) receives tool results and incorporates them into its reasoning. It cannot bypass the MCP boundary to call Snowflake directly.

| MCP Component | Role |
|---|---|
| **MCP Server** | Wraps an existing system (Snowflake, dbt, a file system) and exposes a curated set of tools. Runs as a local subprocess or remote service. |
| **MCP Client** | The LLM client (e.g. Claude Code). Discovers available tools, decides when to call them, and incorporates results into its reasoning chain. |
| **Transport** | How client and server communicate — stdio (subprocess) for local servers, HTTP/SSE for remote. |

### Architecture: Client → MCP → Snowflake

The diagram below shows the full data flow from the developer's environment to Snowflake, with the MCP layer as the enforced boundary between the AI client and the data plane.

```
 ┌──────────────────────────────────────────────────────────────────┐
 │                    Developer Environment                         │
 │              (EC2 via CyberArk  ·  workstation)                 │
 │                                                                  │
 │   ┌────────────────────────────────────────────────────────┐    │
 │   │                    LLM Client                          │    │
 │   │              (Claude Code  ·  VS Code)                 │◄───┼──► api.anthropic.com
 │   └──────────────────────────┬─────────────────────────────┘    │    (HTTPS outbound —
 │                              │ stdio (subprocess)                │     model inference)
 │   ┌──────────────────────────▼─────────────────────────────┐    │
 │   │                    MCP Servers                         │    │
 │   │                                                        │    │
 │   │   ┌──────────────────────┐   ┌───────────────────────┐ │    │
 │   │   │    Snowflake MCP     │   │       dbt MCP         │ │    │
 │   │   │    (read-only)       │   │  (local manifest.json │ │    │
 │   │   │  SELECT  DESCRIBE    │   │   — no network call   │ │    │
 │   │   │  SHOW    USE  only   │   │   required)           │ │    │
 │   │   └──────────┬───────────┘   └───────────────────────┘ │    │
 │   └──────────────┼────────────────────────────────────────-─┘    │
 └──────────────────┼───────────────────────────────────────────────┘
                    │ HTTPS  ·  AWS PrivateLink  (port 443)
        ┌───────────▼────────────────────────────────────────┐
        │                    Snowflake                       │
        │   Auth:   RSA key-pair  ·  AAD External OAuth      │
        │   Authz:  RBAC — AAD Groups → Snowflake Roles      │
        │                                                    │
        │   ┌──────────────────┐   ┌─────────────────────┐   │
        │   │  Source schemas  │   │  IRD / mart schemas  │   │
        │   │  (HVR replicas)  │   │  (dbt-built models)  │   │
        │   └──────────────────┘   └─────────────────────┘   │
        └────────────────────────────────────────────────────┘
```

The key security property of this architecture is that **the LLM never has direct network access to Snowflake**. All data access is intermediated by the MCP server, which enforces the read-only permission set regardless of what the LLM requests. The Snowflake RBAC role provides a second enforcement layer on top of that.

---

## 2. How a coding agent works

Understanding what an agent is actually doing — step by step — helps engineers write better prompts, set realistic expectations, and diagnose problems when the agent goes in the wrong direction. This section explains context derivation, the reasoning-and-tool loop, and how an engineer can actively shape both. Where the behavior differs between **Claude Code** and **Snowflake Cortex Code**, both are called out explicitly.

> For a side-by-side product comparison of Claude Code and Cortex Code, see [Section 3](#3-product-overview-claude-code-and-snowflake-cortex-code).

---

### 2.1 Context: what the agent knows at the start

When you open a conversation with a coding agent, it does not have a pre-built understanding of your project. It starts with whatever context is assembled for it at session startup. The sources differ meaningfully between the two tools:

**Claude Code** builds context from the developer's local environment:

| Context source | What it contributes | Notes |
|---|---|---|
| **System prompt** | Agent persona, behavioral rules, tool permissions, environment facts (OS, shell, date) | Set by the tool; engineers do not write this directly |
| **`CLAUDE.md` files** | Project-level instructions, conventions, known pitfalls, architectural decisions | Written by engineers; loaded automatically from project root |
| **Current working directory** | File and directory names (via `ls`) | Gives the agent a rough map of what exists |
| **Files explicitly read** | Full file contents | Agent reads files on demand during the session |
| **MCP tool results** | Live query results, schema descriptions, dbt model lineage | Pulled on demand when the agent calls a configured MCP tool |
| **Conversation history** | Everything said and returned in the current session | Held in the context window; older turns are compressed as the window fills |

**Snowflake Cortex Code** builds context from within the Snowflake environment:

| Context source | What it contributes | Notes |
|---|---|---|
| **System prompt** | Agent configuration and behavioral rules | Set by Snowflake; not directly editable by engineers |
| **Active Snowflake session** | Current database, schema, warehouse, and role | Always available — no setup required |
| **Snowflake metadata catalog** | Table and column names, data types, object comments | Native access; no MCP or external tool required |
| **Session preamble / semantic model YAML** | An opening context prompt pasted at the start of a CLI session, or a `@semantic_model.yaml` file for persistent metric definitions and business terminology | The closest equivalent to `CLAUDE.md`; must be provided at each session start for the CLI |
| **Highlighted code / selected cells** | The code the engineer has selected or is actively editing (Snowsight/Notebooks); or the SQL/prompt text in the current CLI turn | Snowsight uses selection context automatically; CLI uses what is included in the prompt |
| **Conversation history** | Everything said in the current CLI session or Snowsight session | Resets when the CLI process exits or the Snowsight session ends |

The key structural difference: Claude Code starts with no schema knowledge and builds it via MCP tool calls; Cortex Code always has full schema awareness because it runs inside Snowflake and can query the information schema natively. This makes Cortex Code faster to get started with for pure SQL tasks, but means it has no visibility into files, Python scripts, or dbt models outside the Snowflake environment.

The agent does not read every file or table in the project upfront. Both tools build understanding incrementally — forming a hypothesis about what is relevant, gathering evidence, and refining. The quality of the agent's understanding is directly shaped by how navigable and well-documented the project is.

---

### 2.2 The reasoning-and-tool loop

Once a task is submitted, the agent enters a loop:

```
 ┌─────────────────────────────────────────────────────────┐
 │                      Agent Loop                         │
 │                                                         │
 │   1. REASON  — given current context, what is needed?   │
 │         │                                               │
 │         ▼                                               │
 │   2. PLAN    — decompose the task into sub-steps        │
 │         │                                               │
 │         ▼                                               │
 │   3. ACT     — call a tool (read file, query DB,        │
 │                run shell command, write file)           │
 │         │                                               │
 │         ▼                                               │
 │   4. OBSERVE — receive tool result; add to context      │
 │         │                                               │
 │         ▼                                               │
 │   5. EVALUATE — did the result answer what was needed?  │
 │         │   yes ──► next sub-step (back to step 2)      │
 │         │   no  ──► revise plan (back to step 2)        │
 │         │   done ─► compose final response              │
 └─────────────────────────────────────────────────────────┘
```

Each iteration of this loop consumes context window space — the tool call, its result, and the agent's reasoning are all appended to the running transcript. A complex task (e.g. "trace why this metric changed") may run 15–30 tool calls before producing a response, with the agent progressively narrowing its hypothesis across iterations.

**How planning emerges:** The agent does not execute a hard-coded plan. It generates a step sequence based on the current state of its context, and revises that sequence after each observation. If a file it expected to exist does not, it adjusts. If a query returns unexpected results, it pivots. The plan is always provisional — it reflects the agent's current best guess about how to reach the goal.

**What can go wrong:** If the task description is ambiguous, the agent's initial plan may target the wrong goal entirely. If the relevant files are deeply nested and undiscoverable from the top-level directory listing, the agent may not find them without guidance. If the context window fills (on very long sessions with many tool calls), older turns are compressed and nuance from early in the session may be lost.

---

### 2.3 How the agent decides what tools to call

The agent sees a list of available tools with their names, descriptions, and input schemas. When it needs information, it selects the tool whose description most closely matches what it is trying to accomplish. This means **tool descriptions are load-bearing** — a poorly named or poorly described tool will be underused, while a well-described tool will be reached for reliably.

In the MCP context: the Snowflake MCP tool that runs a query is called something like `run_snowflake_query` with a description explaining it executes read-only SQL. If the agent needs to know what columns are in a table, it will call that tool with `DESCRIBE TABLE ...`. It does not guess — it calls the tool, reads the result, and incorporates that into its reasoning before proceeding.

The agent also infers when it should *not* call a tool. If it has already read a file this session, it will use the version in context rather than re-reading. If a tool result from an earlier step answers the current sub-question, it will reuse that rather than calling again.

---

### 2.4 What an engineer can do to scope the agent better

This is the most practical subsection for day-to-day use. The agent's output quality scales directly with the quality of the scaffolding around it. Each technique is described for both Claude Code and Cortex Code where behavior differs.

---

#### Provide project-level standing instructions

The single highest-leverage investment in either tool is giving the agent persistent, project-scoped instructions so it does not need to rediscover conventions on every session.

**Claude Code — `CLAUDE.md` file**

Claude Code automatically reads any `CLAUDE.md` file in the project root (and in nested directories for subdirectory-specific context). This is the primary mechanism for standing instructions. High-value contents:

- **Tech stack facts** that are non-obvious from file names (e.g. "this project uses dbt-fusion — run `dbtf`, not `dbt`")
- **Naming conventions** (schemas, table prefixes, column suffixes)
- **Known pitfalls** ("never modify `raw_` prefixed tables — they are managed by HVR replication")
- **Architectural constraints** ("all fact tables must join to `dim_date` using `game_date_key`")
- **What to avoid** ("do not add comments describing what the code does; only add comments for non-obvious WHY")

The agent treats `CLAUDE.md` instructions as authoritative and applies them consistently throughout the session. One well-written `CLAUDE.md` improves every subsequent agent interaction in the project.

**Cortex Code — session preamble and semantic model YAML**

Cortex Code does not have a file-based equivalent of `CLAUDE.md` that loads automatically. The practical approach depends on which interface you are using:

- **CLI (`cortex`):** Open each session with a short context prompt that states the current database, schema conventions, naming standards, and any constraints the agent must follow. This takes about 30 seconds and re-establishes the same standing context every time. Maintain a team-standard "session preamble" as a text snippet or shell alias so engineers are not writing this from scratch.
- **Snowsight / Snowflake Notebooks:** A markdown cell pinned at the top of the notebook serves as the session preamble. Keeping it visible and referencing it at the start of a session gives the agent the same standing context. Establish a standard preamble template across team notebooks.

For both interfaces, the **Cortex Analyst semantic model YAML** plays the most durable role: it permanently encodes metric definitions, column descriptions, join logic, and business terminology at the Snowflake level. Reference it in the CLI via `@models/semantic_model.yaml` syntax. This is the closest thing to a persistent, automatically-loaded context — it does not reset between sessions.

The key difference from `CLAUDE.md`: Claude Code's file loads automatically at every session start; Cortex Code's context must be re-established manually each session (CLI or Notebooks), unless the semantic model YAML covers the relevant domain. For a team-wide deployment, a shared preamble snippet + a well-maintained semantic model YAML is the Cortex Code equivalent of a shared `CLAUDE.md`.

**The project context file: persistent working memory**

Standing instructions in `CLAUDE.md` handle *how* the agent should behave. A separate concern is making sure the agent always knows *what has been built, where things stand, and why decisions were made* — knowledge that evolves sprint-to-sprint and cannot be derived from file names or schema structure alone.

Ayesha Mughal, writing in "The Agentic Engineering Stack — 4 Tools, One System, Nothing Else" (AI in Plain English, 2026), identifies this as the critical gap in agentic workflows: "Every time you start a session, the agent is like a new software engineer who has never seen your codebase." Her solution is a dedicated `.ai/memory.md` file that tracks current sprint state, architecture decisions, and project-specific conventions — turning "a series of stateless conversations into a continuously evolving knowledge base."

In this project, `project_context.md` serves this exact role. It records:

- The current phase and what has been completed vs. what is still planned
- Canonical join keys and why those specific identifiers were chosen
- Data source coverage windows and known data quality caveats
- Feature store row counts and validated training window boundaries
- Model inventory with grain, key, and dependency documentation

Any agent — Claude Code or otherwise — that reads `project_context.md` at the start of a session immediately knows what a senior team member would know after a full onboarding. This is referenced in the project's `CLAUDE.md` so that Claude Code loads it automatically; for Cortex Code (CLI or Snowsight), pasting the relevant sections as the opening message of each session achieves the same effect.

The practical pattern for any project is to maintain two separate files with distinct responsibilities:

| File | Contains | Update cadence |
|---|---|---|
| `CLAUDE.md` / session preamble snippet | Behavioral rules, naming conventions, tools to use/avoid, what not to do | Rarely — when conventions change |
| `project_context.md` / `.ai/memory.md` | Current sprint status, architecture decisions, completed work, known issues | Each sprint or after major milestones |

The working memory file is especially valuable at the start of new sessions and when onboarding a new engineer: rather than re-explaining the project from scratch, the agent (and the human) can read a single document and start contributing immediately.

---

#### Be specific in the initial prompt

Both tools plan from the task description they receive. Vague descriptions produce broad, expensive behavior — the agent searches widely before narrowing. Specific descriptions produce targeted, efficient execution.

| Vague | Specific |
|---|---|
| "Why is the revenue number wrong?" | "The `mart_daily_premium` model is showing $2M higher than the finance report for 2025-Q4. The finance report uses `policy_effective_date`; check whether our model uses `transaction_date` instead and fix if so." |
| "Add a test to this model" | "Add a `not_null` and `unique` dbt test to the `policy_id` column in `mart_policy_facts.sql`." |
| "Clean up this SQL" | "Reformat `mart_batter_rolling_stats.sql` to use CTEs instead of nested subqueries. Keep column names and logic identical — structural cleanup only." |

The agent can handle vague prompts — it will ask clarifying questions or make assumptions that may not match your intent. Front-loading specificity saves iteration cycles in both tools.

**Cortex Code note:** Because Cortex Code always has full schema awareness natively, schema-related vagueness matters less ("query the revenue table" will be interpreted correctly). Business logic vagueness ("why is the number wrong?") is just as expensive to recover from as it is in Claude Code — the agent still needs to know *which* number, *which* report, and *what the expected behavior is*.

---

#### Reference specific objects directly

Telling the agent exactly which object to look at eliminates the search phase and focuses its reasoning immediately.

**Claude Code:** Reference files with `@filename` in the VS Code extension, or paste the full path directly into the chat. Include line numbers when the issue is localized ("the filter at line 47 of `stg_policy.sql`"). The agent jumps directly to reading that file rather than scanning the directory tree.

**Cortex Code:** Reference tables using fully qualified names (`DATABASE.SCHEMA.TABLE_NAME`). Paste the output of `DESCRIBE TABLE` or `SHOW COLUMNS` directly into the chat when the issue involves specific columns. In the CLI, include the object reference inline in your prompt ("Look at `IRD_MART.FACT_DAILY_PREMIUM`..."); in Snowsight or Snowflake Notebooks, highlighting a cell or block of SQL before prompting focuses the agent on that selection automatically. If the issue spans multiple objects, list them explicitly: "Look at `IRD_MART.FACT_DAILY_PREMIUM` and `IRD_MART.DIM_POLICY`. The join between them on `policy_id` is returning more rows than expected."

---

#### Use follow-up corrections actively

Both tools revise their plan immediately based on feedback. A short correction after a wrong first response re-grounds subsequent reasoning without needing to re-explain the full task.

> "That's the wrong table — I meant `mart_daily_premium`, not `stg_policy`."

> "Stop. The issue is in the aggregation, not the join. The join is correct."

Corrections are additive: the agent incorporates them into its current context and adjusts from that point forward. Do not restart the session for a correction — redirect instead. This is identical in behavior for both Claude Code and Cortex Code.

---

#### Constrain the scope explicitly

Without a scope constraint, the agent may identify related issues in adjacent objects and proactively address them — which is sometimes useful and sometimes unwanted.

**Claude Code:** Scope by file or directory:

> "Only modify `mart_batter_rolling_stats.sql`. Do not change any other files."

> "Do not touch any staging models. Only work within `dbt/models/mart/`."

**Cortex Code:** Scope by schema or object:

> "Only query the `IRD_MART` schema. Do not join to any tables outside that schema."

> "The fix should be in the `FACT_DAILY_PREMIUM` view only. Do not modify `DIM_POLICY`."

Explicit scope constraints are honored reliably by both tools. They are especially important in Cortex Code when working in a multi-schema Snowflake account where the agent has full catalog visibility and might suggest joins to tables in schemas the engineer does not own or intend to use.

---

#### Break large tasks across sessions

The context window is finite in both tools. For large tasks — building a new multi-model mart, investigating a data quality issue across many tables, redesigning a schema — breaking the work into sequential sessions prevents context window compression from degrading reasoning quality.

**Claude Code:** When context window pressure builds, use the `/compact` command to compress older turns before the client is forced to do it automatically (which happens at the worst moment, mid-task). End each session by asking the agent to write a handoff summary; use that summary as the first message of the next session.

**Cortex Code:** Context resets when the CLI process exits or the Snowsight session ends. There is no equivalent of `/compact`. For the CLI, the practical approach is to work in focused, single-topic sessions and to note progress in `project_context.md` or a brief markdown summary before exiting. Starting the next session with a short recap (pasted as the opening message) re-establishes context efficiently. The CLI's terminal-native workflow makes this slightly faster than the Snowflake Notebooks approach — there is no browser tab to close, no kernel restart to wait for.

---

### 2.5 Summary: the mental model

Think of a coding agent as a very capable but initially uninformed colleague who reads fast and never forgets anything said in the current conversation. It:

- Starts with only what you tell it and what it can discover by looking around
- Builds understanding through rapid, sequential tool calls
- Plans dynamically, revising after each observation
- Follows explicit instructions reliably when given
- Drifts toward plausible-but-wrong interpretations when instructions are vague

Your job as the engineer is to reduce the ambiguity in its starting context and redirect it quickly when it heads in the wrong direction. The loop is fast — each correction compounds.

The tool you are using changes *where* the starting context comes from — Claude Code builds it from local files and MCP tool calls; Cortex Code builds it from the live Snowflake catalog — but the fundamental dynamic is the same: specific instructions produce better output than vague ones, and the agent's reasoning is only as good as the context it has been given.

---

## 3. Product overview: Claude Code and Snowflake Cortex Code

This section provides a standalone overview of each product and a structured comparison across the dimensions most relevant to the IRD pilot. The goal is to support the tool selection decision without presuming a winner — the right answer depends on team workflow, existing infrastructure, and the specific use cases prioritized in the pilot.

---

### 3.1 Claude Code

**What it is**

Claude Code is an agentic software engineering tool developed by Anthropic. It runs as a CLI and as a VS Code extension, operating directly in the engineer's development environment. It uses Claude (Anthropic's LLM) as its reasoning engine and can take actions across the full development stack: reading and writing files, running shell commands, querying databases via MCP, and executing multi-step tasks with minimal manual interruption at each step.

It is not a chat interface with a code completion sidebar. It is an agent that reasons, plans, calls tools, and produces finished work — the difference is the same as asking a colleague to "help me understand this" versus asking them to "build this and come back when it's done."

**Where it runs**

Claude Code runs on the engineer's machine — in this deployment, on the EC2 instance accessed via CyberArk. It has access to the local filesystem, the local shell, and any MCP servers configured for the project (Snowflake MCP, dbt MCP). All reasoning happens via the Anthropic API (`api.anthropic.com`); data results from tool calls stay within the development environment and are not sent to Anthropic beyond what is included in the conversation.

**What it can do**

- Read and write any file in the project (SQL, Python, YAML, Markdown, shell scripts)
- Run shell commands (dbtf compile, dbtf test, Python scripts, git operations)
- Query Snowflake via the Snowflake MCP server (read-only: SELECT, DESCRIBE, SHOW, USE)
- Traverse dbt lineage, column lineage, and model metadata via the dbt MCP server
- Reason across multiple files and query results in a single conversational session
- Generate, review, refactor, and test code across the full project structure

**What it cannot do (by design in this configuration)**

- Write to Snowflake (MCP is read-only; no INSERT, UPDATE, DELETE, DDL)
- Modify or run dbt builds (dbt MCP has build/run/test excluded from the allowlist)
- Access systems that do not have a configured MCP server
- Persist memory between sessions (each session starts fresh, except for `CLAUDE.md`)

**Access model**

Requires an Anthropic Team or Enterprise plan subscription per seat. The subscription covers the Claude Code CLI, VS Code extension, and the full Claude.ai web interface. No per-API-call billing for plan subscribers — usage is covered within the monthly seat allocation.

**Best suited for**

- Data engineers working across the full project (dbt models, Python ingestion scripts, schema design, testing)
- Complex multi-step tasks that span SQL, Python, and YAML in the same session
- dbt-integrated work where local manifest access is a strong advantage
- Engineers already using VS Code and a command-line-centric workflow

---

### 3.2 Snowflake Cortex Code

**What it is**

Snowflake Cortex Code is an AI-assisted coding and analytics tool built natively into the Snowflake platform. It is part of the broader Cortex AI suite — which also includes Cortex Analyst (natural-language-to-SQL via a semantic layer), Cortex Search (enterprise search), and Cortex LLM functions (SQL-callable inference). Cortex Code accepts natural language requests and orchestrates Snowflake operations in response: catalog discovery, SQL generation, data exploration, and application scaffolding. It displays its reasoning steps and actions as it works.

Because it runs within the Snowflake ecosystem, it has native, always-available access to the Snowflake metadata catalog — no MCP configuration or external tool setup is required to get schema-aware SQL generation.

**Where it runs**

Cortex Code supports three interfaces:

1. **CLI (`cortex`)** — A terminal-based agent installed locally (`curl -LsS https://ai.snowflake.com/static/cc-scripts/install.sh | sh`). Engineers run `cortex` from any terminal (macOS, Linux, WSL, Windows) and interact via natural language, with results and reasoning displayed inline. Connections are stored in `~/.snowflake/connections.toml` (shared with Snowflake CLI). This is the most Claude-Code-like interaction model and is the interface recommended for engineering workflows.
2. **Snowsight (web UI)** — Inline AI assistance in the Snowflake browser UI. Useful for quick queries, table exploration, and ad-hoc SQL generation within the browser.
3. **Snowflake Notebooks** — AI assistance embedded within notebook cells. Code suggestions and natural language interactions are available inline without leaving the notebook environment.

All three interfaces operate within the Snowflake environment boundary: they do not have access to the engineer's local filesystem, the local dbt project directory, or any systems outside the Snowflake account.

**What it can do**

- Accept natural language requests in the terminal (CLI) or inline (Snowsight, Notebooks) and orchestrate multi-step Snowflake operations in response
- Discover and explore the Snowflake catalog: databases, schemas, tables, columns, tags — "What databases do I have access to?" or "List every table tagged PII = TRUE"
- Generate and run SQL — "Write a query for the top 10 customers by revenue" or "Write an optimized version of this query"
- Natively access the full Snowflake metadata catalog without any external setup or MCP configuration
- Leverage Cortex Analyst semantic models for natural-language-to-SQL over defined metric layers (`@models/semantic_model.yaml` syntax in CLI)
- Build Streamlit applications from natural language descriptions — "Build a Streamlit dashboard on SALES_MART.REVENUE"
- Call Cortex LLM functions directly within SQL queries (e.g. `SNOWFLAKE.CORTEX.COMPLETE()`)
- Switch between available models mid-session using the `/model` command
- Operate within the engineer's existing Snowflake RBAC role — no additional access grants required

**What it cannot do (by design)**

- Access files on the local filesystem (no dbt project directory, no Python scripts outside Snowflake)
- Read dbt `manifest.json` without it first being uploaded to a Snowflake stage via CI/CD
- Run shell commands, git operations, or interact with on-premises systems outside the Snowflake account
- Persist context automatically across sessions — each CLI invocation or Snowsight session starts fresh

**Access model**

Cortex AI features (including Cortex Code) are available on Snowflake Enterprise Edition and above, in supported regions. There is no per-seat license for Cortex Code itself — access is part of the Snowflake edition. The CLI requires the `SNOWFLAKE.CORTEX_USER` database role. Usage is billed via Snowflake credit consumption at a rate that varies by the underlying LLM model selected. Check the [Snowflake Service Consumption Table](https://www.snowflake.com/legal-files/CreditConsumptionTable.pdf) for current per-token credit rates.

**Best suited for**

- Data engineers and analysts who prefer a terminal-native workflow but want Snowflake-native schema awareness without MCP setup (CLI interface)
- SQL-focused tasks (writing queries, debugging results, generating aggregations) where full Snowflake catalog awareness is a strong advantage
- Self-service analytics use cases where non-engineers need to query data without writing SQL themselves (Cortex Analyst via Snowsight)
- Teams who want a lighter-weight setup compared to Claude Code for Snowflake-only work

---

### 3.3 Head-to-head comparison

| Dimension | Claude Code | Snowflake Cortex Code |
|---|---|---|
| **Where it runs** | Developer environment (EC2, laptop) via CLI + VS Code | Terminal CLI (`cortex`), Snowsight web UI, or Snowflake Notebooks — all Snowflake-scoped |
| **Schema awareness** | Via Snowflake MCP — requires configuration; always current after setup | Native — full catalog access with no configuration required |
| **Local file access** | Full — reads/writes any file on the developer's machine | None — Snowflake objects only |
| **dbt integration** | Via dbt MCP — reads local `manifest.json`; no pipeline needed | Requires `manifest.json` uploaded to a Snowflake stage via CI/CD pipeline |
| **On-premises GitLab** | Strongly preferred — no external pull required | Requires a push pipeline from on-prem GitLab to Snowflake (network egress, credential management) |
| **Python / shell support** | Full — any Python script, shell command, git operation | Python within Snowflake (Notebooks or Snowpark); no local shell access |
| **Multi-step agentic reasoning** | Full — can chain dozens of tool calls across files, queries, and shell in one session | CLI and Snowsight support multi-step reasoning within Snowflake scope; no cross-file or local-shell agentic loop |
| **MCP extensibility** | Full MCP client — any MCP server can be added | Emerging — Snowflake MCP client support is being developed |
| **Cost model** | Per-seat subscription (predictable, flat) | Credit-per-token consumption (variable, usage-dependent) |
| **10-seat pilot cost estimate** | ~$2,400/year (Team Standard, annual) | Variable — depends on usage volume and model tier |
| **Auth / access control** | RSA key-pair + Snowflake RBAC role (service account) | Engineer's existing Snowflake RBAC role — no additional grants needed |
| **Setup complexity** | Moderate — MCP server config, `.mcp.json`, RSA key | Low — CLI install is one `curl` command; auth via `~/.snowflake/connections.toml` |
| **Data residency** | Query results stay in dev environment; prompts sent to `api.anthropic.com` | Fully within Snowflake — no data leaves the account |
| **Primary audience** | Data Engineers (full-stack dev workflows, local files + Snowflake in one session) | Data Engineers and Analysts wanting Snowflake-native agentic workflows via CLI or Snowsight |

---

### 3.4 Which tool for which use case

These are not mutually exclusive — most enterprise teams end up using both in complementary roles. The decision for the IRD pilot is about which to prioritize and validate first.

| Use case | Recommended tool | Reason |
|---|---|---|
| Build a new dbt mart model | Claude Code | Needs local file access, dbt MCP for lineage, and the ability to write YAML, SQL, and run compile checks |
| Investigate a data quality issue across multiple dbt models | Claude Code | Requires reading multiple files and querying Snowflake in the same session |
| Write an ad-hoc SQL query against Snowflake | Either | Cortex Code has native schema awareness; Claude Code has it via MCP after setup |
| Explain a Snowflake table structure to an analyst | Cortex Code | Native catalog access; no setup; self-contained in Snowsight |
| Write a Snowflake Notebook or Streamlit report | Cortex Code | Native Snowflake experience; CLI can scaffold a Streamlit app from a natural language description |
| Business analyst self-service queries | Cortex Analyst | Semantic-layer-driven NL-to-SQL; designed for non-engineering users |
| Refactor a Python ingestion script | Claude Code | Requires file system access and shell execution — outside Snowflake's scope |
| Trace lineage for a schema migration | Claude Code | dbt MCP provides instant local lineage; Cortex requires CI/CD pipeline for same |
| Review and test a pull request | Claude Code | Requires git access, file diffing, and CI/CD integration |

**Recommendation for the IRD pilot:** Start with Claude Code for the engineering cohort. The dbt integration via local manifest, the full project file access, and the ability to work across Python and SQL in one session are concrete advantages for DE/DA workflows that are validated by this project. Evaluate Cortex Code in parallel for analyst-facing use cases — particularly Cortex Analyst for self-service SQL — where Snowflake-native access removes friction for non-engineers. The two tools solve different parts of the problem and are best positioned as complementary rather than competing choices.
## 4. Research evidence and industry adoption

The case for AI-assisted engineering is not anecdotal. A growing body of research — from randomized controlled trials to large-scale industry surveys — demonstrates consistent, measurable productivity gains across engineering roles. The data engineering domain is early in this adoption curve, which means the teams that instrument and learn from AI tooling now will have a structural advantage as the evidence base matures.

### McKinsey identifies agentic engineering as a strategic imperative

In their AI Transformation Manifesto, McKinsey identifies mastering agentic engineering as **Theme #11** — a capability they argue separates companies that will win from those that will fall behind. The economic projections are significant: a **20% EBITDA uplift potential**, a **$3 return per $1 invested**, and breakeven within two years for organizations that adopt agentic engineering at scale.

Arnaud Gelas, writing in ["McKinsey Says Master Agentic Engineering. Here's What That Actually Requires."](https://medium.com/@arnaud.gelas/mckinsey-says-master-agentic-engineering-heres-what-that-actually-requires-80654f38e961) (Medium, April 2026), acknowledges the business case while arguing that McKinsey's treatment underspecifies the engineering discipline required to realize it. Gelas introduces what he calls the **Agentic Loop** — the full lifecycle an engineering team must operate through: **Specify → Execute → Verify → Validate → Observe → Learn → Govern → Repeat**. Each phase feeds back into the previous ones based on evidence; shipping after Execute without completing Verify and Validate is where teams fail.

Gelas identifies five critical engineering gaps that McKinsey does not address — each directly relevant to a data engineering team:

1. **Verification vs. validation** — the SWE-CI benchmark found that most evaluated models introduced regressions on more than 75% of long-horizon maintenance tasks. Agent-generated code without an independent verification step is a liability, not a shortcut.
2. **Blast radius management** — agents fail at machine speed across connected systems when given incorrect context. In a data pipeline, a wrong assumption about a join key propagates downstream before anyone notices.
3. **Memory governance** — distinguishing learned project knowledge from session context prevents unexplained behavioral drift as agents accumulate history across sessions.
4. **Correlated failure in multi-agent systems** — systems built on identical models and knowledge bases tend to fail simultaneously and in the same direction, eliminating the diversity that normally catches errors.
5. **Spectrum-based autonomy governance** — binary allow/deny trust models are insufficient; tiered autonomy levels should be defined as infrastructure policy, not embedded in individual prompts.

The competitive advantage McKinsey identifies is not access to tools — every organization will eventually have access to the same LLMs and MCP servers. The advantage is **speed to learn: the ability to move from hypothesis to evidence to adjusted behavior faster than the competition.** That is an engineering discipline problem, and engineering discipline compounds.

> Gartner separately projects that 40% of AI projects will face cancellation — reinforcing that access to tools is not the differentiator. Discipline in how they are deployed is.

### Peer-reviewed and rigorous research

**Peng, Kalliamvakou, Cihon, and Demirer (2023) — "The Impact of AI on Developer Productivity: Evidence from GitHub Copilot"** (SSRN Working Paper 4375403) is the most rigorous published study to date. The researchers ran a pre-registered randomized controlled experiment with 95 professional software developers completing a JavaScript task in a controlled environment. Developers using GitHub Copilot completed the task **55.8% faster** than the control group. Critically, this was not a self-reported measure — it was a timed completion rate from an RCT, which controls for selection bias and experience effects. The effect size held across developers at different skill levels.

**Brynjolfsson, Li, and Raymond (2023) — "Generative AI at Work"** (NBER Working Paper 31161) studied the impact of a generative AI coding assistant at a large technology company's customer support operation. Agents using the AI tool saw **a 14% average increase in issues resolved per hour**, with the largest gains concentrated among newer, less experienced employees — suggesting AI assistance is particularly high-leverage for accelerating ramp time on unfamiliar systems.

**McKinsey Global Institute (2023) — "The economic potential of generative AI: The next productivity frontier"** is an industry report (not peer-reviewed, but based on extensive practitioner surveys and modeling). McKinsey estimated that software development is among the functions with the highest potential for AI-driven productivity gain, projecting meaningful acceleration in code generation, documentation, and testing tasks. They note that the gains compound: faster initial delivery also reduces the downstream cost of defects found late.

### What the evidence implies for data engineering

The published studies focus primarily on software developers writing application code. Data engineering shares the core bottleneck — understanding an existing system deeply enough to extend it correctly — but adds domain-specific complexity: schema ambiguity, lineage opacity, business rule translation, and cross-system data quality. The implication is that **the gains observed in general software engineering are a floor, not a ceiling, for data engineering**, because the AI's ability to query live schemas and trace lineage removes friction that general-purpose code assistants cannot address.

### Industry adoption patterns

GitHub's published usage data indicates that by 2024, GitHub Copilot had been adopted by more than 50,000 organizations, with the fastest-growing adoption segment being data and analytics teams using it for SQL and Python work — a use case that was not the original design target but emerged organically as engineers found it effective for schema-heavy tasks.

Snowflake, dbt Labs, and Databricks have each published customer case studies describing accelerated delivery of data models, reduced onboarding time for new engineers on complex data assets, and improved documentation coverage when AI tools are introduced into the development workflow. These are vendor-reported findings and should be weighted accordingly, but the consistency of the pattern across independent platforms is notable.

The most relevant evidence for this team is the project described in Section 5 — a direct, verifiable case study of what one engineer can deliver in a compressed timeline with agentic tooling.

---

### The death of traditional ETL: what the data engineering industry is saying

Rotimi Ademola's widely-cited industry analysis ["The Death of Traditional ETL: How AI Agents Are Rewriting Data Engineering"](https://medium.com/@arrufus/the-death-of-traditional-etl-how-ai-agents-are-rewriting-data-engineering-1b3a6e8c7ce5) articulates the structural pressure this shift is creating for data teams and provides concrete production evidence from companies already operating at this level.

The core argument is that the traditional model — where extract, transform, load work was manually orchestrated and pipeline failures were handled reactively — functioned when data changed infrequently and pipeline counts were modest. Modern data environments have broken those assumptions. Ademola cites Informatica data showing that **data teams already spend up to 40% of their time on data quality tasks alone** — work that compounds in cost as pipeline volume grows.

The evidence from production deployments is concrete:

- **Advisor360°** replaced manual Python models with a Snowflake Cortex AI pipeline that was completed in **two days rather than weeks**, saving a senior data scientist a full day monthly at **5% of the previous cost**. This is a direct precedent for the kind of Snowflake-native AI tooling being evaluated for this pilot.
- **RBC Capital Markets** deployed an agentic system (Aiden QuickTakes, built on Databricks) that reduced equity research turnaround times by **20–60%**, enabling coverage expansion from 1,500 to 2,500 firms without a proportional increase in headcount.
- **Alberta Health Services** implemented an AI scribe application that increased emergency department patient throughput by **10–15% per hour** across 6,700+ clinical sessions at 10 facilities — demonstrating that the productivity gains extend into regulated, high-stakes environments, not just greenfield tech companies.

Databricks reports that **over 80% of new databases are now AI agent-created** (up from 30% annually), and Gartner predicts **40% of enterprise applications will embed task-specific agents by the end of 2026** (versus under 5% in 2025). These are not projections about a distant future — the adoption inflection has already started.

Critically, Ademola addresses the concern that AI agents replace engineers. The argument is the opposite: agents eliminate the work engineers least want to do — "the midnight notifications, the tedious lineage tracing" — and redirect attention toward architectural judgment, data contract design, and orchestration decisions that require human expertise. The emerging role emphasizes designing guardrails for agents and validating their outputs, not competing with them on mechanical tasks.

---

### Agile velocity, competitive advantage, and the strategic case for acting now

The productivity gains above are real, but the strategic implication extends beyond individual task speed. The compounding effect matters more: **moving faster means more iterations per sprint, which means better adherence to agile principles and faster feedback loops from stakeholders.**

In traditional data engineering delivery:
- A BRD goes to development → sprint planning → implementation → review → deployment → stakeholder feedback → next iteration
- Each iteration cycle takes weeks; complex multi-sprint deliveries can absorb months before the stakeholder sees a working result

With agentic engineering:
- Initial scaffolding (staging models, mart skeleton, test suite) is produced in hours, not days
- Stakeholder-facing outputs appear earlier in the sprint, enabling meaningful feedback while there is still time to change course
- The engineer's capacity shifts from writing boilerplate to evaluating results and refining requirements — exactly where agile principles say the value is

The net effect is shorter feedback loops at every stage of the SDLC: between engineer and architect, between team and stakeholder, and between delivery and validated business value.

**The competitive dimension matters independently of the productivity gains.** Data and analytics capabilities are increasingly a source of differentiation across the industry. Teams that can deliver reporting, feature engineering, and self-service analytics faster are better positioned to respond to business needs before the window closes. The question is not whether to adopt agentic tooling, but when — and whether to be an early adopter or a follower.

### SWOT analysis: current state vs. agentic engineering

| | **Strengths** | **Weaknesses** |
|---|---|---|
| **Current (manual) configuration** | Established processes; no new tooling risk; full human review of every line | 40% of time on data quality tasks alone; slow delivery cycles; expert knowledge concentrated in senior engineers; onboarding takes months |
| **Agentic engineering approach** | Dramatically faster delivery; better test coverage; self-service lineage and documentation; agents amplify every engineer's capacity | Requires change management; upfront setup investment; new skills (prompt engineering, agent scoping); cost visibility (consumption-based models) |

| | **Opportunities** | **Threats** |
|---|---|---|
| **Current (manual) configuration** | None specific to tooling; any gains come from process improvement or headcount | Competitors may adopt agentic tooling and deliver faster; talent retention risk if engineers are doing work they find tedious |
| **Agentic engineering approach** | Get to market with AI-accelerated data products before competitors; use faster delivery to run more hypothesis-driven analytics experiments; expand analyst self-service without expanding DE headcount | Industry is moving fast — delayed adoption widens the gap; first-mover advantage is real in tooling adoption curves |

The current engineering configuration is heavily manual: pipeline construction, lineage tracing, data quality investigation, and documentation are all done by engineers against static tooling. This is not a criticism — it is simply the current state of the industry. The SWOT above makes clear that the risk of inaction (falling behind competitors who are adopting these tools) is at least as significant as the risk of adoption (learning curve, change management). The question is when, not whether.

**The opportunity for early movers is real.** Gartner's projection — 40% of enterprise applications embedding task-specific agents by end of 2026 — implies that companies beginning adoption now are doing so during the adoption inflection, not after it. Teams that build competency with agentic tooling in 2025–2026 will have institutional knowledge and working patterns that late adopters will spend years trying to replicate.

---

## 5. Agentic engineering use cases in data

### Core use cases

**End-to-end pipeline generation.** Given a source schema and a description of the desired output, an agent can produce a complete dbt pipeline: staging model with appropriate type-casting and deduplication, mart model with business logic, and a schema YAML with column descriptions and tests. What would take a sprint to scaffold from scratch takes an afternoon to review and refine.

**Multi-step data quality investigation.** When a data quality alert fires, the agent reads the failed test, queries the affected partition to inspect the anomaly, traces the lineage to the upstream source that changed, and drafts an incident summary with root cause and proposed fix — all within a single conversation thread. This collapses a process that typically requires three or four engineers across multiple tools into a single workflow.

**Source table analysis and dimensional modeling.** For a Data Architect working with tables replicated from Db2 or Oracle via HVR, the agent can analyze a set of source tables — reading column names, data types, and sample data — identify the underlying business entities and their relationships, and propose a Star Schema with grain-defined fact tables and conformed dimensions. This is the highest-leverage use of agentic tooling in the data domain: translating normalized operational data into an enterprise reporting model is exactly the kind of multi-context reasoning task that benefits from an AI that can hold the entire source schema in mind at once.

**SQL dialect translation.** Legacy Db2 and Oracle SQL contains constructs that do not translate directly to Snowflake: proprietary date functions, `ROWNUM`-style pagination, `CONNECT BY` hierarchical queries, package-scoped PL/SQL logic. An agent can translate these systematically, flagging constructs that require semantic review rather than mechanical rewriting.

**dbt test generation.** Describe a data quality requirement ("the `order_id` column must be unique within a `game_date` partition") and the agent writes the appropriate dbt test — generic, singular SQL, or a macro call — and places it in the correct schema YAML file. Combined with data profiling, this makes it practical to add test coverage to existing models that were never tested.

**Documentation automation.** An agent can read a dbt model, understand its SQL logic, and generate column-level descriptions and model-level documentation that accurately describe the business meaning — not just the mechanical transformation. This is consistently the task teams deprioritize under delivery pressure; AI makes it a low-marginal-cost addition to every model delivery.

**Self-service analytics for Business Analysts.** A BA asks a question in natural language ("what is the strike rate for left-handed pitchers against left-handed batters in the last two seasons?"). The agent translates the question to SQL using live schema awareness from the Snowflake MCP server, executes the query, and returns a structured result — without the BA needing to know the table names, join conditions, or grain of the underlying data model.

**Onboarding and knowledge transfer.** A new engineer joins a team with a complex dbt project. Rather than reading hundreds of lines of SQL and schema YAML, they ask the agentic assistant: "explain the lineage of `mart_batter_rolling_stats` and describe what each column represents." The agent traverses the manifest, reads the relevant models, and produces a structured explanation in minutes.

### Proof of concept: this project

The most direct evidence available to this team is the project represented in this repository — a baseball betting and fantasy analytics ML platform built by a single engineer using Claude Code as an agentic assistant.

**What was delivered:**
- Full ingestion pipeline integrating four independent data sources: Baseball Savant (Statcast, ~7.5M pitches across 10 seasons), MLB Stats API (schedule, confirmed lineups, probable pitchers), The Odds API (betting markets), and MLB venue data
- 23+ dbt models across staging, mart, and feature layers — including rolling performance statistics at 7-day, 14-day, 30-day, and season-to-date windows for both batters and pitcher metrics
- Handedness-split analysis models (batter vs. pitcher matchup profiles)
- Bullpen workload and effectiveness models
- Ballpark run factor and park context models
- Schedule fatigue and rest context models
- A complete ML feature store with 25,146 game rows covering the 2015–2025 seasons, producing ~23,444 training-ready rows

**The complexity benchmark:** The rolling statistics models alone involve multi-window CTEs, partition-aware aggregations, pitch-level to game-level rollups, and careful handling of data availability windows across 10 years of schema evolution in the source data. The feature store joins all domain models at game-level grain with appropriate temporal constraints to prevent data leakage. This is the kind of feature engineering work that typically requires multiple engineers across multiple sprints.

**What the agentic tooling enabled:**
- Live schema queries during development meant no back-and-forth between the IDE and Snowflake — the agent queried row counts, profiled null rates, and checked join cardinality inline as models were written
- dbt lineage traversal via MCP meant impact analysis was immediate — before changing a staging model, the full set of downstream dependencies was visible without reading the manifest manually
- Data quality issues were diagnosed by the agent querying the affected data, identifying the upstream source of the anomaly, and proposing the fix — compressing what would have been multi-hour debugging sessions
- The full Phase 2 feature store was completed and validated by a single engineer in a timeline that would not have been achievable without agentic assistance

This is not a proof-of-concept in a sandbox — it is a production-quality data asset that will serve as the foundation for ML model development in Phase 3 and beyond.

---

## 6. Why MCP fits Data Engineering and Analytics roles

Data work is fundamentally about understanding the shape and behavior of data — schemas, lineage, distributions, transformations. Historically, that knowledge lived in documentation (stale), in tribal knowledge (siloed), or required manual querying (slow). MCP changes the interaction model:

### For Data Engineers
- Query live table schemas and row counts without leaving the AI interface
- Trace dbt model lineage and understand upstream dependencies on demand
- Generate and validate SQL against the actual warehouse schema, not a static copy
- Debug dbt compilation errors with real column and type information

### For Data Analysts
- Explore datasets conversationally: ask "what does this column represent?" and get an answer grounded in the actual data
- Rapidly prototype queries, then iterate in natural language
- Access dbt model documentation and column descriptions without reading YAML files manually

### For Business Analysts and SMEs
- Ask questions in plain English and receive SQL results, without needing to know the schema upfront
- Validate business logic against real data distributions
- Understand what data is available for a given reporting question before commissioning development work

### The core insight
MCP removes the translation layer between "what the LLM knows" (its training data) and "what the data actually looks like right now" (the live warehouse). The LLM stops hallucinating schema details because it can look them up. The analyst stops copying column names into a chat window because the LLM already has access. This is the same principle as giving a developer a REPL instead of asking them to reason about code from memory.

---

## 7. Benefits of MCP-enabled LLM clients

### Development velocity
Engineers spend a significant fraction of development time on context retrieval — looking up column names, tracing lineage, understanding how a table was populated, reading documentation written by someone who left six months ago. MCP eliminates that round-trip. The LLM looks up the answer against the live system; the engineer sees the result immediately and can continue developing.

### Schema-grounded code generation
SQL and dbt model generation without live schema access produces hallucinated column names, incorrect join keys, and wrong data types — errors that are only caught at execution time. With Snowflake MCP, the LLM queries `SHOW COLUMNS` or `DESCRIBE TABLE` before generating code, producing output that is valid against the actual schema on the first attempt.

### Self-service analytics for non-engineers
Business analysts and SMEs can ask data questions in natural language and receive query results without writing SQL. The Snowflake MCP server handles the connection and execution; the LLM handles the translation. This doesn't replace the data model or the analyst role — it makes the data model more accessible to the people closest to the business questions.

### Lineage and impact analysis on demand
With the dbt MCP server, any team member can ask "what models depend on this source?" or "what's the upstream lineage of this feature?" and receive an accurate answer derived from the current manifest. This is particularly valuable during incident response, schema migrations, and feature audits — situations where understanding blast radius quickly matters.

### Reduced tool-switching
Before MCP, a developer exploring a data question might have: opened Snowsight to check a schema, switched to VS Code to find the dbt model, opened the dbt docs site to read column descriptions, switched back to the SQL editor to write a query, copied the output into a spreadsheet, and finally asked Claude to help interpret it. With MCP, all of those steps happen inside the LLM client in a single conversation thread.

### Consistent, auditable access
Because all Snowflake access through the MCP server is channeled through a single service account with a defined role, DBA teams have a clear, auditable access pattern. There is no ambiguity about which permissions are in use, no risk of an analyst accidentally using an elevated role, and no ad-hoc credential sharing. The MCP layer makes least-privilege practical.

### Comparison: Claude Code vs Snowflake Cortex Code

| Capability | Claude Code + MCP | Snowflake Cortex Code |
|---|---|---|
| Natural-language queries against Snowflake | Yes (via Snowflake MCP) | Yes (native Cortex Analyst) |
| dbt model introspection and lineage | Yes (via dbt MCP — reads local manifest) | Requires manifest.json uploaded to Snowflake via CI/CD |
| Multi-turn conversational reasoning | Yes (full LLM context) | Limited — typically single-turn SQL generation |
| Code generation across the full project (Python, SQL, YAML) | Yes | Primarily SQL within Snowsight |
| Data residency | Depends on Claude deployment model | Fully within Snowflake |
| Extensibility to new tools | Any MCP server | Snowflake ecosystem primarily |
| On-premises GitLab compatibility | Full — no external pull needed | Requires CI/CD push pipeline to Snowflake stage |
| Best fit | Engineering workflows (dbt, Python, multi-step dev) | Analyst self-service within the Snowflake UI |

The two tools are complementary rather than competing in most deployments. However, for teams on **on-premises GitLab**, Claude Code has a concrete structural advantage for dbt-integrated workflows: the dbt MCP server reads `manifest.json` from the local filesystem with no CI/CD pipeline dependency, whereas Cortex Code requires the manifest to be published to a Snowflake stage via a push pipeline from the on-prem runner. If that pipeline cannot be implemented — due to network egress constraints, governance approval timelines, or credential management complexity — Claude Code is the clearly lower-friction choice for dbt lineage and metadata access. See the caveat in [Section 11](#caveat-dbt-manifestjson-delivery-with-on-premises-gitlab) for the full breakdown.

---

## 8. Enablement overview: strategy, use cases, and rollout

This section answers the key questions a team needs to address before enabling AI-assisted development tooling in an enterprise data engineering context.

---

### Q: What do we want enabled?

The preferred outcome is **Claude Code** enabled for engineers — it offers the broadest capabilities across the full development lifecycle (SQL, Python, dbt, shell, file system) and integrates with the existing VS Code + EC2 development environment through the MCP servers documented in this guide.

As a first step within the existing Snowflake environment, **Snowflake Cortex Code** (Snowsight Copilot and Cortex Analyst) can be enabled with no new infrastructure. This provides immediate value for SQL authoring and data exploration within Snowsight without requiring new tooling procurement.

Both can coexist. Cortex Code serves analysts and engineers who work primarily within the Snowflake UI; Claude Code serves engineers who need deeper integration across the full project (dbt models, Python scripts, schema introspection, multi-step reasoning). See [Section 7](#7-benefits-of-mcp-enabled-llm-clients) for a detailed comparison.

---

### Q: How would we enable it?

**Snowflake Cortex Code — Snowflake Admin steps:**

1. **Verify account tier.** Cortex AI features require an Enterprise or Business Critical Snowflake account. Confirm with the Snowflake account team if the current tier qualifies.

2. **Enable Cortex AI at the account level.** An ACCOUNTADMIN executes:
   ```sql
   ALTER ACCOUNT SET ENABLE_CORTEX_AI_SERVICES = TRUE;
   ```

3. **Grant the Cortex user database role** to the target Snowflake roles (e.g. the analyst and engineer roles mapped from AAD groups):
   ```sql
   GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE <engineer_role>;
   GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE <analyst_role>;
   ```

4. **Enable Snowsight Copilot** for the account in Snowsight: Admin → Features → Snowflake Copilot → toggle on. This enables the AI SQL assistant within the Snowsight worksheet editor.

5. **Configure network policy** if the Snowflake account uses Private Link. Cortex AI services route through Snowflake-internal endpoints; no additional outbound firewall rules are required for Cortex itself, but confirm with the Snowflake account team that Cortex service traffic is not blocked by the existing network policy.

6. **Set up usage monitoring.** Cortex AI feature usage consumes Snowflake credits. Configure a resource monitor on the warehouse(s) used during the pilot to cap unexpected consumption:
   ```sql
   CREATE RESOURCE MONITOR cortex_pilot_monitor
     WITH CREDIT_QUOTA = 500
     TRIGGERS ON 75 PERCENT DO NOTIFY
              ON 90 PERCENT DO NOTIFY
              ON 100 PERCENT DO SUSPEND;
   ```

**Claude Code — provisioning steps:**

Procurement of Anthropic API access (API key) or Claude Code team licenses is required. Once provisioned, each engineer configures their EC2 environment per [Section 10](#10-setup-snowflake-mcp-and-dbt-mcp-in-claude-code) and [Section 14](#14-ec2-based-development-environments-cyberark). No Snowflake admin steps are needed beyond what is already configured for the MCP servers.

---

### Q: What will it do?

**For a Data Engineer or SQL developer**, AI-assisted development in Snowflake means:

- **Accelerated query development.** Write or describe the desired output in plain language; the AI generates SQL with awareness of the actual schema. Iterate through corrections and edge cases conversationally rather than cycling through documentation.
- **Data quality evaluation.** Quickly assess a new table: profile null rates, cardinality, value distributions, and referential integrity against related tables — queries that would otherwise take hours to write from scratch.
- **dbt test generation.** Describe a quality requirement; the AI writes the corresponding dbt generic or singular test (e.g. `not_null`, `unique`, `accepted_values`, or a custom SQL test for business rule validation) and places it in the correct schema YAML.
- **Bug identification.** Paste a failing query or a dbt model that produces unexpected results; the AI explains the logic error, points to the specific clause, and proposes a fix with reasoning.
- **Rapid delivery of complex assets.** Transformations that involve multi-level CTEs, window functions, rolling aggregates, or complex join logic — the kinds of tasks that dominate sprint delivery timelines — can be scaffolded quickly and then refined rather than built from a blank page.
- **Code explanation and onboarding.** New team members can ask "what does this model do and why is it structured this way?" and receive an explanation grounded in the actual SQL, reducing onboarding time on unfamiliar parts of the codebase.

**For a Data Architect or Data Modeler** working with source data replicated from Db2 or Oracle via HVR:

HVR ingestion lands source tables in Snowflake as near-exact replicas of the operational schema — normalized, transaction-oriented, and often poorly documented. Translating those tables into enterprise-grade Star Schema models requires understanding the source data, the business process, and the reporting requirements simultaneously. AI assistance changes that workflow materially:

- **Source table analysis.** Point the AI at a set of HVR-replicated staging tables; it reads the column names, data types, relationships (via referential integrity or naming conventions), and sample data, then describes what business process the data represents and how the tables relate to one another.
- **Star Schema proposals.** Given the source tables and a description of the reporting requirements, the AI proposes a dimensional model: candidate fact tables with grain definitions, conformed dimension tables (customer, product, date, etc.), and handling strategies for slowly changing dimensions (SCD Type 1/2/3).
- **DDL generation.** Once the model is agreed upon, the AI generates the full Snowflake DDL for the proposed fact and dimension tables, including column types, clustering keys, and comments.
- **Conformance checking.** For organizations with existing enterprise dimensions, the AI can compare proposed dimension attributes against the established conformed standard and flag gaps or conflicts before development begins.
- **Documentation drafting.** Column-level descriptions, model-level documentation, and dbt schema YAML can be generated from the proposed model, reducing the documentation burden that is often deferred or omitted entirely under delivery pressure.

---

### Q: What will it have access to?

The AI operates within the bounds of the engineer's existing Snowflake session. It can only access schemas, tables, and views that the engineer's current Snowflake role has been granted. There is no privilege escalation — if the role cannot `SELECT` from a table, the AI cannot either.

For MCP-based access (Claude Code), a second enforcement layer is applied via `snowflake_mcp_config.yaml`, which restricts all queries to `SELECT`, `DESCRIBE`, `SHOW`, and `USE`. Write operations (INSERT, UPDATE, DELETE, CREATE, ALTER, DROP) are blocked at the MCP layer regardless of what the underlying role permits. Any DDL or DML that the AI generates must be reviewed and executed explicitly by the engineer.

Access should be provisioned on a principle of least privilege: the pilot cohort receives access to the IRD development schemas and approved source schemas only. Production schema access is not required for development assistance and should not be granted unless a specific read need is identified and approved.

---

### Q: Where should we start?

Begin with a **focused pilot on the IRD modeling team** scoped to a single business process end-to-end. Constraining to one business process allows the team to measure the impact of AI assistance on a known workload — delivery timeline, defect rate, and engineer experience — without the noise of org-wide variation.

Define success criteria before the pilot starts:
- **Velocity:** reduction in time from requirements to delivered, tested dbt model
- **Quality:** defect rate (data quality issues found post-delivery) vs. historical baseline
- **Experience:** end-of-pilot survey (NPS-style) on usefulness, trust in outputs, and time saved
- **Adoption:** percentage of pilot cohort using the tools at least weekly by week 4

---

### Q: Who would start?

The IRD modeling team, spanning the three roles present across the full delivery lifecycle:

| Role | Primary AI use case during pilot |
|---|---|
| **Data Engineer** | dbt model development, SQL generation, test writing, bug diagnosis |
| **Business Analyst** | Data exploration, quality assessment, requirements-to-SQL translation |
| **Data Architect** | Source table analysis, Star Schema proposal, dimensional model documentation |

Starting with all three roles in the same pilot creates cross-functional feedback — the team can observe where AI assistance is strong (code generation, quality testing) vs. where human judgment remains essential (grain definition, business rule interpretation, model governance decisions).

---

### Q: What guardrails should we put in place?

**Access controls:**
- AI tools operate within the engineer's existing Snowflake RBAC grants — no additional permissions granted to the AI itself
- MCP access configured read-only (SELECT, DESCRIBE, SHOW, USE only)
- PII-tagged tables excluded from AI-accessible schemas during the pilot; data classification tags enforced via row access policies

**Code governance:**
- All AI-generated dbt models and SQL undergo the standard peer review process before merge to main
- No AI-generated code promoted to production without a human reviewer sign-off in the pull request
- dbt tests for any AI-generated model are required as part of the PR, not optional

**Usage monitoring:**
- Cortex credit consumption tracked via a dedicated resource monitor with notification thresholds
- AI-originated Snowflake queries identifiable in `QUERY_HISTORY` by session tag or service account prefix
- Monthly review of query volume, credit usage, and any anomalous patterns during the pilot

**People controls:**
- Completion of a responsible AI use training module required before access is provisioned
- Engineers understand that AI outputs require verification — the AI is a productivity accelerator, not an autonomous developer
- A dedicated feedback channel (Slack or ticketing) for reporting unexpected, incorrect, or concerning AI outputs
- Clear escalation path if the AI produces output that accesses or exposes data beyond intended scope

**Output validation:**
- AI-generated SQL is treated as a first draft, not a finished product — the engineer is accountable for correctness
- For Star Schema proposals, a Data Architect sign-off is required before DDL is committed, regardless of whether AI assisted with the design

---

### Q: How would we change over time?

**Phase 1 — IRD pilot (0–3 months):**
Enable Cortex Code and/or Claude Code for the IRD modeling team on a single business process. Collect velocity metrics and survey data throughout. At the end of the pilot, evaluate against the defined success criteria.

**Phase 2 — IRD full rollout (3–6 months):**
If the pilot demonstrates positive velocity gains and favorable survey results, execute a phased rollout to the remaining IRD delivery teams. Apply lessons from the pilot — what use cases drove the most value, which guardrails needed adjustment, what training gaps emerged.

**Phase 3 — Standards and observability (6–9 months):**
Develop a best practices guide covering prompt patterns that work well for dbt and Snowflake SQL development, common failure modes to watch for, and recommended review workflows. Formalize standards around AI-assisted development (e.g. PR checklist requirements, tagging conventions for AI-generated models). Instrument observability tooling to track adoption and quality metrics org-wide.

**Phase 4 — Broader group onboarding (9–12 months):**
Identify the next cohorts — Milo, Risk, Pricing, and other business units — based on expressed interest and readiness. Each new group onboarding requires:
- A tailored training session covering the tooling, guardrails, and appropriate use cases for their domain
- Setup documentation adapted to their environment (different Snowflake roles, different schemas, potentially different development tooling)
- Observability instrumentation specific to their usage patterns
- A designated point of contact within the IRD team to support questions during their ramp period

At each phase transition, revisit the tool selection decision — the landscape for Claude Code, Cortex Code, and competing AI development tools is evolving rapidly. The pilot and subsequent phases generate evidence that should inform procurement and licensing decisions at each renewal or expansion point.

---

## 9. Cost and licensing

### 9.1 Claude Code — Team and Enterprise plans

Claude Code is included in both the Team and Enterprise plans on Claude.ai. As of April 2026:

| Plan | Per-seat cost | Minimum seats | Notes |
|---|---|---|---|
| **Team — Standard** | $20/seat/month (annual) or $25/seat/month (monthly) | 5 | Includes Claude Code, SSO |
| **Team — Premium** | $100/seat/month (annual) or $125/seat/month (monthly) | 5 | Higher usage limits, priority access |
| **Enterprise** | $20/seat/month base + usage (custom quote) | Negotiated | SSO, SCIM, audit logs, HIPAA option, role-based access |

> **Verify current rates at [claude.com/pricing](https://claude.com/pricing) before budgeting** — Anthropic adjusts plan structure and pricing periodically. The figures above were current as of April 2026 but may have changed.

#### 10-seat pilot estimate (Claude Code)

| Scenario | Annual cost |
|---|---|
| Team Standard (annual) | $20 × 10 × 12 = **$2,400/year** |
| Team Premium (annual) | $100 × 10 × 12 = **$12,000/year** |
| Enterprise (base only) | ~$20 × 10 × 12 = **~$2,400/year** + negotiated usage |

For a 10-engineer pilot, the Team Standard plan is the lowest-friction starting point: no procurement negotiation required, per-seat cost is predictable, and Claude Code is included. Enterprise adds the governance controls (SSO, SCIM, audit logs) that a larger rollout will eventually require.

**What is included in the seat cost:** Claude Code CLI access, VS Code extension, access to claude.ai for all model tiers, usage up to the plan's monthly limits. There is no per-API-call cost for plan subscribers — the seat cost covers a usage allocation, not per-token billing. This makes per-engineer costs fully predictable, which is a significant advantage for budget planning compared to pure consumption models.

---

### 9.2 Snowflake Cortex Code — credit consumption model

Snowflake Cortex AI features (including Cortex Code) are not licensed per seat — they are billed by Snowflake credit consumption. Credits are consumed when Cortex LLM functions are called, at rates that vary by the underlying model.

Key facts about Cortex credit billing:

- **No separate Cortex Code license.** Access is included with Snowflake editions that support Cortex AI (Enterprise and above on most cloud providers).
- **Credit consumption is per-token.** Each request to a Cortex LLM function (including the coding assistant) consumes credits proportional to the model used and the number of input/output tokens.
- **Model tiers drive cost.** Lighter models (e.g. Llama-based) consume far fewer credits than frontier models (e.g. Claude 3.5 Sonnet via Cortex). The specific rates are published in the [Snowflake Service Consumption Table](https://www.snowflake.com/legal-files/CreditConsumptionTable.pdf), which is updated periodically.
- **Costs are shared across the account.** Unlike a per-seat license, Cortex usage accrues to the Snowflake account. Heavy use by one team affects the shared credit pool.

> **Obtain current credit rates from Snowflake directly** — the Service Consumption Table is the authoritative source, and rates change as Snowflake adds models and adjusts pricing. For a concrete estimate, ask your Snowflake account team for the current Cortex AI credit rates and model the expected token volume for your pilot cohort.

---

### 9.3 Cost comparison: Claude Code vs. Cortex Code for a 10-engineer pilot

| Dimension | Claude Code (Team Standard) | Snowflake Cortex Code |
|---|---|---|
| **License model** | Per-seat, flat monthly fee | Consumption-based (credits per token) |
| **10-engineer pilot annual cost** | ~$2,400/year (predictable) | Variable — depends on usage volume and model selection |
| **Cost visibility** | Fully predictable from day 1 | Requires usage estimation; hard to forecast without telemetry |
| **Infrastructure dependency** | None — runs on engineer's machine | Requires Snowflake Cortex-enabled edition; compute warehouse active during use |
| **Included with existing Snowflake contract?** | No — separate Anthropic subscription | Potentially yes, if Snowflake edition already supports Cortex |
| **Best for** | Engineers needing full dev environment integration (code, SQL, files, shell) | Engineers and analysts who want Snowflake-native agentic workflows via CLI, Snowsight, or Notebooks |

**Recommendation for IRD pilot:** Start with the Claude Code Team Standard plan for the 10-engineer cohort. The flat per-seat cost is budget-predictable, the MCP integration is already validated (this project), and the full development environment coverage suits DE/DA workflows better than a Snowflake-embedded tool. Cortex Code is the right answer for analyst-facing use cases where the work happens entirely within the Snowflake UI — evaluate it in parallel for that audience rather than as a replacement.

---

## 10. Setup: Snowflake MCP and dbt MCP in Claude Code

Both MCP servers in this project activate automatically when Claude Code loads the project directory, because the configuration lives in `.mcp.json` at the repo root. No separate install step is required; `uvx` fetches and caches both packages on first run.

### 10.1 Prerequisites

| Requirement | Details |
|---|---|
| Claude Code | v1.x+ (CLI or VS Code extension) |
| `uv` / `uvx` | `brew install uv` or `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Snowflake RSA key pair | RSA private key for key-pair authentication |
| dbt-fusion binary | `dbtf` at `/Users/<you>/.local/bin/dbt` (installed with the dbt-fusion package) |

### 10.2 `.mcp.json` structure

Place `.mcp.json` in the repo root. Claude Code reads this file on project load and starts each listed server as a subprocess.

```json
{
  "mcpServers": {
    "dbt": {
      "command": "uvx",
      "args": ["dbt-mcp"],
      "env": {
        "DBT_PROJECT_DIR": "/absolute/path/to/your/dbt/",
        "DBT_PROFILES_DIR": "/absolute/path/to/your/dbt/",
        "DBT_PATH": "/absolute/path/to/dbt-fusion-binary",
        "DBT_MCP_ENABLE_TOOLS": "list,compile,parse,get_lineage_dev,get_node_details_dev,search_product_docs,get_product_doc_pages,get_column_lineage",
        "DO_NOT_TRACK": "true"
      }
    },
    "snowflake": {
      "command": "uvx",
      "args": [
        "snowflake-labs-mcp",
        "--service-config-file",
        "/absolute/path/to/snowflake_mcp_config.yaml"
      ],
      "env": {
        "SNOWFLAKE_ACCOUNT": "<account-identifier>",
        "SNOWFLAKE_USER": "<service-account-username>",
        "SNOWFLAKE_ROLE": "<scoped-role>",
        "SNOWFLAKE_WAREHOUSE": "<warehouse-name>",
        "SNOWFLAKE_PRIVATE_KEY_FILE": "/absolute/path/to/rsa_key.pem"
      }
    }
  }
}
```

### 10.3 Snowflake MCP setup

**Step 1 — Create a read-only service account in Snowflake.**
Create a dedicated user (e.g. `claude_ro`) with a scoped role that has only SELECT on the schemas you want accessible. Do not use an admin or developer account.

**Step 2 — Generate an RSA key pair for key-pair authentication.**
```bash
openssl genrsa 2048 | openssl pkcs8 -topk8 -nocrypt -out rsa_key.pem
openssl rsa -in rsa_key.pem -pubout -out rsa_key.pub
```
Register the public key with the Snowflake user:
```sql
ALTER USER claude_ro SET RSA_PUBLIC_KEY = '<contents of rsa_key.pub, header/footer removed>';
```

**Step 3 — Create `snowflake_mcp_config.yaml`.** This file controls which SQL statement types are permitted. Store it in the repo (no credentials here) and reference it from `.mcp.json`.

```yaml
other_services:
  query_manager: true
  object_manager: false
  semantic_manager: false

sql_statement_permissions:
  - Select: true
  - Describe: true
  - Show: true
  - Use: true
  - Alter: false
  - Create: false
  - Delete: false
  - Drop: false
  - Insert: false
  - Update: false
  - Truncate: false
```

**Step 4 — Populate `.mcp.json`** with your account identifier, username, role, warehouse, and key path. The key file path is sensitive — keep the PEM file outside the repo and reference it by absolute path.

**Step 5 — Verify** by asking Claude Code to run a test query:
```
SELECT game_date, home_team, away_team FROM baseball_data.betting.mart_game_results LIMIT 3
```

### 10.4 dbt MCP setup

The dbt MCP server (`dbt-mcp` from dbt Labs) reads your project's `manifest.json` and exposes model metadata, lineage, and column details as MCP tools.

**Step 1 — Identify your dbt binary path.** If using standard dbt-core: `which dbt`. If using dbt-fusion: `/Users/<you>/.local/bin/dbt`. Set this as `DBT_PATH`.

> **dbt-fusion compatibility note:** Standard dbt-core cannot parse a dbt-fusion project because the packages installed by dbt-fusion use incompatible dependency versions. If your project uses dbt-fusion (`dbtf`), you must point `DBT_PATH` at the dbt-fusion binary. The dbt-mcp settings validator explicitly accepts absolute paths.

**Step 2 — Run a build to generate `manifest.json`.** The `get_lineage_dev` and `get_node_details_dev` tools read from `dbt/target/manifest.json`. If the manifest is stale or absent, run:
```bash
cd dbt && dbtf build --select state:modified+
```
or a full `dbtf build` after major changes.

**Step 3 — Set `DBT_MCP_ENABLE_TOOLS`** to an allowlist of tool names. This restricts Claude Code to read-only introspection and prevents it from invoking `run`, `build`, `test`, or `clone` operations:
```
list,compile,parse,get_lineage_dev,get_node_details_dev,search_product_docs,get_product_doc_pages,get_column_lineage
```

**Step 4 — Restart Claude Code** to reload `.mcp.json` and start the new server processes.

**Step 5 — Verify** by asking Claude Code: `"List all models in the dbt project using the dbt MCP server"`

### 10.5 Available dbt MCP tools (read-only subset)

| Tool | What it does |
|---|---|
| `list` | List all models, sources, tests, or seeds by layer or resource type |
| `compile` | Compile Jinja SQL for a model without executing it |
| `parse` | Re-parse the project and regenerate `manifest.json` |
| `get_lineage_dev` | Return upstream/downstream lineage for a model from manifest |
| `get_node_details_dev` | Return model description, column definitions, and config from manifest |
| `get_column_lineage` | Trace column-level lineage via the dbt-fusion Language Server (LSP) |
| `search_product_docs` | Search dbt documentation |
| `get_product_doc_pages` | Retrieve specific dbt documentation pages |

---

## 11. Extending to Snowflake Cortex Code

[Snowflake Cortex](https://docs.snowflake.com/en/user-guide/snowflake-cortex/overview) provides AI capabilities natively within the Snowflake platform, including Cortex Analyst (natural-language-to-SQL) and Cortex Code (AI-assisted SQL development via terminal CLI, Snowsight, and Snowflake Notebooks). As MCP adoption grows across the AI tooling ecosystem, the same MCP server pattern can be surfaced to any MCP-compatible client.

### How the configuration maps

The `.mcp.json` and `snowflake_mcp_config.yaml` files are client-agnostic — they configure the server, not the client. The key adaptation for a different client is how that client discovers and registers MCP servers.

| Concern | Claude Code | Generic MCP-compatible client |
|---|---|---|
| Server discovery | `.mcp.json` in project root or `~/.claude/settings.json` | Client-specific config file or UI registration |
| Transport | stdio (subprocess) for local; HTTP/SSE for remote | Same options, depending on client support |
| Auth to Snowflake | RSA key, env vars in `.mcp.json` | Same credentials, passed via the client's secret/env management |
| Tool allowlist | `DBT_MCP_ENABLE_TOOLS` env var on the server | Same env var — server-side control, client-agnostic |
| Service permissions | `snowflake_mcp_config.yaml` | Same file — server-side control, client-agnostic |

### Adapting for Snowflake Cortex Code or Cortex Analyst

When Snowflake surfaces MCP client support within Cortex (e.g. for Cortex Analyst workflows or AI-assisted Snowsight development), the same MCP servers can be registered through Snowflake's configuration interface. The server command, environment variables, and service config file remain identical. The only change is where the client discovers the server — through Snowflake's settings rather than a local `.mcp.json`.

For teams using Cortex Analyst's semantic model approach, the dbt MCP server is a natural complement: Cortex Analyst handles the natural-language-to-SQL translation against a defined semantic layer, while the dbt MCP server provides lineage context and model documentation that can inform how the semantic layer is maintained.

### Remote MCP server deployment

For a shared team environment (where multiple analysts access the same Snowflake MCP server rather than each running their own), the server can be deployed as a remote HTTP/SSE endpoint:

```
Developer laptop  →  Remote MCP server (HTTP/SSE)  →  Snowflake (Private Link)
Claude Code                                            dbt project (read-only)
```

In this model, the MCP server runs as a service (containerized, deployed inside the corporate network perimeter), and clients connect over HTTPS. Authentication to the MCP server uses the same RBAC controls as other internal services. Each user authenticates to the MCP server with their own identity; the server maps that identity to an appropriate Snowflake role.

### Caveat: dbt manifest.json delivery with on-premises GitLab

For Cortex Code or Cortex Analyst to leverage dbt project metadata (model lineage, column descriptions, semantic layer context), the `manifest.json` produced by `dbt build` must be available inside Snowflake — typically uploaded to a Snowflake internal stage and registered with Cortex. This creates a CI/CD delivery requirement that is non-trivial in environments where GitLab is hosted on-premises.

**The core constraint:** Snowflake is a cloud service. It can receive data that is pushed to it, but it cannot reach into an on-premises GitLab instance to pull artifacts. The only viable direction is **push**: a GitLab CI/CD pipeline must upload `manifest.json` to Snowflake after every `dbt build` that changes the project.

**What that pipeline would need:**

1. A GitLab Runner with outbound network access to the Snowflake endpoint (public or Private Link). On-premises runners in locked-down environments often have strict egress controls; this may require a firewall exception or a dedicated runner in a DMZ.
2. Snowflake credentials stored as GitLab CI/CD protected secrets — typically a service account key pair — with a rotation and audit process.
3. A pipeline step that runs after `dbt build` and executes a `PUT` command (via `snowsql` or the Snowflake Python connector) to upload the manifest to a designated Snowflake stage:

```yaml
# .gitlab-ci.yml (illustrative)
upload_manifest:
  stage: post_build
  script:
    - snowsql -a $SNOWFLAKE_ACCOUNT -u $SNOWFLAKE_USER
        --private-key-path $SNOWFLAKE_KEY_PATH
        -q "PUT file://dbt/target/manifest.json @baseball_data.betting.dbt_artifacts AUTO_COMPRESS=FALSE OVERWRITE=TRUE;"
  only:
    - main
```

4. Cortex then configured to read the manifest from that stage on each session.

**Where this gets complicated in practice:**
- The GitLab runner network path to Snowflake requires security team approval and potentially a dedicated runner subnet.
- The Snowflake credential stored in GitLab secrets must be scoped, rotated, and audited separately from developer credentials.
- The manifest is only as fresh as the last pipeline run — if a developer builds locally on the EC2 and the pipeline hasn't run yet, Cortex's view of the project is stale.
- Any governance process that requires change-control approval before pipeline changes will slow the initial setup.

**How Claude Code avoids this entirely:** The dbt MCP server reads `manifest.json` directly from the local filesystem on the EC2 (or developer machine). There is no upload step, no Snowflake stage, and no CI/CD pipeline dependency. The manifest is always current — it reflects whatever `dbtf build` last produced — and the entire integration is self-contained within the developer's environment. If the CI/CD push pipeline cannot be implemented quickly due to network constraints, governance approval, or credential management complexity, **this is a concrete reason to prefer Claude Code over Cortex Code** for dbt-integrated LLM assistance in on-premises GitLab environments.

---

## 12. Building a custom enterprise MCP server with FastMCP

The MCP servers used in this project (`snowflake-labs-mcp`, `dbt-mcp`) are general-purpose servers built by the community. They expose a fixed set of tools that cover the most common use cases but are not scoped to any particular business domain, schema set, or team. For a broader enterprise rollout, this generality can become a governance and usability problem: an engineer on the Milo team does not need — and should not see — tools that expose Risk or IRD-specific schemas.

**FastMCP** ([gofastmcp.com](https://gofastmcp.com)) is the standard Python framework for building custom MCP servers. It lets engineering teams define exactly which tools are exposed, scope them to specific schemas or business domains, and enforce those boundaries at the server level — independently of what the LLM client requests.

---

### 12.1 How FastMCP works

FastMCP wraps Python functions as MCP tools using a decorator pattern. The framework automatically generates the JSON schema, input validation, and protocol lifecycle — the developer writes business logic and annotates intent:

```python
from fastmcp import FastMCP

mcp = FastMCP("IRD Data Tools")

@mcp.tool(tags={"ird", "schema"})
def describe_ird_table(table_name: str) -> str:
    """Returns column definitions and row count for an IRD mart table.
    Only tables in the IRD_MART schema are accessible."""
    # ... execute DESCRIBE TABLE against IRD_MART.{table_name} only
    ...

@mcp.tool(tags={"ird", "query"})
def query_ird_mart(sql: str) -> list[dict]:
    """Executes a read-only SELECT against the IRD_MART schema.
    Only SELECT statements are permitted; the schema is hardcoded."""
    # ... validate SELECT-only, prepend schema, execute
    ...
```

Tools are grouped by tags, which become the mechanism for domain-level filtering.

---

### 12.2 Scoping tools by business domain

FastMCP provides server-level visibility controls that determine which tools an LLM client can discover and call:

```python
# Expose only tools tagged for the IRD domain
mcp.enable(tags={"ird"}, only=True)

# Disable a specific tool by key (e.g. a tool under review)
mcp.disable(keys={"tool:admin_action"})

# Disable all tools with a given tag (e.g. destructive operations)
mcp.disable(tags={"write", "admin"})
```

**Disabled tools do not appear in `list_tools` and cannot be called.** The LLM client has no visibility into their existence — they are effectively absent from the agent's tool palette.

This makes domain scoping composable:

| MCP server instance | Tags enabled | Audience |
|---|---|---|
| `mcp-ird` | `{"ird"}` only | IRD data engineers and analysts |
| `mcp-milo` | `{"milo"}` only | Milo team engineers |
| `mcp-risk` | `{"risk"}` only | Risk team engineers |
| `mcp-shared` | `{"shared", "catalog"}` | All teams — cross-domain lookups |

Each team's `CLAUDE.md` (or `.mcp.json`) points to the appropriate server instance. An IRD engineer never sees Milo-tagged tools; a Milo engineer never sees IRD tools. The scoping is enforced at the server level, not left to the LLM's discretion.

---

### 12.3 What a custom enterprise MCP server can enforce that a general-purpose server cannot

| Capability | General-purpose MCP | Custom FastMCP server |
|---|---|---|
| Schema restriction | Relies on Snowflake RBAC only | Hardcoded at the tool level — tool will not accept off-schema table names |
| Query validation | Passes queries through; RBAC blocks unauthorized tables | Tool validates SQL structure (SELECT-only, no DDL, no cross-schema refs) before executing |
| Domain-specific tool descriptions | Generic ("run a SQL query") | Precise ("query the IRD premium fact table; `policy_id` is the grain") |
| Allowlist vs denylist | No concept | Tag-based `enable(only=True)` allowlist or `disable(tags=...)` denylist |
| Business context in tool metadata | None | Custom `meta=` field with data dictionaries, SLA info, schema documentation |

The practical effect is that the agent gets a narrower, more precisely described tool set — which makes its reasoning more accurate and its tool calls more reliable. A tool description that says "query the IRD daily premium summary (grain: policy × effective date)" gives the agent far more signal than "run a Snowflake query".

---

### 12.4 Recommended deployment pattern for enterprise rollout

1. **Stand up a shared read-only Snowflake service account** per team domain (or reuse existing RBAC roles). The FastMCP server authenticates as this account.
2. **Define domain-scoped tools** in Python — query execution, schema description, lineage lookup — each hardcoded to the team's schemas.
3. **Deploy the server as a local subprocess** (via `uvx` or `pip install`) referenced in each engineer's `.mcp.json`. No shared server infrastructure is required for the pilot; each engineer runs their own server process locally against the shared Snowflake account.
4. **Tag all tools by domain and capability tier** (`{"ird", "query"}`, `{"ird", "schema"}`, `{"ird", "admin"}`). Use `enable(tags={"ird"}, only=True)` to enforce the domain boundary.
5. **Promote shared tools to a central `mcp-shared` server** over time — catalog search, lineage queries, cross-domain dimension lookups — and reference it alongside the domain-specific server in each team's `.mcp.json`.

This pattern keeps the pilot low-risk (no shared infrastructure) while building toward a maintainable multi-team architecture.

---

## 13. Corporate security considerations

This section addresses the security requirements for a corporate deployment where engineers use MCP-connected LLM tools to assist with Snowflake SQL and dbt development, under standard enterprise governance constraints.

### 13.1 Network isolation via Private Link

Snowflake supports private connectivity through:
- **Azure Private Link** (for Azure-hosted Snowflake accounts)
- **AWS PrivateLink** (for AWS-hosted accounts)
- **Google Private Service Connect** (for GCP-hosted accounts)

When Private Link is enabled, all traffic between the MCP server and Snowflake traverses the private network and never touches the public internet. From a configuration standpoint, this is transparent to the MCP setup — the `SNOWFLAKE_ACCOUNT` identifier in `.mcp.json` resolves to the private endpoint rather than the public one. No changes to the MCP server configuration are required; the routing is handled at the network layer.

For a remote MCP server deployment (shared team server), the server should be deployed within the same VNet/VPC as the Snowflake private endpoint, ensuring end-to-end private connectivity:

```
Developer workstation  →  Corporate VPN / Zero Trust  →  MCP Server (internal)  →  Snowflake (Private Link)
```

### 13.2 RBAC via Azure Active Directory

Snowflake integrates with Azure Active Directory (AAD) through **External OAuth** (Azure AD OAuth 2.0). This allows Snowflake roles to be mapped to AAD group memberships, so access is governed by the same identity system used for all other corporate resources.

**Configuration pattern:**

1. Define Snowflake roles with least-privilege grants (e.g. `ANALYST_RO` — SELECT only on specific schemas; `ENGINEER_RW` — SELECT + DDL on dev schemas).
2. Create AAD security groups that correspond to those roles (e.g. `sf-analyst-ro`, `sf-engineer-rw`).
3. Configure Snowflake's External OAuth integration to map AAD group claims to Snowflake roles.
4. Users authenticate to the MCP server (or directly to Snowflake) using their AAD identity; the token carries their group claims, and Snowflake grants the corresponding role.

**For MCP-specific access:** The service account used by the MCP server (`SNOWFLAKE_USER` in `.mcp.json`) should itself be an AAD-registered service principal assigned to a group with only the permissions required for read-only introspection. The `snowflake_mcp_config.yaml` SQL permission allowlist is a second enforcement layer, but the Snowflake role grant is the authoritative control.

**Scoping recommendations for a development assistance use case:**

| Access need | Recommended Snowflake role grant |
|---|---|
| Query prod data for exploration | SELECT on specific schemas; no system tables |
| Describe tables and columns | DESCRIBE on target database |
| dbt model introspection (dbt MCP) | No Snowflake access needed — reads local `manifest.json` only |
| Generate and test SQL in dev schema | SELECT + CREATE on developer's personal dev schema only |

### 13.3 Read-only enforcement at the MCP layer

Beyond Snowflake RBAC, the MCP server itself enforces read-only access via `snowflake_mcp_config.yaml`:

- `object_manager: false` — disables DDL operations (CREATE, ALTER, DROP)
- `semantic_manager: false` — disables semantic model modifications
- `sql_statement_permissions` — explicit allowlist: SELECT, DESCRIBE, SHOW, USE only; all write operations (INSERT, UPDATE, DELETE, TRUNCATE, CREATE, ALTER, DROP) are blocked

Similarly, the dbt MCP server is restricted to read-only tools via `DBT_MCP_ENABLE_TOOLS`, preventing Claude Code from invoking `run`, `build`, `test`, or `clone` operations that would materialize models or modify the warehouse.

### 13.4 Data and model training

**Claude Code (Anthropic API):** When Claude Code is used via the Anthropic API (the standard commercial and enterprise tier), conversation content — including data returned through MCP tool calls — is **not used to train Anthropic's models** by default. Anthropic's API usage policy explicitly states that inputs and outputs are not used for model training without opt-in. Enterprise agreements provide additional contractual guarantees. Teams should verify their specific agreement, but the default posture is: data that passes through MCP tools remains within the session and is not retained by Anthropic for training purposes.

**Snowflake Cortex:** When AI features are accessed within the Snowflake platform (Cortex Analyst, Cortex LLM functions), data stays within the Snowflake environment. Snowflake's AI product terms govern retention and usage; Snowflake has published commitments that customer data is not used to train foundation models. For Enterprise tier accounts, these guarantees are covered under the standard data processing addendum.

**Key principle for sensitive environments:** The MCP server is a conduit — it executes queries and returns results to the LLM client. The LLM client's data retention policy is what governs whether that data is persisted. For organizations with strict data residency requirements, deploy the LLM client on-premises or in a private cloud environment, use a model with a contractually guaranteed no-training policy, and scope MCP access to non-sensitive schemas or aggregated data only.

### 13.5 Audit logging

Both Snowflake and dbt MCP activity can be audited:
- **Snowflake:** All queries executed through the MCP server appear in `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY` with the service account username. Add a recognizable username prefix (e.g. `mcp_claude_ro`) to make MCP-originated queries easy to filter.
- **Claude Code sessions:** Claude Code can be configured with logging hooks to record tool calls and their inputs/outputs for compliance review.
- **dbt MCP:** The dbt-mcp server can be run with stdout/stderr logging redirected to a file for local audit.

---

## 14. EC2-based development environments (CyberArk)

Many corporate engineering teams do not develop on local machines — instead, each engineer is provisioned a remote Linux EC2 instance inside the corporate VPC, and access is brokered through a privileged access management (PAM) solution such as **CyberArk**. This section covers the caveats and configuration steps specific to that topology.

### 14.1 How the CyberArk tunnel works

CyberArk PSM (Privileged Session Manager) acts as a proxy between the engineer's workstation and the target EC2. When an engineer initiates a session, the connection flows:

```
Engineer workstation  →  CyberArk PSM / PSMP  →  EC2 (private subnet)
```

CyberArk authenticates the engineer against AD/AAD, checks out the appropriate vault credential (or injects it transparently), establishes the SSH session to the EC2, and optionally records the session for audit. The engineer never holds the EC2 SSH private key directly — CyberArk manages it.

VS Code Remote SSH is fully compatible with this topology, but requires the SSH `ProxyCommand` (or `ProxyJump`) to be configured so that VS Code routes its SSH connection through the CyberArk PSMP host.

### 14.2 VS Code Remote SSH configuration for CyberArk

**Step 1 — Install the Remote - SSH extension** on the engineer's local VS Code. This extension installs VS Code Server on the remote EC2 automatically on first connection; no manual setup on the EC2 is needed.

**Step 2 — Configure `~/.ssh/config`** on the engineer's local workstation. The exact format depends on whether your CyberArk deployment uses PSMP (SSH Proxy) or a jump-host pattern:

*CyberArk PSMP pattern (most common):*
```
Host ec2-dev
  HostName psmp.company.com
  User <ec2-username>@<vault-username>@<ec2-private-ip-or-hostname>
  Port 22
  IdentityFile ~/.ssh/id_rsa
  ServerAliveInterval 60
  ServerAliveCountMax 3
```

*Standard ProxyJump pattern (if PSMP is configured as a jump host):*
```
Host cyberark-psmp
  HostName psmp.company.com
  User <cyberark-username>
  Port 22
  IdentityFile ~/.ssh/id_rsa

Host ec2-dev
  HostName <ec2-private-ip>
  User ec2-user
  ProxyJump cyberark-psmp
  ServerAliveInterval 60
  ServerAliveCountMax 3
```

Consult your CyberArk/PAM team for the exact connection string format — the `User` field syntax for PSMP varies by deployment. Once `~/.ssh/config` is correct, VS Code Remote SSH picks it up automatically from the host list.

**Step 3 — Connect and install extensions.** Open the Remote Explorer in VS Code, select the EC2 host, and connect. VS Code installs `~/.vscode-server/` on the EC2 automatically. Install the Claude Code extension on the remote: in VS Code with the EC2 connected, open the Extensions panel, find Claude Code, and click "Install in SSH: ec2-dev". The extension process runs on the EC2; the UI renders locally.

**Step 4 — Open the project directory** on the EC2 via `File → Open Folder (Remote)` and point it at the cloned repo. Claude Code reads `.mcp.json` from the project root; MCP server subprocesses (`uvx dbt-mcp`, `uvx snowflake-labs-mcp`) launch on the EC2.

### 14.3 Sudo access requirements

For the MCP + Claude Code development toolchain, **sudo access is not required** if user-space package managers are used. All components install into the user's home directory:

| Component | Install location | Requires sudo? |
|---|---|---|
| `uv` / `uvx` | `~/.local/bin/uv` | No — user-space curl installer |
| `dbt-mcp` (via uvx) | `~/.cache/uv/` (cached on first run) | No |
| `snowflake-labs-mcp` (via uvx) | `~/.cache/uv/` | No |
| VS Code Server | `~/.vscode-server/` | No — installed by VS Code Remote extension |
| Claude Code VS Code extension | `~/.vscode-server/extensions/` | No |
| Claude Code CLI | `~/.npm/bin/claude` (via nvm) or `~/.local/bin/` (via pipx) | No — if using nvm or user-space npm |
| dbt-fusion | `~/.local/bin/dbt` | No — if installed via user-space pip / uv venv |
| RSA private key | `~/.ssh/` or a path the engineer controls | No |

**Where sudo may be needed:**
- Installing system-level packages (Python, Node, git) that are not already present on the AMI. Most corporate EC2 AMIs include these; confirm with your platform team.
- If the EC2 uses a strict `umask` or SELinux policy that blocks writes to `~/.local/` — rare but possible on hardened AMIs. In that case, request that the platform team pre-install `uv` system-wide (`/usr/local/bin/uv`) rather than granting broad sudo.
- Docker installation — not required for this toolchain, but common in data engineering environments.

The key principle: **scope sudo requests to specific packages, not to a standing sudoers entry.** Use `sudo apt install <package>` for one-time system dependencies, not a general `ALL=(ALL) NOPASSWD: ALL` grant.

### 14.4 Installing uv without sudo on EC2

```bash
# Installs to ~/.local/bin/uv — no sudo needed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Add to PATH if not already (add to ~/.bashrc or ~/.zshrc)
export PATH="$HOME/.local/bin:$PATH"

# Verify
uvx --version
```

If the EC2 has no outbound internet access (common in air-gapped VPCs), the `uv` binary and the `dbt-mcp` / `snowflake-labs-mcp` packages must be available via an **internal artifact mirror** (Artifactory, Nexus, AWS CodeArtifact). Configure `uv` to use the internal PyPI mirror:

```bash
# In ~/.config/uv/uv.toml or as an env var
UV_INDEX_URL=https://internal-pypi.company.com/simple/
```

### 14.5 Credential management on EC2

The standard `.mcp.json` approach (RSA private key referenced by file path) works on EC2, but storing a Snowflake RSA private key as a flat file on a shared or long-lived EC2 carries risk. Prefer one of the following patterns in corporate environments:

**Option A — AWS Secrets Manager (recommended):**
Store the RSA private key in AWS Secrets Manager. At session start (or via a shell profile script), retrieve it and write it to a temp file with tight permissions:

```bash
aws secretsmanager get-secret-value \
  --secret-id prod/snowflake/mcp-rsa-key \
  --query SecretString \
  --output text > /tmp/snowflake_rsa_key_$$.pem
chmod 600 /tmp/snowflake_rsa_key_$$.pem
```

Then reference that path in `SNOWFLAKE_PRIVATE_KEY_FILE`. The EC2 instance profile IAM role controls access to the secret — no static credentials anywhere. Clean up the temp file on logout via a `~/.bash_logout` trap.

**Option B — Snowflake External OAuth with AWS IAM:**
If your Snowflake account is configured for External OAuth with AWS IAM as the identity provider, the EC2 instance profile can authenticate to Snowflake directly using short-lived IAM credentials — no private key file at all. This is the most secure option and eliminates the key rotation problem entirely. Requires coordination between the Snowflake admin and AWS IAM team to configure the OAuth integration.

**Option C — CyberArk Credential Provider:**
CyberArk's Application Identity Manager (AIM) / Credential Provider can inject credentials into application processes at runtime without exposing them as files. If your organization has AIM deployed, the MCP server startup script can retrieve the Snowflake private key from the vault rather than reading a file. This aligns with existing CyberArk governance and avoids any credential persistence on the EC2.

### 14.6 Outbound network requirements from EC2

The following outbound connections must be permitted in the EC2's security group and subnet NACLs for the full toolchain to function:

| Destination | Port | Purpose | Notes |
|---|---|---|---|
| Snowflake private endpoint | 443 | Snowflake MCP queries | Routed via AWS PrivateLink — stays in VPC |
| `api.anthropic.com` | 443 | Claude Code API calls | Must be whitelisted or routed via proxy |
| PyPI / internal mirror | 443 | `uvx` package downloads | Lock to internal mirror in air-gapped envs |
| npm registry / internal mirror | 443 | Claude Code CLI install | Only needed at install time; pin versions |
| GitHub (or internal git) | 443 / 22 | Repo clone / push | Already present in most dev EC2 setups |

If the VPC uses a centralised egress (NAT Gateway + proxy/firewall), the security team will typically need to add an explicit allow rule for `api.anthropic.com`. This is a standard pattern — similar to allowing access to `registry.npmjs.org` or `pypi.org`.

For fully air-gapped environments where outbound to `api.anthropic.com` is not permitted, Claude Code can be configured to route through a corporate HTTPS proxy:

```bash
export HTTPS_PROXY=https://proxy.company.com:8080
export HTTP_PROXY=http://proxy.company.com:8080
export NO_PROXY=snowflake-private-endpoint.company.com,localhost
```

### 14.7 Additional security considerations for EC2-based development

**Session recording scope:**
CyberArk records privileged sessions at the terminal level. This means that LLM responses, MCP query results (including data returned from Snowflake), and all Claude Code interactions are captured in the session recording if the engineer is working in a terminal. This is generally acceptable — it provides a complete audit trail of AI-assisted development activity. Engineers should be aware that their sessions are recorded and treat MCP-returned data accordingly (e.g. do not use MCP to query tables containing PII if session recordings are stored in a lower-security system).

**Shared vs. dedicated EC2 instances:**
In environments where multiple engineers share an EC2 (uncommon but not rare), `.mcp.json` referencing a shared service account credential creates a shared-credential problem. Each engineer should have their own Snowflake user with their own AAD-mapped role, and their own credential stored in a user-scoped path (e.g. `~/.config/mcp/snowflake_key.pem`). The `SNOWFLAKE_USER` and `SNOWFLAKE_PRIVATE_KEY_FILE` values in `.mcp.json` should be parametrized via environment variables sourced from the engineer's shell profile rather than hardcoded in the repo file.

Example — parametrized `.mcp.json`:
```json
"env": {
  "SNOWFLAKE_ACCOUNT": "IHUPICS-DP59975",
  "SNOWFLAKE_USER": "${SNOWFLAKE_USER}",
  "SNOWFLAKE_PRIVATE_KEY_FILE": "${SNOWFLAKE_PRIVATE_KEY_FILE}",
  "SNOWFLAKE_ROLE": "${SNOWFLAKE_ROLE}",
  "SNOWFLAKE_WAREHOUSE": "COMPUTE_WH"
}
```

Each engineer sets `SNOWFLAKE_USER`, `SNOWFLAKE_PRIVATE_KEY_FILE`, and `SNOWFLAKE_ROLE` in their `~/.bashrc` or `~/.zshrc`. The `.mcp.json` is committed to the repo with placeholders; credentials remain out of source control entirely.

**EC2 instance profile scope:**
The EC2 instance IAM role (instance profile) should follow least-privilege. If engineers use the instance profile to authenticate to Snowflake (Option B in 7.5), scope the instance profile policy to only allow `sts:AssumeRoleWithWebIdentity` for the specific Snowflake OAuth integration. Do not attach broad `AdministratorAccess` or `PowerUserAccess` managed policies to dev EC2 instance profiles.

**IMDSv2 enforcement:**
Require IMDSv2 (Instance Metadata Service v2) on all dev EC2 instances to prevent SSRF attacks from compromising the instance profile credentials. Set `HttpTokens: required` at the instance level or via an AWS Config rule org-wide. This is independent of MCP but is a baseline EC2 security hardening step relevant to any credential-aware workload.

**dbt project and manifest on EC2:**
The dbt MCP server reads `target/manifest.json` locally. In an EC2 environment, the dbt project must be cloned to the EC2 (not just mounted from a network share, which introduces latency on `parse`). Run `dbtf build` or `dbtf parse` on the EC2 to generate a fresh manifest before starting Claude Code. If multiple engineers share a repo clone on a network share, stale manifests from another engineer's build can cause confusing lineage results — each engineer should work from their own clone.

### 14.8 Summary: what you need before starting on EC2

| Item | Where to get it | Sudo needed? |
|---|---|---|
| EC2 access via CyberArk | PAM/IT team | No |
| VS Code with Remote - SSH extension | Local install | No |
| `~/.ssh/config` ProxyCommand/Jump config | PAM team provides connection string | No |
| `uv` / `uvx` on EC2 | `curl` install to `~/.local/bin` | No |
| Snowflake service account + role | Snowflake admin + AAD team | No |
| RSA private key (or Secrets Manager secret) | Snowflake admin / AWS team | No |
| Outbound 443 to `api.anthropic.com` | Network/firewall team | No |
| Claude Code API key | Anthropic console (or enterprise provisioning) | No |
| dbt-fusion binary on EC2 | `pip install dbt-fusion` via uv venv | No |
| Fresh `manifest.json` | `cd dbt && dbtf build` on EC2 | No |

---

## 15. Requirements to delivery: Plan Spec and the AI-assisted SDLC

### The coordination problem in AI-accelerated delivery

When execution gets cheap — as it does when AI can scaffold a dbt model, write tests, and draft documentation in minutes — the bottleneck shifts from implementation to coordination. A Business Requirements Document arrives from a stakeholder. A Data Architect interprets it into a dimensional model. A Data Engineer implements it in dbt. A Business Analyst validates the output against the original intent. Each handoff is a coordination cost, and in fast-moving delivery environments, intent degrades at each step: the BRD uses business language, the model design uses dimensional modeling language, the dbt code uses SQL, and the tests use assertion language. They all describe the same thing, but the mapping between them is implicit and fragile.

**[Plan Spec](https://planspec.io)** is a declarative specification standard designed to address exactly this problem. It represents plans as directed acyclic graphs (DAGs) — schema-validated, version-controlled, execution-agnostic documents that capture intent, structure, and task dependencies in a durable artifact. Inspired by Kubernetes-style declarative configuration, a Plan Spec is not a workflow engine or an agent framework: it describes *what* should happen, leaving *how* to the tools and engineers that execute it. Plans become reviewable artifacts that can be inspected, approved, paused, and handed off — just like code.

### BRD → Plan Spec: the AI-assisted translation

The most immediate application of Plan Spec in the data engineering SDLC is as the structured output of the requirements-to-design translation step. A Business Analyst or Data Architect takes a Business Requirements Document, works with an AI assistant to analyze it, and produces a Plan Spec that decomposes the delivery into explicit, dependency-ordered tasks.

**What the AI does in this step:**
- Reads the BRD and identifies the business entities, metrics, dimensions, and reporting grain that the requirements imply
- Maps those entities to source tables available in Snowflake (using the Snowflake MCP server for live schema context)
- Proposes a dimensional model (fact and dimension tables) that satisfies the reporting requirements
- Decomposes the delivery into a Plan Spec: each task is a concrete deliverable (e.g. "implement `dim_customer` from HVR source tables", "implement `fact_orders` with grain = order line", "write dbt tests for referential integrity between fact and dimension")
- Captures dependencies between tasks explicitly (e.g. `fact_orders` cannot be delivered until `dim_customer` and `dim_product` are complete)
- Attaches acceptance criteria to each task, derived directly from the BRD's stated requirements

The resulting Plan Spec is a machine-readable, version-controlled artifact that lives in the GitLab repo alongside the dbt models it describes. It is not a chat log or a planning document that sits in Confluence and goes stale — it is a structured specification that can be diffed, reviewed in a merge request, and referenced throughout delivery.

### How Plan Spec fits into the data engineering SDLC

```
 BRD                Plan Spec               Implementation           Validation
 (Business)        (AI-assisted)            (Engineer + AI)          (BA + Architect)
    │                   │                         │                       │
    │  AI analyzes BRD  │                         │                       │
    ├──────────────────►│                         │                       │
    │  Proposes model   │                         │                       │
    │  Decomposes tasks │                         │                       │
    │  Maps sources     │  Tasks assigned         │                       │
    │                   ├────────────────────────►│                       │
    │                   │  MR per task            │                       │
    │  Review Plan Spec │  AI implements          │                       │
    │◄──────────────────┤  Human reviews MR       │                       │
    │  Approve/revise   │  Merges to main         │  Output validated     │
    │                   │                         ├──────────────────────►│
    │                   │  Plan Spec updated      │  against BRD          │
    │                   │  as tasks complete      │                       │
```

**Phase-by-phase integration:**

| SDLC Phase | Traditional approach | With Plan Spec + AI |
|---|---|---|
| **Requirements** | BRD written, emailed, interpreted manually | BRD → AI analysis → Plan Spec generated; reviewed and approved by BA + Architect before development begins |
| **Design** | Data Architect designs model in isolation | AI proposes model from BRD + live schema context; Architect reviews, refines, approves Plan Spec |
| **Development** | Engineers pick up tasks from Jira/backlog | Engineers work through Plan Spec tasks with AI assistance; each task produces a GitLab MR with the Plan Spec task ID referenced |
| **Testing** | Testing added if time permits | Plan Spec includes explicit test tasks; AI generates dbt tests from acceptance criteria in the spec |
| **Review** | Informal review against verbal requirements | MR is reviewed against the Plan Spec acceptance criteria; BA validates output against original BRD |
| **Documentation** | Written last (or not at all) | AI generates dbt model and column documentation as part of each task; documentation completeness is a Plan Spec acceptance criterion |

### Why this matters for the IRD team specifically

The IRD team regularly translates complex business and reporting requirements into data models that must conform to enterprise standards across multiple source systems. The BRD → Plan Spec → implementation chain gives the team a repeatable, auditable process for that translation:

- The Data Architect is no longer the single point of interpretation between the BRD and the code — the Plan Spec externalizes that interpretation so it can be reviewed and corrected before implementation begins
- Business Analysts can read the Plan Spec and verify that the decomposition reflects their intent, before a line of code is written
- When scope changes arrive mid-delivery (as they always do), the Plan Spec is updated, the diff shows exactly what changed, and the downstream task dependencies are re-evaluated explicitly rather than propagated informally
- Post-delivery, the Plan Spec serves as a traceable record of what was built and why — the artifact that links the business requirement to the dbt model to the Snowflake table

---

## 16. Agentic engineering in CI/CD

### The principle: AI accelerates, humans gate

Agentic engineering does not remove the need for human judgment in the delivery pipeline — it changes where that judgment is applied. The goal is to use AI to eliminate low-value review work (catching obvious errors, flagging missing tests, writing MR descriptions) so that human reviewers can focus on the high-value questions: Is the business logic correct? Does this model conform to enterprise standards? Are the acceptance criteria from the Plan Spec met?

The non-negotiable rule is: **no code is merged to the main branch without a human reviewer approval.** AI tools participate in the pipeline as accelerators and quality signals, not as gatekeepers.

### Where AI fits in the GitLab CI/CD pipeline

```
 Developer workflow                  GitLab CI pipeline                 Human gate
 ──────────────────                  ──────────────────                 ──────────
 1. Write code (AI-assisted)
 2. Pre-commit checks:
    - AI code quality scan        →  3. Compile check (dbtf compile)
    - Linting (sqlfluff)          →  4. Unit test run (dbt test)
    - Missing test detection      →  5. AI MR review comment
 ──────────────────────────────────  6. Coverage report                 7. Human MR review ← REQUIRED
                                     7. All checks pass?                   (approve or request changes)
                                                                        8. Merge to main
                                                                        →  9. dbtf build (full refresh)
                                                                        → 10. Validation query run
```

### Pre-commit: AI quality checks before the MR is created

Before pushing to GitLab, engineers run a pre-commit hook suite that includes AI-assisted checks:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/sqlfluff/sqlfluff
    hooks:
      - id: sqlfluff-lint
        args: [--dialect, snowflake]

  - repo: local
    hooks:
      - id: dbt-compile-check
        name: dbt compile check
        entry: dbtf compile --select state:modified+
        language: system
        pass_filenames: false

      - id: ai-quality-scan
        name: AI code quality scan
        entry: claude --print "Review the staged dbt SQL changes for: missing tests in schema.yml,
               undocumented columns, anti-patterns (SELECT *, Cartesian joins, hardcoded dates),
               and conformance with the project's style guide. Output a summary of issues found."
        language: system
        pass_filenames: false
```

The AI quality scan is advisory — it outputs a summary for the engineer to review before pushing. It does not block the commit on its own, because the human reviewer is the gate. Its purpose is to surface issues early so the engineer can fix them before the MR rather than in review.

### CI pipeline: automated quality gates

The GitLab CI pipeline runs a defined set of automated checks on every MR. These are hard gates — the MR cannot be merged if they fail:

```yaml
# .gitlab-ci.yml (illustrative structure)
stages:
  - validate
  - test
  - review
  - build

compile:
  stage: validate
  script:
    - dbtf compile --select state:modified+
  only: [merge_requests]

lint:
  stage: validate
  script:
    - sqlfluff lint dbt/models/ --dialect snowflake
  only: [merge_requests]

dbt_test:
  stage: test
  script:
    - dbtf build --select state:modified+ --full-refresh
    - dbtf test --select state:modified+
  only: [merge_requests]

ai_mr_summary:
  stage: review
  script:
    - |
      claude --print "
        Review the dbt model changes in this MR. For each changed model:
        1. Summarize what business logic changed and why (reference Plan Spec task ID if present)
        2. List any tests added or removed
        3. Flag any columns added without documentation
        4. Identify any downstream models affected by this change
        Output a structured MR description suitable for a human reviewer.
      " > mr_summary.txt
    - cat mr_summary.txt
  artifacts:
    paths: [mr_summary.txt]
  only: [merge_requests]

deploy:
  stage: build
  script:
    - dbtf build --select state:modified+
  only: [main]
  when: manual  # human must trigger production deployment
```

### AI-generated MR descriptions

One of the highest-leverage CI/CD integrations is having the AI generate the MR description automatically. Engineers often write minimal MR descriptions under delivery pressure, leaving reviewers without context. An AI-generated description that summarizes what changed, what the Plan Spec task was, which tests were added, and which downstream models are affected gives the human reviewer the context they need to do a meaningful review — not just a line-by-line syntax check.

The AI-generated summary is posted as the MR description or as a bot comment. The engineer can edit it before requesting review. The human reviewer reads it as a starting point, not as a final assessment.

### Human code review: the non-negotiable gate

All AI participation in the pipeline is upstream of the human reviewer. The reviewer's responsibilities are explicitly those that AI cannot reliably perform:

| Reviewer responsibility | Why AI cannot own it |
|---|---|
| Verify business logic against requirements | Requires understanding of business context outside the codebase |
| Confirm Plan Spec acceptance criteria are met | Requires judgment about whether the output satisfies the stated intent |
| Validate dimensional model conformance | Requires knowledge of enterprise standards and existing conformed dimensions |
| Approve data type and grain decisions | Requires accountability for downstream impact |
| Merge approval | Human accountability is a hard requirement for regulated environments |

The reviewer uses the AI-generated MR summary, the compile and test results from CI, and the Plan Spec (if applicable) as inputs. Their approval is the single gate before merge.

### GitLab-specific considerations for on-premises deployments

For teams running on-premises GitLab with no outbound internet access from runners, the AI quality scan and MR summary steps require the runner to have access to the Claude Code API (`api.anthropic.com`). If the runner is in a locked-down subnet, route through the corporate proxy or deploy a dedicated runner in a DMZ segment with approved outbound access. Alternatively, the AI quality scan can be moved from CI to a developer-side pre-push hook, keeping the CI pipeline fully internal while still capturing AI-assisted review before the MR is created.

The compile, lint, and dbt test stages have no external dependencies and run entirely within the corporate network — these are always achievable regardless of egress restrictions.

---

## 17. Best practices for agentic engineering

This section captures practical guidance for getting consistent, high-quality output from a coding agent. The principles apply regardless of which client (Claude Code, Cortex Code) or which MCP configuration is in use.

---

### 17.1 Prompt engineering

**Be specific about the goal, not just the action.**

The agent plans from the task description. Descriptions that explain *what you are trying to achieve* and *why* produce better plans than descriptions that prescribe step-by-step actions. The agent is good at method; it is not good at inferring intent.

| Less effective | More effective |
|---|---|
| "Fix the SQL in this file" | "The `mart_daily_premium` model returns nulls for `written_premium` when `policy_status = 'cancelled'`. Check whether the cancellation records are being filtered out upstream in the `stg_policy` model and fix if so." |
| "Add documentation" | "Add `description:` entries to all undocumented columns in `mart_batter_rolling_stats.yml`. Use language consistent with the existing documented columns in that file." |
| "Refactor this" | "Refactor `mart_pitcher_rolling_stats.sql` to use CTEs instead of nested subqueries. Keep column names and logic identical — this is a structural cleanup only." |

**Front-load constraints.** If there are things the agent must not do (modify other files, change column names, add new dependencies), state them at the beginning of the prompt, not the end.

**Separate exploration from implementation.** Ask the agent to investigate and report first; implement second. This catches wrong assumptions before code is written:

> Step 1: "Read `stg_policy.sql` and `mart_daily_premium.sql`. Tell me how cancelled policies are handled in each model and whether there is a filter that could be dropping their premium contributions."

> Step 2 (after reviewing the report): "The filter is in `stg_policy` at line 47. Remove it there and add a `policy_status` column to the mart so downstream models can filter themselves."

---

### 17.2 Context management

**Write and maintain a `CLAUDE.md` file.** This is the single highest-leverage investment. Instructions in `CLAUDE.md` are loaded at session start and apply to every interaction in the project. Anything you find yourself repeating across sessions belongs there.

High-value `CLAUDE.md` contents for a data engineering team:

```markdown
# CLAUDE.md

## Stack
- dbt-fusion: use `dbtf`, not `dbt`
- Snowflake warehouse: COMPUTE_WH
- All transforms live in `dbt/models/`; Python scripts in `scripts/`

## Naming conventions
- Staging: `stg_<source>_<entity>` (e.g. `stg_statsapi_schedule`)
- Mart: `mart_<domain>_<entity>` (e.g. `mart_batter_rolling_stats`)
- Feature store: `feature_<scope>` (e.g. `feature_game_level`)

## Architecture constraints
- Never modify `raw_` prefixed tables — managed by HVR replication
- All fact tables must join to `dim_date` using the `game_date_key` surrogate
- Column names on mart tables must match exactly what downstream models reference

## Code style
- No inline comments explaining WHAT the code does
- Only add a comment when the WHY is non-obvious (hidden constraint, workaround, invariant)
- CTEs preferred over nested subqueries

## Testing
- Every new column added to a mart model needs at minimum a `not_null` test
- `unique` test required on grain-defining columns
```

**Break long tasks across sessions.** Do not let a single session sprawl across many hours of work. As the context window fills, older turns are compressed and the agent loses nuance from early in the session. Natural session boundaries:

- Completing a single mart model build
- Completing a single investigation task
- Completing a single PR worth of changes

End each session by asking the agent to write a brief handoff summary (what was done, what was not done, what the next session should start with). Use that summary as the opening prompt of the next session.

**Use `/compact` (or equivalent) proactively.** Most agent clients (including Claude Code) offer a manual context compaction command that summarizes earlier turns while preserving recent context. Use it before the client is forced to compress automatically — forced compression happens at the worst moment (mid-task) and may drop detail you need.

---

### 17.3 Token management

Token consumption drives both cost and context window exhaustion. The primary levers are:

**File reads are expensive.** Each file the agent reads adds to the running token count. The agent reads what it thinks is necessary — but a vague task description causes it to read more files than a specific one. The more precisely you identify which files are relevant, the fewer unnecessary reads occur.

**Tool call results accumulate.** Every MCP query result, shell command output, and file read is appended to the context window. Long conversation sessions with many tool calls will eventually compress. If you can ask the agent to be specific about what it returns (e.g. "show me only the columns that are null in this query result"), the result is smaller.

**Estimate token consumption for planning purposes.** Rough order-of-magnitude estimates for common data engineering tasks with Claude Code:

| Task type | Approximate token range |
|---|---|
| Investigate a data quality issue (3–5 file reads + 2–3 queries) | 15,000–40,000 tokens |
| Build a new dbt mart model from scratch | 30,000–80,000 tokens |
| Write tests for an existing model | 10,000–25,000 tokens |
| Trace lineage and explain a metric | 20,000–50,000 tokens |
| Review and refactor a complex SQL file | 15,000–35,000 tokens |

For the Claude Code Team Standard plan, the monthly usage allocation is shared across all sessions. Monitor usage in the Claude.ai admin panel if you are approaching limits — this typically becomes visible at high-volume usage patterns (multiple engineers, multiple sessions per day).

**For Snowflake Cortex Code:** Because costs are credit-per-token, token consumption maps directly to billing. Prefer lighter models (Llama-tier) for routine tasks (autocomplete, describe) and frontier models (Claude-tier) only for complex reasoning tasks (root cause analysis, multi-model design). Configure this at the Cortex Code tool level; the default model selection may not be cost-optimized for routine use.

---

### 17.4 Task scoping and session hygiene

**One deliverable per session.** A session that tries to build a fact table, fix a data quality issue, and update three test files will have a muddied context by the end. The agent's understanding of "what we were trying to do" drifts as the session accumulates turns. One session = one PR worth of work = one clear goal.

**State the expected output format.** If you want a markdown summary, say so. If you want the agent to write code but not explain it, say so. If you want it to ask before writing, say so. Agents default to verbose explanations unless instructed otherwise.

**Iterate quickly when the agent goes wrong.** The agent revises its plan immediately based on corrections. A single short redirect ("that table is in the IRD schema, not staging") is more efficient than letting it complete a wrong approach and then asking it to undo the work. Interrupt early; don't wait for the wrong answer to complete.

**Verify outputs before declaring done.** Agents can produce code that looks correct but contains subtle logical errors — off-by-one grain joins, wrong aggregation windows, missing NULL handling. The final verification step is always human: run the query, check the row counts, compare the output against the expected value. The agent is a capable drafter; the engineer remains the accountable reviewer.

---

### 17.5 Quick reference: the checklist before starting a session

```
□ CLAUDE.md is up to date with current conventions
□ The task is scoped to a single deliverable
□ The prompt includes: what file/table is involved, what the expected behavior is,
  and what the current behavior is
□ Constraints are stated upfront (what NOT to change)
□ A verification step is planned (how will you check the output?)
```

The most common cause of poor agent output is not model capability — it is an underspecified starting prompt. The checklist above takes 60 seconds and consistently produces better first-pass results.

---

### 17.6 The six values of agentic engineering

Arnaud Gelas's ["The Agentic Engineering Manifesto: Six Values for a Post-Agile World"](https://medium.com/@arnaud.gelas/the-agentic-engineering-manifesto-six-values-for-a-post-agile-world-ec5c9f20bf6f) proposes six values that define professional agentic engineering practice. These are presented as deliberate tradeoffs — what to prioritize *over* something else — not just a list of good intentions.

| Prioritize | Over |
|---|---|
| **Iterative steering and alignment** | Rigid upfront specifications |
| **Verified outcomes with auditable evidence** | Assertions of success |
| **Right-sized agent collaboration** | Monolithic "god-agents" |
| **Curated, high-signal context and memory** | Stateless sessions |
| **Tooling, telemetry, and observability** | Chat-based approaches |
| **Resilience under stress** | Performance only in ideal conditions |

These values map directly to the practices in the earlier subsections of this section. The fourth value — curated, high-signal context over stateless sessions — is the principle behind maintaining `CLAUDE.md` and `project_context.md`. The second value — verified outcomes with auditable evidence — is the principle behind having human reviewers on every agent-generated change (Section 16).

Gelas's definition of done for agentic work is worth holding as a standard: work is complete only when it is **shipped, observable, verified against tests, provably correct (when necessary), learned from, governed appropriately, and economically routed**. "The model said it worked" is not a definition of done.

---

