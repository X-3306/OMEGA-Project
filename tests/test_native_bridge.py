from omega_protocol.native_bridge import NativeBridge


def test_native_bridge_falls_back_when_dll_is_missing(monkeypatch):
    monkeypatch.setattr("omega_protocol.native_bridge.native_dll_candidates", lambda: [])

    bridge = NativeBridge()

    assert bridge.state.available is False
    ok, message = bridge.sanitize_file("C:\\missing.bin", dry_run=True)
    assert ok is False
    assert "not found" in message.lower() or "fallback" in message.lower()
