"""A credential mangled by a bad paste must fail at import, not at request time.

Whitespace in SUPABASE_URL or SUPABASE_SERVICE_KEY is not rejected by anything
until httpx encodes it into a header, where it raises LocalProtocolError
("Illegal header value") on every request. That happens client-side, so nothing
reaches Supabase and nothing appears in its logs; the process starts, reports
healthy, and then fails everything it is asked to do. A single trailing space
does it.

The interesting half is the interior check. A shell that wraps a long paste puts
newlines in the middle of the value, where strip() removes nothing -- so a fix
that only stripped would leave the original failure exactly as it was.

These are pure unit tests: _clean is a plain function, and the import test runs
in a subprocess so nothing here can disturb the session's own client.
"""
import os
import subprocess
import sys

import pytest

from services.supabase_client import _clean

# A stand-in for a mangled credential. Nothing real is ever used here -- this is
# also what the "value must not be echoed" test greps for.
SENTINEL = "tainted-value-do-not-echo"


# ── Stripping: whitespace around the value ───────────────────────────────────

@pytest.mark.parametrize("raw", [
    "  abc",
    "abc  ",
    "\nabc\n",
    "\tabc\t",
    " \r\n abc \r\n ",
])
def test_surrounding_whitespace_is_stripped(raw):
    assert _clean("SUPABASE_SERVICE_KEY", raw) == "abc"


def test_a_clean_value_passes_through_untouched():
    value = "sb_secret_ExampleNotARealKey0123456789"
    assert _clean("SUPABASE_SERVICE_KEY", value) == value


def test_a_url_keeps_its_structure():
    url = "https://abcdefgh.supabase.co"
    assert _clean("SUPABASE_URL", url) == url


# ── The check that matters: whitespace inside the value ──────────────────────

@pytest.mark.parametrize("raw", [
    "ab cd",              # a space in the middle
    "ab\ncd",             # the wrapped paste this exists for
    "ab\r\ncd",           # the same from a Windows clipboard
    "ab\tcd",
    "  ab\ncd  ",         # surrounded AND interior: stripping is not enough
])
def test_interior_whitespace_is_rejected(raw):
    with pytest.raises(RuntimeError, match="whitespace inside"):
        _clean("SUPABASE_SERVICE_KEY", raw)


def test_stripping_alone_would_not_have_caught_it():
    """The point of the interior check, stated as an executable claim.

    If someone later 'simplifies' _clean down to raw.strip(), this fails.
    """
    wrapped = "sb_secret_first_half\nsecond_half"
    assert wrapped.strip() == wrapped, "premise: strip() changes nothing here"
    with pytest.raises(RuntimeError):
        _clean("SUPABASE_SERVICE_KEY", wrapped)


def test_the_error_names_the_variable():
    """So the message points at which of the two is wrong."""
    with pytest.raises(RuntimeError, match="SUPABASE_URL"):
        _clean("SUPABASE_URL", "https://a b.supabase.co")


def test_the_error_never_contains_the_value():
    """Startup errors get pasted into issues and chat logs."""
    with pytest.raises(RuntimeError) as excinfo:
        _clean("SUPABASE_SERVICE_KEY", f"{SENTINEL}\nwrapped")
    assert SENTINEL not in str(excinfo.value)


# ── It actually fires at import, not merely in a unit test ───────────────────

def _import_with(env_overrides):
    """Import services.supabase_client in a subprocess under a patched env.

    A subprocess rather than importlib.reload: reloading would build a second
    Supabase client inside the test session and leave services.auth holding a
    reference to the old one. This also tests what actually happens -- a process
    that refuses to start -- rather than an approximation of it.

    load_dotenv does not override variables already set, so an override here wins
    over backend/.env exactly as a real misconfiguration would.
    """
    env = {**os.environ, **env_overrides}
    return subprocess.run(
        [sys.executable, "-c", "import services.supabase_client"],
        cwd=os.path.join(os.path.dirname(__file__), ".."),
        env=env, capture_output=True, text=True, timeout=60,
    )


def test_a_tainted_key_stops_the_process_starting():
    result = _import_with({"SUPABASE_SERVICE_KEY": f"{SENTINEL}\nwrapped"})

    assert result.returncode != 0, "a mangled key started cleanly"
    assert "SUPABASE_SERVICE_KEY" in result.stderr
    assert "whitespace inside" in result.stderr


def test_a_tainted_url_stops_the_process_starting():
    result = _import_with({"SUPABASE_URL": "https://a b.supabase.co"})

    assert result.returncode != 0
    assert "SUPABASE_URL" in result.stderr


def test_the_startup_error_does_not_leak_the_value():
    """A crash-looping revision's logs are widely visible."""
    result = _import_with({"SUPABASE_SERVICE_KEY": f"{SENTINEL}\nwrapped"})

    assert SENTINEL not in result.stderr, "the mangled credential reached the logs"


def test_a_clean_environment_still_imports():
    """The guard must not reject the real configuration."""
    result = _import_with({})

    assert result.returncode == 0, f"import broke with a valid env:\n{result.stderr}"
