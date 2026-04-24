# PlanSpec: Overview, Purpose, and Application to Agentic Engineering

---

## What is PlanSpec?

PlanSpec is a declarative planning specification standard designed to represent software delivery work as structured, version-controlled, machine-readable documents. Inspired by Kubernetes-style declarative configuration, a PlanSpec document describes *what* should be accomplished — not *how* to accomplish it. The how is left to the engineers and AI agents that execute against the spec.

Plans are expressed as YAML documents conforming to the `planspec.io/v1alpha1` API schema. A complete plan is composed of two primary document kinds — `Goal` and `Plan` — that work together to define an objective and decompose it into an ordered, dependency-aware task graph.

PlanSpec integrates directly with Claude Code via a `/planspec` skill. Once installed, Claude Code can generate plans from natural language descriptions, validate plan correctness, and execute tasks in dependency order while checking acceptance criteria against each task's definition of done.

---

## How PlanSpecs Are Structured

### The `Goal` Kind

A `Goal` document defines the intended outcome. It captures the objective at a level of abstraction that remains stable even as implementation details change. Goals do not specify how work will be done — only what success looks like.

```yaml
apiVersion: planspec.io/v1alpha1
kind: Goal
metadata:
  name: user-authentication
  namespace: default
spec:
  description: Secure user authentication system
  acceptanceCriteria:
    - description: Users can create accounts
    - description: Users can log in securely
    - description: Sessions expire after inactivity
```

Key fields:
- `metadata.name` — a unique identifier for the goal, referenced by the Plan
- `spec.description` — a plain-language statement of intent
- `spec.acceptanceCriteria` — the conditions that must be true for the goal to be considered complete

### The `Plan` Kind

A `Plan` document references a Goal and defines the task graph required to achieve it. The graph is a directed acyclic graph (DAG) of nodes, where each node is a `Task` with an explicit description, optional dependencies on prior tasks, and its own acceptance criteria.

```yaml
apiVersion: planspec.io/v1alpha1
kind: Plan
metadata:
  name: user-authentication-plan
  namespace: default
spec:
  description: Implementation plan for secure user authentication
  goalRef:
    name: user-authentication
  graph:
    nodes:
      - id: setup-database
        kind: Task
        description: Create user table in the database
        acceptanceCriteria:
          - type: command_succeeds
            name: Table exists
            command: psql
            args: ["-c", "\\d users"]

      - id: implement-signup
        kind: Task
        description: Create signup endpoint
        dependsOn:
          - setup-database
        acceptanceCriteria:
          - type: artifact_exists
            name: Signup handler file exists
            path: src/handlers/signup.ts

      - id: implement-login
        kind: Task
        description: Create login endpoint with session management
        dependsOn:
          - setup-database
        acceptanceCriteria:
          - type: command_succeeds
            name: Login endpoint test passes
            command: npm
            args: ["test", "--", "--grep", "login"]
```

Key fields:
- `spec.goalRef` — links the plan to its parent Goal
- `graph.nodes` — the ordered list of tasks
- `node.id` — unique identifier for the task within the graph
- `node.dependsOn` — list of task IDs that must complete before this task can begin
- `node.acceptanceCriteria` — verifiable conditions proving the task is complete

### The `Gate` Kind

Gates are verification checkpoints that block advancement until a condition is satisfied. Common gate types include human approval (e.g., security team sign-off), code review requirements, and automated quality checks. Gates decouple sequential work from the assumption that the preceding task was correct.

```yaml
apiVersion: planspec.io/v1alpha1
kind: Gate
metadata:
  name: security-review
  namespace: default
spec:
  gateType: review
  description: Security team must approve before deployment
  reviewers:
    - team:security
```

### Acceptance Criteria

Acceptance criteria appear at both the Goal level (high-level outcomes) and the Task level (specific, verifiable conditions). Strong acceptance criteria are:

- **Specific and measurable** — "API responds within 200ms for 95th percentile" not "API is fast"
- **Verifiable** — ideally automated; criteria types include `command_succeeds`, `artifact_exists`, and `endpoint_responds`
- **Independent** — each criterion can be evaluated on its own, not sequentially dependent on another

Goal-level criteria define what success looks like for the whole objective. Task-level criteria define the definition of done for each individual unit of work.

---

## How PlanSpecs Are Used

The intended workflow has three phases:

1. **Plan generation** — invoke `/planspec plan "description"` in Claude Code. The agent reads the description, infers the task decomposition and dependency order, and generates a Goal + Plan YAML document pair.

2. **Validation** — invoke `/planspec validate` to confirm the plan is schema-valid, that all `dependsOn` references resolve, and that all tasks have acceptance criteria.

3. **Execution** — invoke `/planspec implement`. Claude Code reads the task graph, resolves the dependency order, implements each task in sequence, and verifies each task's acceptance criteria before moving to the next. If a task's criteria are not met, execution halts at that node rather than propagating failure downstream.

The PlanSpec YAML document is a file that lives in the project repository alongside the code it describes. It can be committed, diffed, reviewed in a pull request, and updated as scope changes — the same lifecycle as any other versioned artifact.

---

## Why PlanSpecs Exist

### The coordination problem

When AI tooling makes execution cheap — a Claude Code agent can scaffold a dbt model, write tests, and draft documentation in minutes — the bottleneck shifts from implementation speed to coordination clarity. The failure mode is not slow code; it is requirements that degrade through each handoff: from business language in a requirements document, to design language in a ticket, to SQL in a dbt model, to assertion language in a test. Each translation is implicit and lossy.

PlanSpec addresses this by externalizing the interpretation of requirements into a structured, reviewable artifact *before implementation begins*. The plan is the contract between the person who specified the work and the person (or agent) who implements it. When scope changes, the plan document changes, the diff is visible, and downstream dependencies are re-evaluated explicitly.

### Making plans reviewable like code

A task list in a ticket or a chat message is invisible to version control, untestable, and gone once the conversation ends. A PlanSpec YAML file is a first-class citizen of the repository. It can be:
- Reviewed and approved before a line of implementation code is written
- Diffed when requirements change, making the impact of scope changes explicit
- Referenced from commit messages and pull request descriptions to link implementation to intent
- Read by any engineer (or agent) joining the project mid-delivery to understand what was built and why

### Structured dependency ordering

Informal backlogs rarely capture task dependencies rigorously. Engineers discover them during implementation — "oh, I can't build this until that other thing is done." PlanSpec requires dependencies to be declared upfront in the `dependsOn` field. This has two benefits: it catches sequencing problems at plan review time (not mid-implementation), and it gives an execution engine (Claude Code or otherwise) a topological sort order to follow.

---

## PlanSpec and Agentic Engineering

PlanSpec is directly relevant to agentic engineering, and the fit is strong enough that it changes the quality ceiling of what agents can reliably deliver.

### The core problem agents face without structure

An AI agent given a vague task ("build the ML pipeline") must infer scope, invent sub-tasks, decide sequencing, and determine what done looks like — all from ambiguous context. Even capable agents drift: they solve adjacent problems, over-engineer, miss a required component, or cannot tell when to stop. The quality of the output depends heavily on how well the initial prompt constrained the problem.

PlanSpec eliminates that ambiguity at the source. The agent receives a task with a specific description, a declared set of dependencies that have already been completed, and a list of acceptance criteria that define done precisely. The agent's job is narrower and better-defined: implement this task, in the context of what has already been built, and verify these specific conditions.

### The verification loop

One of the most important properties of PlanSpec for agentic use is that acceptance criteria are machine-checkable. Rather than asking the agent to self-assess ("does this look right?"), acceptance criteria of type `command_succeeds`, `artifact_exists`, or `endpoint_responds` produce a binary pass/fail signal that the agent can evaluate without subjective judgment. This grounds the agent's self-evaluation in observable reality rather than its own confidence.

In the context of this project: a PlanSpec task for building a dbt model might have acceptance criteria like `dbtf build --select <model>` exits with code 0 and all tests pass. That is an objective, automatable gate — not a request for the agent to assess whether the SQL "looks correct."

### Dependency ordering as an execution scaffold

Agentic execution of a multi-task plan without dependency structure tends to produce one of two failure modes: the agent tries to do everything in one pass (producing shallow, incomplete work across too many files), or it executes in an arbitrary order and hits blocking dependencies at runtime. PlanSpec's DAG structure solves this by giving the agent a topological execution order. Each task is attempted only when its declared prerequisites are done. The agent's context at each step is narrow and relevant — it is not carrying the full 10-task plan in its reasoning window simultaneously.

### Human oversight at the right granularity

PlanSpec does not remove human judgment from the loop — it places it at the right points. Humans approve the plan before execution begins (reviewing the decomposition and acceptance criteria), and Gates can enforce human checkpoints mid-execution for decisions that require judgment the agent should not make alone (security sign-off, architecture review, scope change approval). Between those gates, the agent can execute autonomously against well-specified tasks. This is the appropriate autonomy profile for production engineering work: agent-driven within well-defined task boundaries, human-gated at decision points.

### Application to this project

The next phase of this project — building the `betting_ml/` pipeline (Cards 4.6 through 4.10 in `project_context.md`) — is a good candidate for PlanSpec. The cards already have the structure: each card has a description, a blockers section (which maps to `dependsOn`), and an acceptance criteria checklist. Translating those cards into a PlanSpec Plan would:

1. Give Claude Code a structured execution scaffold for implementing each card in the correct dependency order (4.6 → 4.7, 4.8, 4.9 in parallel → 4.10)
2. Provide verifiable acceptance criteria that the agent can check programmatically (e.g., `pytest` exits 0, Snowflake query returns the expected row count)
3. Create a version-controlled record of what was built and why, separate from the code itself
4. Allow human review of the full implementation plan before any code is written — catching sequencing problems, ambiguous specs, or missing dependencies at plan time rather than mid-implementation

The Trello card format already used in this project (`project_context.md` Section 12) is functionally close to PlanSpec's task structure. The main additions PlanSpec brings are: machine-readable YAML (reviewable and executable, not just readable), formal `dependsOn` dependency declarations, and typed acceptance criteria that an agent can evaluate programmatically rather than by reading prose.

---

## Summary

| Dimension | PlanSpec |
|---|---|
| **Format** | YAML, Kubernetes-style declarative, version-controlled |
| **Primary kinds** | `Goal` (objective), `Plan` (task DAG), `Gate` (checkpoint) |
| **Dependency model** | DAG with explicit `dependsOn` per task; topologically ordered execution |
| **Definition of done** | Typed, verifiable acceptance criteria at goal and task level |
| **Claude Code integration** | Native via `/planspec` skill; plan, validate, and implement commands |
| **Human oversight** | Plan review before execution; Gates at checkpoints |
| **Value for agentic engineering** | High — narrows agent scope, grounds self-evaluation in objective criteria, enforces correct execution order, makes plans reviewable artifacts |
