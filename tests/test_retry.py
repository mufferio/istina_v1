"""
Unit tests for the retry utility.

Covers:
- Successful call on first attempt
- Retry on failure then success
- Exhausts all attempts and re-raises
- Respects max_attempts
- Exponential backoff delay schedule
- max_delay cap is respected
- Non-retryable exceptions are not caught
- Argument validation (max_attempts, base_delay, backoff_factor, max_delay)
- base_delay=0 skips sleep
"""
import pytest
from istina.utils.retry import retry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class Flaky:
    """Callable that fails a fixed number of times before succeeding."""
    def __init__(self, fail_times: int, exc: Exception = RuntimeError("fail")):
        self.fail_times = fail_times
        self.exc = exc
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise self.exc
        return "ok"


def no_sleep(delay: float) -> None:
    """Drop-in sleep replacement that does nothing."""
    pass


def recording_sleep(delays: list):
    """Returns a sleep function that records delays it was called with."""
    def _sleep(delay: float) -> None:
        delays.append(delay)
    return _sleep


# ---------------------------------------------------------------------------
# Success cases
# ---------------------------------------------------------------------------

def test_succeeds_on_first_attempt():
    fn = Flaky(fail_times=0)
    result = retry(fn, sleep=no_sleep)
    assert result == "ok"
    assert fn.calls == 1


def test_succeeds_on_second_attempt():
    fn = Flaky(fail_times=1)
    result = retry(fn, max_attempts=3, sleep=no_sleep)
    assert result == "ok"
    assert fn.calls == 2


def test_succeeds_on_last_attempt():
    fn = Flaky(fail_times=2)
    result = retry(fn, max_attempts=3, sleep=no_sleep)
    assert result == "ok"
    assert fn.calls == 3


# ---------------------------------------------------------------------------
# Failure cases
# ---------------------------------------------------------------------------

def test_raises_after_all_attempts_exhausted():
    fn = Flaky(fail_times=5)
    with pytest.raises(RuntimeError, match="fail"):
        retry(fn, max_attempts=3, sleep=no_sleep)
    assert fn.calls == 3


def test_reraises_original_exception_type():
    class CustomError(Exception):
        pass

    fn = Flaky(fail_times=5, exc=CustomError("boom"))
    with pytest.raises(CustomError, match="boom"):
        retry(fn, exceptions=(CustomError,), max_attempts=2, sleep=no_sleep)


def test_non_retryable_exception_propagates_immediately():
    """Exceptions not in the `exceptions` tuple should not be caught."""
    def fn():
        raise ValueError("not retryable")

    with pytest.raises(ValueError, match="not retryable"):
        retry(fn, exceptions=(RuntimeError,), max_attempts=5, sleep=no_sleep)


# ---------------------------------------------------------------------------
# Delay / backoff
# ---------------------------------------------------------------------------

def test_sleep_called_between_retries():
    delays = []
    fn = Flaky(fail_times=2)
    retry(fn, max_attempts=3, base_delay=1.0, backoff_factor=2.0, sleep=recording_sleep(delays))
    # 2 failures -> 2 sleeps (but last attempt doesn't sleep)
    assert len(delays) == 2


def test_exponential_backoff_schedule():
    delays = []
    fn = Flaky(fail_times=3)
    retry(
        fn,
        max_attempts=4,
        base_delay=1.0,
        backoff_factor=2.0,
        max_delay=100.0,
        sleep=recording_sleep(delays),
    )
    assert delays == [1.0, 2.0, 4.0]


def test_max_delay_cap_is_respected():
    delays = []
    fn = Flaky(fail_times=4)
    retry(
        fn,
        max_attempts=5,
        base_delay=1.0,
        backoff_factor=10.0,
        max_delay=5.0,
        sleep=recording_sleep(delays),
    )
    assert all(d <= 5.0 for d in delays)


def test_base_delay_zero_never_calls_sleep():
    delays = []
    fn = Flaky(fail_times=2)
    retry(fn, max_attempts=3, base_delay=0.0, sleep=recording_sleep(delays))
    assert delays == []


# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------

def test_max_attempts_less_than_1_raises():
    with pytest.raises(ValueError, match="max_attempts"):
        retry(lambda: None, max_attempts=0)


def test_base_delay_negative_raises():
    with pytest.raises(ValueError, match="base_delay"):
        retry(lambda: None, base_delay=-1.0)


def test_backoff_factor_less_than_1_raises():
    with pytest.raises(ValueError, match="backoff_factor"):
        retry(lambda: None, backoff_factor=0.5)


def test_max_delay_negative_raises():
    with pytest.raises(ValueError, match="max_delay"):
        retry(lambda: None, max_delay=-1.0)


# ---------------------------------------------------------------------------
# Return value
# ---------------------------------------------------------------------------

def test_return_value_is_passed_through():
    result = retry(lambda: {"key": "value"}, sleep=no_sleep)
    assert result == {"key": "value"}


def test_max_attempts_1_no_retry_on_failure():
    fn = Flaky(fail_times=1)
    with pytest.raises(RuntimeError):
        retry(fn, max_attempts=1, sleep=no_sleep)
    assert fn.calls == 1
