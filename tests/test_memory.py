from simple_agent.memory import Memory


class TestMemory:
    def test_add_and_get_recent(self):
        mem = Memory(window=5)
        mem.add("user", "hello")
        mem.add("agent", "hi there")
        recent = mem.get_recent()
        assert len(recent) == 2
        assert recent[0].content == "hello"
        assert recent[1].content == "hi there"

    def test_window_limits_recent(self):
        mem = Memory(window=3)
        for i in range(5):
            mem.add("user", f"msg {i}")
        recent = mem.get_recent()
        assert len(recent) == 3
        assert recent[0].content == "msg 2"

    def test_compact_context(self):
        mem = Memory()
        mem.add("user", "hello")
        mem.add("agent", "world")
        ctx = mem.compact_context()
        assert "[user] hello" in ctx
        assert "[agent] world" in ctx

    def test_compact_context_empty(self):
        mem = Memory()
        ctx = mem.compact_context()
        assert "no prior context" in ctx

    def test_clear(self):
        mem = Memory()
        mem.add("user", "test")
        mem.clear()
        assert len(mem) == 0

    def test_len(self):
        mem = Memory()
        assert len(mem) == 0
        mem.add("user", "a")
        mem.add("agent", "b")
        assert len(mem) == 2

    def test_empty_content_ignored(self):
        mem = Memory()
        mem.add("user", "")
        assert len(mem) == 0
