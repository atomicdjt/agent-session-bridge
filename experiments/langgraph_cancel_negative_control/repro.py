"""Show that a consumer-observed custom stream event is not graph state."""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import tempfile
from importlib.metadata import version
from pathlib import Path
from typing import TypedDict

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

THREAD_ID = "tfb-langgraph-negative-control"
SEED_MESSAGE = "synthetic checkpoint state from before cancellation"
PARTIAL_MESSAGE = "synthetic partial output observed before cancellation"


class GraphState(TypedDict, total=False):
    mode: str
    messages: list[str]


def seed_state(_: GraphState) -> dict[str, list[str]]:
    return {"messages": [SEED_MESSAGE]}


async def emit_then_wait(_: GraphState) -> dict[str, list[str]]:
    writer = get_stream_writer()
    writer(
        {
            "run_id": "lg-negative-control-run-001",
            "run_generation": 1,
            "stream_seq": 1,
            "kind": "partial_output",
            "text": PARTIAL_MESSAGE,
        }
    )
    await asyncio.Event().wait()
    return {"messages": [PARTIAL_MESSAGE]}


def compile_graph(checkpointer: AsyncSqliteSaver):
    builder = StateGraph(GraphState)
    builder.add_node("seed", seed_state)
    builder.add_node("stream", emit_then_wait)
    builder.add_conditional_edges(
        START,
        lambda state: "stream" if state.get("mode") == "stream" else "seed",
        {"seed": "seed", "stream": "stream"},
    )
    builder.add_edge("seed", END)
    builder.add_edge("stream", END)
    return builder.compile(checkpointer=checkpointer)


async def reproduce() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="tfb-langgraph-control-") as temp_dir:
        database = Path(temp_dir) / "checkpoint.sqlite"
        async with AsyncSqliteSaver.from_conn_string(str(database)) as checkpointer:
            graph = compile_graph(checkpointer)
            config = {"configurable": {"thread_id": THREAD_ID}}

            await graph.ainvoke({"mode": "seed"}, config, durability="sync")
            before = await graph.aget_state(config)
            before_messages = before.values.get("messages", [])
            if before_messages != [SEED_MESSAGE]:
                raise AssertionError("Could not read back the seed checkpoint.")

            observed: list[dict[str, object]] = []
            event_seen = asyncio.Event()

            async def consume_stream() -> None:
                async for mode, payload in graph.astream(
                    {"mode": "stream"},
                    config,
                    stream_mode=["custom"],
                    durability="sync",
                ):
                    if mode == "custom":
                        observed.append(payload)
                        event_seen.set()
                        # Hold the consumer at the exact observation boundary.
                        await asyncio.Event().wait()

            task = asyncio.create_task(consume_stream())
            await asyncio.wait_for(event_seen.wait(), timeout=10)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            after = await graph.aget_state(config)
            after_messages = after.values.get("messages", [])
            checkpoint_contains_partial = PARTIAL_MESSAGE in after_messages
            if after_messages != before_messages or checkpoint_contains_partial:
                raise AssertionError(
                    "The negative control changed checkpoint state unexpectedly."
                )
            if len(observed) != 1 or observed[0].get("text") != PARTIAL_MESSAGE:
                raise AssertionError("The consumer did not observe the expected event.")

            return {
                "schema": "tfb.runtime-boundary-observation.v1",
                "case": "langgraph-visible-stream-cancel-before-state-checkpoint",
                "runtime": {
                    "python": platform.python_version(),
                    "langgraph": version("langgraph"),
                    "langgraph-checkpoint-sqlite": version(
                        "langgraph-checkpoint-sqlite"
                    ),
                    "checkpointer": "AsyncSqliteSaver",
                    "durability": "sync",
                    "model_or_external_api": False,
                },
                "run_identity": {
                    "thread_id": THREAD_ID,
                    "run_id": "lg-negative-control-run-001",
                    "run_generation": 1,
                },
                "observation": {
                    "stream_seq": 1,
                    "kind": "partial_output",
                    "consumer_observed": len(observed) == 1,
                    "observed_at_utc": None,
                    "timestamp_status": "not captured",
                },
                "cancellation": {
                    "requested_after_observation": True,
                    "node_returned": False,
                },
                "checkpoint_readback": {
                    "prior_state_readable": after_messages == before_messages,
                    "messages": after_messages,
                    "contains_partial_stream_output": checkpoint_contains_partial,
                },
                "classification": {
                    "observation": "OBSERVED",
                    "checkpoint_persistence": "NOT_PROVEN",
                    "outcome": "UNKNOWN",
                },
                "scope": (
                    "Local LangGraph graph plus SQLite checkpointer only; this does "
                    "not reproduce LangGraph Platform/API issue #5672."
                ),
            }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("fixtures/runtime/langgraph-cancel-negative-control.result.json"),
    )
    args = parser.parse_args()
    result = asyncio.run(reproduce())
    output = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output, encoding="utf-8")
    print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
