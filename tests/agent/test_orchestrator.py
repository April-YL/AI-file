from agent.orchestrator import WorkbookQcOrchestrator


def test_orchestrator_dispatches_once_with_same_context_and_options():
    calls = []
    context = object()

    def core_runner(received_context, **kwargs):
        calls.append((received_context, kwargs))
        return "report"

    orchestrator = WorkbookQcOrchestrator(core_runner=core_runner)

    result = orchestrator.run(context, llm=False, delivery_context=None)

    assert result == "report"
    assert len(calls) == 1
    assert calls[0][0] is context
    assert calls[0][1]["llm"] is False
    assert calls[0][1]["delivery_context"] is None
    assert calls[0][1]["llm_config"].enabled is False
    assert calls[0][1]["llm_router"].config is calls[0][1]["llm_config"]
