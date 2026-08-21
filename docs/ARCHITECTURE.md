# Architecture

## Design
```text
Source Session (Claude JSONL)
      │
      ▼
┌───────────────┐
│ Source Parser │ (Streaming line-processor)
└───────┬───────┘
        ▼
┌─────────────────────┐
│ Canonical Session   │ (ASEF Pydantic Models)
└─────────┬───────────┘
          │
      Inspector
          │
          ▼
   Target Adapter  (Antigravity Exporter)
          │
          ▼
   Destination Payload
```

## Loss Accounting
Every transformation explicitly returns:
- Turns Preserved
- Tools Preserved
- Unsupported Events (Silent loss prevention)
