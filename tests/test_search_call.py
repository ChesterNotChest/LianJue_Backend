import os
from types import SimpleNamespace

import pytest

from config import LITELLM_MODEL_CONFIGS
from knowlion.abution_knowlion_driver import KnowLion


def test_search_call_formats_retrieval_and_calls_model(monkeypatch):
    captured = {}

    def fake_init(self, model_configs, graph_name, abution_url=None, username=None, password=None):
        self.graph_name = graph_name
        self.model = SimpleNamespace(
            call_text_model=lambda system_prompt, user_prompt, stream=False: captured.update(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                stream=stream,
            )
            or "mocked-answer"
        )

    monkeypatch.setattr(KnowLion, "__init__", fake_init)
    monkeypatch.setattr(
        KnowLion,
        "search",
        lambda self, text, top_k=10, classify_list=None: {
            "reasoning_paths": ["path-a"],
            "paragraphs": ["para-a"],
        },
    )

    knowlion = KnowLion({}, "graph_demo")
    result = knowlion.search_call("what is supervised learning", top_k=3, prompt="extra prompt", stream=False)

    assert result == "mocked-answer"
    assert "what is supervised learning" in captured["user_prompt"]
    assert "path-a" in captured["user_prompt"]
    assert "para-a" in captured["user_prompt"]
    assert captured["stream"] is False


@pytest.mark.llm
def test_search_call_uses_real_llm_when_enabled(monkeypatch):
    if os.getenv("RUN_LLM_TESTS") != "1":
        pytest.skip("Set RUN_LLM_TESTS=1 to run the real LLM search_call smoke test.")

    monkeypatch.setattr(
        KnowLion,
        "search",
        lambda self, text, top_k=10, classify_list=None: {
            "reasoning_paths": ["Supervised learning uses labeled examples."],
            "paragraphs": ["Learn a mapping from inputs to outputs from the training set."],
        },
    )

    knowlion = KnowLion(LITELLM_MODEL_CONFIGS or {}, "graph_demo")
    result = knowlion.search_call(
        "Explain supervised learning briefly.",
        top_k=3,
        prompt="Answer in two or three sentences.",
        stream=False,
    )

    assert isinstance(result, str)
    assert result.strip()
