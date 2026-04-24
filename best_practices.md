### Techniques

- PRD-First Developer
    - product requirement documents - these are markdown docs outlining the scope
    - Becomes the northstar of everything you're supposed to build
    - don't have the coding agent do too much, break into tasks
    - Brownfield development: 
        - Document what you already have and what you want to build next
    - There are commands: 
        - Prompts which create the workflows
    - Prime Command
        - Use it to load all of the necessary context for the agent (primes itself)
- Modular Rules Architecture
    - These are the constraints and conventions loaded at the start of every conversation
    - Commands, testing strategy, logging strategy
    - Take different rules for different task types and only load those when they're needed
        - Include tech stack, project structure, commands, mcp servers, code conventions
        - Want the LLM to know this
        - Reference Documentation
            - Task type specific context: very specific with instructions because just reading when working
    - Goal is to protect the context window of the coding agent
- Command-ify Everything
    - If you do something more than twice, make it a command
    - Workflows become reusable - these are just markdown documents which get loaded for context
    - Anything you can do as part of the workflow will become repeatable
- The Context Reset
    - In between planning and execution, should always resart the conversation with the coding agent
    - Plan -> Doc -> Clear conversation Fresh Start -> Clean context, better results
    - Want to do this because we want to keep context as clean as possible
- System Evolution Mindset
    - Every bug is an opportunity to evolve your SYSTEM for AI Coding
    - What we can fix: 
        - Global rules
        - Reference context
        - Commands/workflows
    - When it messes up, it's a rule that you want to specify or a process you want to specify
    - This is more of a mindset, don't fix the bug, fix the system which caused the bug


### BXT

- Business Viability
    - Strategic Alignment: Every initiative starts with a clear understanding of the business objective. 
    - Value Creation: Focus on use cases that deliver measurable impact
    - Stakeholder Engagement: Bring together groups for buy-in and long-term success
- Experience Desirability
    - User-Centric Design:  Solutions are crafted with the end-user in mind, maximize adoption and satisfaction
    - Change Management: Education, coaching, co-development - ensures smooth transitions
- Technical Feasibility
    - Modern Data Platforms
    - Conforms with Security Requirements
    - Appropriate tooling

