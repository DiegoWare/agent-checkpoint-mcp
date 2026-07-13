"""Canonical instruction text written by `agent-checkpoint-mcp init`.

Kept in sync by hand with examples/CLAUDE.md.example and
examples/AGENTS.md.example in the repository.
"""

INSTRUCTIONS_MARKER = "agent-checkpoint MCP"

CHECKPOINT_INSTRUCTIONS = """\
# Checkpoint discipline (agent-checkpoint MCP)

This project uses the `agent-checkpoint` MCP server so multi-step work
survives session cuts (context limits, quota). Rules for any agent:

1. **Starting a task that might be a continuation** (or when unsure): call
   `get_checkpoint` first. If a checkpoint exists, continue from "what
   remains"; never redo anything under "what was already done".

2. **After every concrete sub-task** — a file edited, a test passing, a
   command run, a bug diagnosed — call `save_checkpoint`. Do not wait for a
   whole numbered step to finish. The test: if this session died right now,
   could another agent continue from the checkpoint without asking questions?

3. **Checkpoint quality**: pass the full plan verbatim each time; make
   `what_was_done` cumulative and specific; make `what_remains` the exact
   next action in the current step.

4. **Finishing**: save a final checkpoint with `step_status="done"`. Only
   call `clear_checkpoints` with `confirm=true` after the user agrees.
"""
