# Independent Reproduction Guide

This guide reproduces the experiments used to test whether Antigravity CLI 1.1.17 can resume an externally synthesized `transcript.jsonl` as native conversation history. The procedure is intentionally conservative and does not modify Antigravity's internal conversation databases.

### Step 1: Test `transcript.jsonl` as an import source
1. Generate a fresh test identifier (for example `test-ablation-2222`).
2. Create the derived-log directory:
   ```bash
   mkdir -p ~/.gemini/antigravity/brain/test-ablation-2222/.system_generated/logs/
   ```
3. Write a synthetic transcript record:
   ```bash
   echo '{"step_index":1,"source":"USER_EXPLICIT","type":"USER_INPUT","status":"DONE","created_at":"2026-08-21T10:00:00Z","content":"Hello world!"}' > ~/.gemini/antigravity/brain/test-ablation-2222/.system_generated/logs/transcript.jsonl
   ```
4. Attempt to resume it:
   ```bash
   agy --conversation test-ablation-2222 --print "What did I say?"
   ```
5. **Observed on v1.1.17 / Windows:** `warning: conversation "test-ablation-2222" not found`.

This demonstrates only that the derived transcript by itself is insufficient for native resumption in the tested environment.

### Step 2: Inspect observed Antigravity-managed conversation state
1. Create a clean conversation through the official CLI:
   ```cmd
   cmd.exe /c "set AGY_CONVERSATION_ID= && set AGY_WORKSPACE= && agy --new-project --print \"The verification phrase is DELTA-99991.\""
   ```
2. Locate the most recently generated conversation database:
   ```powershell
   Get-ChildItem -Path ~/.gemini/antigravity/conversations/*.db | Sort-Object LastWriteTime -Descending | Select-Object -First 1
   ```
3. Inspect schema metadata **read-only**:
   ```python
   import sqlite3
   import sys

   db_path = sys.argv[1]
   conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
   print(conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall())
   ```
4. **Observed on v1.1.17 / Windows:** tables such as `steps`, `trajectory_meta`, and `gen_metadata`, including opaque/BLOB-encoded fields whose supported external construction contract is undocumented.

Do not mutate these databases as an integration strategy. The purpose of this experiment is to identify the boundary: the CLI needs a supported import/creation interface if external historical state is to become a normal resumable Antigravity conversation.
