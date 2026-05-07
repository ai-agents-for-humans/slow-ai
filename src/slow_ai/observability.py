"""
LLM request/response observability.

Wraps every pydantic-ai agent with OpenTelemetry via InstrumentedModel.
Spans are exported to the Python logger as structured JSON — no external
service required. Works for all providers (Google, Anthropic, Ollama).

Call setup_llm_logging() once at startup in both the app and the runner.
"""

import json
import logging
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult

logger = logging.getLogger("slow_ai.llm")


class _LLMSpanExporter(SpanExporter):
    """Routes pydantic-ai GenAI spans to the Python logger as JSONL."""

    def export(self, spans: Any) -> SpanExportResult:
        for span in spans:
            attrs = dict(span.attributes or {})
            if "gen_ai.request.model" not in attrs:
                continue

            duration_ms = (
                (span.end_time - span.start_time) // 1_000_000
                if span.end_time and span.start_time
                else None
            )

            record: dict[str, Any] = {
                "event": "llm_call",
                "span": span.name,
                "model": attrs.get("gen_ai.request.model"),
                "provider": attrs.get("gen_ai.system"),
                "input_tokens": attrs.get("gen_ai.usage.input_tokens"),
                "output_tokens": attrs.get("gen_ai.usage.output_tokens"),
                "duration_ms": duration_ms,
            }

            # Full message content when include_content=True
            raw_input = attrs.get("gen_ai.input.messages")
            raw_output = attrs.get("gen_ai.output.messages")
            if raw_input:
                try:
                    record["input"] = json.loads(raw_input)
                except Exception:
                    record["input"] = raw_input
            if raw_output:
                try:
                    record["output"] = json.loads(raw_output)
                except Exception:
                    record["output"] = raw_output

            logger.info(json.dumps(record, ensure_ascii=False))

        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return True


def setup_llm_logging(include_content: bool = True) -> None:
    """Instrument all pydantic-ai agents and route spans to the logger.

    Args:
        include_content: Log full prompt/response content in addition to
            token counts. Set False in production if prompts are sensitive.
    """
    from pydantic_ai import Agent
    from pydantic_ai.models.instrumented import InstrumentationSettings

    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(_LLMSpanExporter()))
    trace.set_tracer_provider(provider)

    Agent.instrument_all(InstrumentationSettings(include_content=include_content))
    logger.info(json.dumps({"event": "llm_logging_configured", "include_content": include_content}))
