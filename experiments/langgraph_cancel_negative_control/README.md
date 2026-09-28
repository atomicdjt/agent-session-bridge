# LangGraph cancellation negative control

This no-model, local-only experiment separates a custom stream event observed by a consumer from state represented by a LangGraph SQLite checkpoint. It uses a synthetic event and makes no network calls or hosted Platform/API requests.

Run it with Python 3.10 or newer from the repository root:

```text
python -m venv .venv-langgraph-negative-control
# PowerShell / Windows:
.venv-langgraph-negative-control/Scripts/python.exe -m pip install -r experiments/langgraph_cancel_negative_control/requirements.txt
.venv-langgraph-negative-control/Scripts/python.exe experiments/langgraph_cancel_negative_control/repro.py
# macOS / Linux: replace the two executable paths above with
# .venv-langgraph-negative-control/bin/python
```

The script writes its sanitized result to `fixtures/runtime/langgraph-cancel-negative-control.result.json`. The result records the exact library versions, whether the stream event reached the consumer, and what a read-back from the SQLite checkpointer contains. It intentionally records no wall-clock observation timestamp or dynamic checkpoint identifier.

The expected boundary is:

```text
stream event observed by consumer
  -> consumer cancels before the node returns
  -> prior graph state remains readable
  -> the partial stream event is absent from that graph state
  -> observation = OBSERVED; checkpoint persistence = NOT_PROVEN; outcome = UNKNOWN
```

This is a negative control for evidence interpretation: it shows why visible stream output must not be promoted to checkpointed state or a successful outcome. It does **not** reproduce the hosted LangGraph Platform/API path in issue [#5672](https://github.com/langchain-ai/langgraph/issues/5672), prove a framework defect, or characterize every checkpointer, version, or application. LangGraph durability modes govern graph-state checkpoint writes; this experiment's custom stream payload is not a graph-state update.

The JSON result is not an ATIF document. In particular, ATIF v1.7 `ObservationResult` has no timestamp field; no timestamp is fabricated for the streamed event.
