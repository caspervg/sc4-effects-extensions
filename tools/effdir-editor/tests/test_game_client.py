from effdir_editor.game_client import make_command, quote_argument, send_command


def test_game_command_quotes_paths_with_spaces():
    assert make_command("EffectsLoadFx", r"C:\My Effects\preview.fx") == (
        'EffectsLoadFx "C:\\My Effects\\preview.fx"'
    )


def test_game_command_leaves_simple_values_unquoted():
    assert make_command("EffectsPreviewTransform", 1, 2.5, -3) == "EffectsPreviewTransform 1 2.5 -3"


def test_game_command_rejects_unrepresentable_quote():
    try:
        quote_argument('bad"name')
    except ValueError:
        pass
    else:
        raise AssertionError("a quote must not be emitted ambiguously")


def test_game_command_posts_to_sc4(monkeypatch):
    class Response:
        status = 200
        reason = "OK"

        def read(self):
            return b"ok"

    class Connection:
        def __init__(self, host, port, timeout):
            assert (host, port, timeout) == ("127.0.0.1", 50020, 30.0)

        def request(self, method, path, body):
            assert (method, path, body) == ("POST", "/", b"EffectsStatus")

        def getresponse(self):
            return Response()

        def close(self):
            pass

    monkeypatch.setattr("effdir_editor.game_client.http.client.HTTPConnection", Connection)
    assert send_command("EffectsStatus") == "ok"


def test_game_command_extracts_http_result(monkeypatch):
    class Response:
        status = 200
        reason = "OK"

        def read(self):
            return b'Command:\n   EffectsStatus\nResult:\n   "city=1" 0'

    class Connection:
        def __init__(self, *_args, **_kwargs):
            pass

        def request(self, *_args, **_kwargs):
            pass

        def getresponse(self):
            return Response()

        def close(self):
            pass

    monkeypatch.setattr("effdir_editor.game_client.http.client.HTTPConnection", Connection)
    assert send_command("EffectsStatus") == '"city=1" 0'


def test_game_command_connection_error_mentions_required_argument(monkeypatch):
    class Connection:
        def __init__(self, *_args, **_kwargs):
            pass

        def request(self, *_args, **_kwargs):
            raise ConnectionRefusedError("refused")

        def close(self):
            pass

    monkeypatch.setattr("effdir_editor.game_client.http.client.HTTPConnection", Connection)
    try:
        send_command("EffectsStatus")
    except ConnectionError as exc:
        assert "-NetCommandGenerator:enabled" in str(exc)
    else:
        raise AssertionError("connection failure must be reported")


def test_game_command_rejects_non_ascii_before_connecting():
    try:
        send_command("EffectsLoadFx café.fx")
    except ValueError:
        pass
    else:
        raise AssertionError("the SC4 wire protocol is ASCII-only")
