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

        def expander(self, label: str) -> Any:
            return nullcontext()

        def text_area(
            self, label: str, value: str | None, height: int, key: str
        ) -> str:
            assert value is None
            assert key in self.session_state
            if key not in self.session_state:
                self.session_state[key] = value
            return self.session_state[key]

        def button(self, label: str, disabled: bool = False, key: str = "") -> bool:
            return self.clicked and not disabled and key == "dashboard_ai_button"

        def spinner(self, label: str) -> Any:
            return nullcontext()

        def markdown(self, value: str) -> None:
            self.messages.append(value)

        def error(self, value: str) -> None:
            self.messages.append(value)

    calls: list[dict[str, Any]] = []

    def handle_analysis(
        summary: dict[str, Any], lang: str, model: str, prompt: str
    ) -> str:
        calls.append(summary)
        assert model == st.session_state["dashboard_ai_model"]
        assert prompt == st.session_state["dashboard_ai_prompt_en"]
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

    def handle_failure(
        summary: dict[str, Any], lang: str, model: str, prompt: str
    ) -> str:
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


@pytest.mark.parametrize("model", ai_analysis.ANALYSIS_MODELS)
@pytest.mark.parametrize(
    "configured, expected", [(None, 8192), ("", 8192), ("12000", 12000)]
)
def test_models_share_configured_token_budget(
    monkeypatch: pytest.MonkeyPatch,
    model: str,
    configured: str | None,
    expected: int,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    if configured is None:
        monkeypatch.delenv("OPENAI_MAX_OUTPUT_TOKENS", raising=False)
    else:
        monkeypatch.setenv("OPENAI_MAX_OUTPUT_TOKENS", configured)

    def handle_request(request: Any, timeout: int) -> Any:
        payload = json.loads(request.data)
        assert "reasoning" not in payload
        assert payload["max_output_tokens"] == expected
        assert payload["model"] == model
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
    assert ai_analysis.request_analysis({}, "en", model=model) == "insights"


@pytest.mark.parametrize(
    "lang, message", [("en", "output token limit"), ("ko", "출력 토큰 한도")]
)
def test_token_exhaustion_reports_specific_cause(
    monkeypatch: pytest.MonkeyPatch,
    lang: str,
    message: str,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    monkeypatch.setenv("OPENAI_MAX_OUTPUT_TOKENS", "12288")
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
    with pytest.raises(ai_analysis.AnalysisError, match=message) as caught:
        ai_analysis.request_analysis({}, lang, model="gpt-4.1-mini")
    assert "12288" in str(caught.value)
    assert "OPENAI_MAX_OUTPUT_TOKENS" in str(caught.value)


def test_explicit_model_is_sent_to_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")

    def handle_request(request: Any, timeout: int) -> Any:
        payload = json.loads(request.data)
        assert payload["model"] == "gpt-5-mini"
        assert "reasoning" not in payload
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
    from streamlit.elements.widgets import text_widgets
    from streamlit.testing.v1 import AppTest

    from solar_rs485_monitor import dashboard

    original_check = text_widgets.check_widget_policies

    def handle_widget_policies(*args: Any, **kwargs: Any) -> None:
        if str(args[1]).startswith("dashboard_ai_prompt_"):
            assert kwargs["default_value"] is None
        original_check(*args, **kwargs)

    monkeypatch.setattr(text_widgets, "check_widget_policies", handle_widget_policies)

    calls: list[str] = []
    prompts: list[str] = []

    def handle_analysis(
        summary: dict[str, Any], lang: str, model: str, prompt: str
    ) -> str:
        calls.append(model)
        prompts.append(prompt)
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
    app.button(key="dashboard_ai_button").click().run()
    assert not app.exception
    assert calls == ["gpt-5-mini"]
    assert prompts == [ai_analysis.get_default_analysis_prompt("en")]
    assert app.markdown[0].value == "Analysis using gpt-5-mini"
    app.selectbox[0].select("gpt-4.1").run()
    assert calls == ["gpt-5-mini"]
    assert any("Model: gpt-5-mini" in item.value for item in app.caption)
    app.button(key="dashboard_ai_button").click().run()
    assert not app.exception
    assert calls == ["gpt-5-mini", "gpt-4.1"]

    app.text_area[0].input("Compare output voltage fluctuations only.").run()
    assert len(calls) == 2
    assert any("prompt has changed" in caption.value for caption in app.caption)
    app.button(key="dashboard_ai_button").click().run()
    assert not app.exception
    assert prompts[-1] == "Compare output voltage fluctuations only."
    assert app.session_state["dashboard_ai_result"]["prompt"] == prompts[-1]
    app.button(key="dashboard_ai_prompt_reset").click().run()
    assert not app.exception
    assert app.text_area[0].value == ai_analysis.get_default_analysis_prompt("en")
    assert len(calls) == 3
    app.text_area[0].input("   ").run()
    assert app.button(key="dashboard_ai_button").disabled
    assert len(calls) == 3
    app.button(key="dashboard_ai_prompt_reset").click().run()

    monkeypatch.setattr(dashboard, "request_analysis", ai_analysis.request_analysis)
    monkeypatch.setenv("OPENAI_MAX_OUTPUT_TOKENS", "8192")
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
    app.button(key="dashboard_ai_button").click().run()
    assert not app.exception
    assert "output token limit" in app.error[0].value
    assert "8192" in app.error[0].value
    assert "OPENAI_MAX_OUTPUT_TOKENS" in app.error[0].value
    assert "Check the API key" not in app.error[0].value


@pytest.mark.parametrize("configured", ["invalid", "0", "-1", "1.5"])
def test_invalid_token_budget_does_not_call_api(
    monkeypatch: pytest.MonkeyPatch,
    configured: str,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    monkeypatch.setenv("OPENAI_MAX_OUTPUT_TOKENS", configured)

    def handle_unexpected_request(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Invalid configuration must not call the API")

    monkeypatch.setattr(ai_analysis, "urlopen", handle_unexpected_request)
    with pytest.raises(ai_analysis.AnalysisError, match="positive integer"):
        ai_analysis.request_analysis({}, "en", model="gpt-5-mini")


def test_custom_prompt_replaces_default_and_keeps_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    summary = {"loaded_rows": 10, "statistics": {"output_ac_power_w": {"mean": 500}}}
    prompt = "발전 출력이 급격히 변한 구간만 분석해줘."

    def handle_request(request: Any, timeout: int) -> Any:
        payload = json.loads(request.data)
        assert payload["instructions"] == prompt
        assert json.loads(payload["input"]) == summary
        assert (
            ai_analysis.get_default_analysis_prompt("ko") not in payload["instructions"]
        )
        return nullcontext(
            StringIO(
                json.dumps(
                    {
                        "status": "completed",
                        "output": [
                            {
                                "type": "message",
                                "content": [
                                    {"type": "output_text", "text": "분석 결과"},
                                ],
                            }
                        ],
                    }
                )
            )
        )

    monkeypatch.setattr(ai_analysis, "urlopen", handle_request)
    assert (
        ai_analysis.request_analysis(summary, "ko", "gpt-4.1-mini", prompt)
        == "분석 결과"
    )


@pytest.mark.parametrize("prompt", ["", "   "])
def test_empty_prompt_does_not_call_api(
    monkeypatch: pytest.MonkeyPatch,
    prompt: str,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")

    def handle_unexpected_request(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Empty prompt must not call the API")

    monkeypatch.setattr(ai_analysis, "urlopen", handle_unexpected_request)
    with pytest.raises(ai_analysis.AnalysisError, match="Enter an analysis prompt"):
        ai_analysis.request_analysis({}, "en", "gpt-4.1-mini", prompt)


def test_logout_clears_custom_prompts() -> None:
    from types import SimpleNamespace

    from solar_rs485_monitor import dashboard

    st = SimpleNamespace(
        session_state={
            "dashboard_ai_prompt_ko": "사용자 질문",
            "dashboard_ai_prompt_en": "Custom question",
            "dashboard_ai_result": {"prompt": "Custom question"},
        }
    )
    dashboard.clear_dashboard_auth_session(st)
    assert not st.session_state
