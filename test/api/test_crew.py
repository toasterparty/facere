"""The threads recipes execute on, which the main thread waits for."""

import threading

import pytest

from facere._schedule import Crew


def test_thread_that_failed_to_start_is_not_waited_for(monkeypatch: pytest.MonkeyPatch) -> None:
    crew = Crew(lambda: 2)

    def refuse(thread: threading.Thread) -> None:
        raise RuntimeError("can't start new thread")

    with monkeypatch.context() as patch:
        patch.setattr(threading.Thread, "start", refuse)
        with pytest.raises(RuntimeError):
            crew.try_add(lambda: None)

    assert crew.wait(lambda: False) is True
