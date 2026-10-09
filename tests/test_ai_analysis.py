import json
from contextlib import nullcontext
from datetime import datetime, timezone
from io import StringIO
from typing import Any
from urllib.error import HTTPError, URLError

import pandas as pd
import pytest

from solar_rs485_monitor import ai_analysis


def test_summary_is_bounded_and_excludes_sensitive_columns() -> None:
    timestamps = pd.date_range("2026-01-01", periods=250, freq="2min", tz="UTC")
    df = pd.DataFrame(
        {
            "timestamp": timestamps,
            "output_ac_power_w": [float("inf"), float("nan"), *range(248)],
            "raw_frame_hex": "private",
            "inverter_name": "private",
        }
    )
    since = datetime(2026, 1, 1, tzinfo=timezone.utc)
    summary = ai_analysis.build_analysis_summary(
        df,
        ["output_ac_power_w"],
        since,
        since,
        60,
        250,
        pd.DataFrame({"timestamp": timestamps, "value": range(250)}),
        None,
    )
    encoded = json.dumps(summary, allow_nan=False)
    assert "private" not in encoded
    assert len(summary["time_samples"]) == 48
    assert summary["time_samples"][0]["output_ac_power_w"] is None
    assert summary["time_samples"][-1]["output_ac_power_w"] == 247
    assert summary["statistics"]["output_ac_power_w"]["missing"] == 2
    assert len(summary["daily_generation_recent_90"]) == 90
    assert summary["possibly_limited"]
    assert summary["gaps_over_bucket"] == 249
    assert summary["recent_events"] is None


def test_request_uses_server_key_and_extracts_only_output_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")

    def handle_request(request: Any, timeout: int) -> Any:
        payload = json.loads(request.data)
        assert timeout == 60
        assert request.full_url == "https://api.openai.com/v1/responses"
        assert request.get_header("Authorization") == "Bearer test-secret"
        assert payload["store"] is False
        assert payload["model"] == "test-model"
        assert "test-secret" not in request.data.decode()
        assert "Korean" in payload["instructions"]
        return nullcontext(
            StringIO(
                json.dumps(
                    {
                        "status": "completed",
                        "output": [
                            {"type": "reasoning"},
                            {
                                "type": "message",
                                "content": [
                                    {"type": "output_text", "text": "분석 결과"},
                                ],
                            },
                        ],
                    }
                )
            )
        )

    monkeypatch.setattr(ai_analysis, "urlopen", handle_request)
    assert (
        ai_analysis.request_analysis({"loaded_rows": 10}, "ko", model="test-model")
        == "분석 결과"
    )


@pytest.mark.parametrize(
    "error",
    [
        HTTPError("https://api.openai.com", 401, "private", {}, None),
        URLError("private test-secret"),
        TimeoutError("private test-secret"),
    ],
)
def test_api_errors_do_not_expose_secrets(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")

    def handle_request(*args: Any, **kwargs: Any) -> None:
        raise error

    monkeypatch.setattr(ai_analysis, "urlopen", handle_request)
    with pytest.raises(RuntimeError) as caught:
        ai_analysis.request_analysis({}, "en", model="gpt-4.1-mini")
    assert "test-secret" not in str(caught.value)
    assert "private" not in str(caught.value)


@pytest.mark.parametrize(
    "result",
    [
        {"status": "incomplete", "output": []},
        {"status": "completed", "output": []},
    ],
)
def test_incomplete_or_empty_response_is_rejected(
    monkeypatch: pytest.MonkeyPatch, result: dict[str, Any]
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    monkeypatch.setattr(
        ai_analysis,
        "urlopen",
        lambda *args, **kwargs: nullcontext(StringIO(json.dumps(result))),
    )
    with pytest.raises(RuntimeError):
        ai_analysis.request_analysis({}, "en", model="gpt-4.1-mini")


def test_missing_key_does_not_call_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        ai_analysis.request_analysis({}, "ko", model="gpt-4.1-mini")


def test_dashboard_refresh_retains_result_without_another_api_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from solar_rs485_monitor import dashboard

    class DashboardStub:
        def __init__(self) -> None:
            self.session_state: dict[str, Any] = {}
            self.clicked = True
            self.messages: list[str] = []

        def subheader(self, value: str) -> None:
            pass

        def caption(self, value: str) -> None:
            self.messages.append(value)

        def columns(self, sizes: list[int]) -> list[Any]:
            return [nullcontext() for _ in sizes]

        def selectbox(
            self, label: str, options: list[str], index: int, key: str
        ) -> str:
            if key not in self.session_state:
                self.session_state[key] = options[index]
            return self.session_state[key]

        def button(self, label: str, disabled: bool, key: str) -> bool:
            return self.clicked and not disabled

        def spinner(self, label: str) -> Any:
            return nullcontext()

        def markdown(self, value: str) -> None:
            self.messages.append(value)

        def error(self, value: str) -> None:
            self.messages.append(value)

    calls: list[dict[str, Any]] = []

    def handle_analysis(summary: dict[str, Any], lang: str, model: str) -> str:
        calls.append(summary)
        assert model == st.session_state["dashboard_ai_model"]
        return "insights"

    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    monkeypatch.setattr(dashboard, "request_analysis", handle_analysis)
    st = DashboardStub()
    since = datetime(2026, 1, 1, tzinfo=timezone.utc)
    df = pd.DataFrame({"timestamp": [since], "output_ac_power_w": [100]})
    args = (
        st,
        df,
        None,
        None,
        "MariaDB",
        since,
        since,
        60,
        100,
        dashboard.UI_TEXT["en"],
        "en",
    )
    dashboard.render_ai_analysis(*args)
    assert len(calls) == 1
    assert st.session_state["dashboard_ai_result"]["result"] == "insights"
    assert st.session_state["dashboard_ai_result"]["model"] == "gpt-4.1-mini"
    assert st.session_state["dashboard_ai_model"] == "gpt-4.1-mini"
    st.clicked = False
    st.session_state["dashboard_ai_model"] = "gpt-5-mini"
    dashboard.render_ai_analysis(*args)
    assert len(calls) == 1
    assert st.messages.count("insights") == 2
    assert st.session_state["dashboard_ai_model"] == "gpt-5-mini"
    assert st.messages[-2].startswith("Model: gpt-4.1-mini · ")

    def handle_failure(summary: dict[str, Any], lang: str, model: str) -> str:
        raise ai_analysis.AnalysisError(
            "OpenAI analysis reached the output token limit."
        )

    monkeypatch.setattr(dashboard, "request_analysis", handle_failure)
    st.clicked = True
    dashboard.render_ai_analysis(*args)
    assert any("output token limit" in message for message in st.messages)
    assert st.session_state["dashboard_ai_result"]["model"] == "gpt-4.1-mini"
    st.clicked = False
    dashboard.render_ai_analysis(*args[:7], 120, *args[8:])
    assert "dashboard_ai_result" not in st.session_state
    assert len(calls) == 1


def test_gpt5_mini_has_budget_for_reasoning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")

    def handle_request(request: Any, timeout: int) -> Any:
        payload = json.loads(request.data)
        assert payload["reasoning"] == {"effort": "low"}
        assert payload["max_output_tokens"] == 8000
        return nullcontext(
            StringIO(
                json.dumps(
                    {
                        "status": "completed",
                        "output": [
                            {
                                "type": "message",
                                "content": [
                                    {"type": "output_text", "text": "insights"},
                                ],
                            }
                        ],
                    }
                )
            )
        )

    monkeypatch.setattr(ai_analysis, "urlopen", handle_request)
    assert ai_analysis.request_analysis({}, "en", model="gpt-5-mini") == "insights"


def test_token_exhaustion_reports_specific_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    monkeypatch.setattr(
        ai_analysis,
        "urlopen",
        lambda *args, **kwargs: nullcontext(
            StringIO(
                json.dumps(
                    {
                        "status": "incomplete",
                        "incomplete_details": {"reason": "max_output_tokens"},
                        "output": [],
                    }
                )
            )
        ),
    )
    with pytest.raises(RuntimeError, match="output token limit"):
        ai_analysis.request_analysis({}, "en", model="gpt-4.1-mini")


def test_explicit_model_is_sent_to_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")

    def handle_request(request: Any, timeout: int) -> Any:
        payload = json.loads(request.data)
        assert payload["model"] == "gpt-5-mini"
        assert payload["reasoning"] == {"effort": "low"}
        return nullcontext(
            StringIO(
                json.dumps(
                    {
                        "status": "completed",
                        "output": [
                            {
                                "type": "message",
                                "content": [
                                    {"type": "output_text", "text": "insights"},
                                ],
                            }
                        ],
                    }
                )
            )
        )

    monkeypatch.setattr(ai_analysis, "urlopen", handle_request)
    assert ai_analysis.request_analysis({}, "en", model="gpt-5-mini") == "insights"


def test_streamlit_model_selection_only_calls_api_on_click(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from streamlit.testing.v1 import AppTest

    from solar_rs485_monitor import dashboard

    calls: list[str] = []

    def handle_analysis(summary: dict[str, Any], lang: str, model: str) -> str:
        calls.append(model)
        return f"Analysis using {model}"

    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    monkeypatch.setattr(dashboard, "request_analysis", handle_analysis)
    app = AppTest.from_string("""
import streamlit as st
import pandas as pd
from datetime import datetime, timezone
from solar_rs485_monitor.dashboard import render_ai_analysis, UI_TEXT
since = datetime(2026, 1, 1, tzinfo=timezone.utc)
df = pd.DataFrame({"timestamp": [since], "output_ac_power_w": [100]})
render_ai_analysis(st, df, None, None, "MariaDB", since, since,
                   60, 100, UI_TEXT["en"], "en")
""").run()
    assert not app.exception
    assert app.selectbox[0].value == "gpt-4.1-mini"
    app.selectbox[0].select("gpt-5-mini").run()
    assert not calls
    app.button[0].click().run()
    assert not app.exception
    assert calls == ["gpt-5-mini"]
    assert app.markdown[0].value == "Analysis using gpt-5-mini"
    app.selectbox[0].select("gpt-4.1").run()
    assert calls == ["gpt-5-mini"]
    assert any("Model: gpt-5-mini" in item.value for item in app.caption)
    app.button[0].click().run()
    assert not app.exception
    assert calls == ["gpt-5-mini", "gpt-4.1"]
