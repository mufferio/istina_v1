"""
Rate limiter tests.

Goal:
- Test that RateLimiter properly enforces request-per-minute limits
- Verify loop of N calls respects configured limits with proper delays
- Test edge cases and rolling window behavior
- Ensure thread-safety considerations are documented
"""

import pytest
import time
from unittest.mock import patch, MagicMock

from istina.utils.rate_limiter import RateLimiter, maybe_acquire


class TestRateLimiterBasics:
    """Test basic rate limiter functionality and validation."""

    def test_rate_limiter_creation_valid_params(self):
        """Test creating rate limiter with valid parameters."""
        limiter = RateLimiter(rpm=60)
        assert limiter.rpm == 60
        assert limiter.window_seconds == 60.0
        assert len(limiter._calls) == 0

    def test_rate_limiter_creation_custom_window(self):
        """Test creating rate limiter with custom window size."""
        limiter = RateLimiter(rpm=30, window_seconds=120.0)
        assert limiter.rpm == 30
        assert limiter.window_seconds == 120.0

    def test_rate_limiter_invalid_rpm(self):
        """Test that invalid RPM values raise ValueError."""
        with pytest.raises(ValueError, match="rpm must be a positive integer"):
            RateLimiter(rpm=0)
        
        with pytest.raises(ValueError, match="rpm must be a positive integer"):
            RateLimiter(rpm=-5)

    def test_rate_limiter_invalid_window(self):
        """Test that invalid window values raise ValueError."""
        with pytest.raises(ValueError, match="window_seconds must be > 0"):
            RateLimiter(rpm=60, window_seconds=0)
        
        with pytest.raises(ValueError, match="window_seconds must be > 0"):
            RateLimiter(rpm=60, window_seconds=-1)

    def test_maybe_acquire_with_none_limiter(self):
        """Test maybe_acquire helper with None limiter."""
        # Should not raise any exceptions
        maybe_acquire(None)
        
    def test_maybe_acquire_with_valid_limiter(self):
        """Test maybe_acquire helper with valid limiter."""
        limiter = RateLimiter(rpm=60)
        # Should not raise any exceptions
        maybe_acquire(limiter)
        # Should record the call
        assert len(limiter._calls) == 1


class TestRateLimiterFastCalls:
    """Test behavior when calls are under the limit."""

    def test_single_call_no_delay(self):
        """Test that single call passes through immediately."""
        limiter = RateLimiter(rpm=60)
        
        start_time = time.monotonic()
        limiter.acquire()
        end_time = time.monotonic()
        
        # Should be nearly instantaneous (less than 10ms)
        elapsed = end_time - start_time
        assert elapsed < 0.01
        assert len(limiter._calls) == 1

    def test_calls_under_limit_no_delay(self):
        """Test that calls under limit pass through quickly."""
        limiter = RateLimiter(rpm=10)  # 10 calls per minute
        
        start_time = time.monotonic()
        
        # Make 5 calls (under limit)
        for _ in range(5):
            limiter.acquire()
        
        end_time = time.monotonic()
        elapsed = end_time - start_time
        
        # Should be very fast (under 100ms for 5 calls)
        assert elapsed < 0.1
        assert len(limiter._calls) == 5


class TestRateLimiterRateLimitingBehavior:
    """Test core rate limiting and delay behavior."""

    def test_calls_over_limit_trigger_delay(self):
        """Test that calls over the limit are properly delayed."""
        # Use a very low limit and short window for faster testing
        limiter = RateLimiter(rpm=2, window_seconds=1.0)  # 2 calls per second
        
        start_time = time.monotonic()
        
        # Make 2 calls (at limit)
        limiter.acquire()
        limiter.acquire()
        
        # Third call should be delayed
        limiter.acquire()
        
        end_time = time.monotonic()
        elapsed = end_time - start_time
        
        # Should have been delayed by roughly 1 second
        assert elapsed >= 0.8  # Allow some timing variance
        assert elapsed < 1.5   # But not too much delay
        # After the delay, old calls may have been cleaned up from window
        assert len(limiter._calls) >= 1, "Should have at least the most recent call"

    @pytest.mark.slow
    def test_loop_of_n_calls_respects_limit(self):
        """**Main test requested by user**: Loop of N calls respects configured limit."""
        # Test with realistic but fast parameters
        rpm_limit = 6  # 6 calls per minute
        window_seconds = 10.0  # 10 second window for faster testing
        num_calls = 10
        
        limiter = RateLimiter(rpm=rpm_limit, window_seconds=window_seconds)
        
        start_time = time.monotonic()
        call_times = []
        
        # Make N calls in a loop
        for i in range(num_calls):
            before_call = time.monotonic()
            limiter.acquire()
            after_call = time.monotonic()
            call_times.append({
                'iteration': i,
                'before': before_call - start_time,
                'after': after_call - start_time,
                'delay': after_call - before_call
            })
        
        end_time = time.monotonic()
        total_elapsed = end_time - start_time
        
        # Verify the rate limiting behavior
        print(f"\\nRate limit test results:")
        print(f"RPM Limit: {rpm_limit}, Window: {window_seconds}s")
        print(f"Total calls: {num_calls}, Total time: {total_elapsed:.2f}s")
        
        # Calculate expected minimum time
        # For 10 calls at 6 RPM in 10s window:
        # - First 6 calls should be fast
        # - Remaining 4 calls should be delayed
        # - Minimum time should be roughly the time to clear the window
        calls_over_limit = max(0, num_calls - rpm_limit)
        if calls_over_limit > 0:
            # Should take at least some portion of the window duration
            expected_min_time = window_seconds * 0.3  # Conservative estimate
            assert total_elapsed >= expected_min_time, f"Expected at least {expected_min_time:.2f}s, got {total_elapsed:.2f}s"
        
        # Verify call timing pattern
        fast_calls = sum(1 for call in call_times if call['delay'] < 0.1)
        slow_calls = sum(1 for call in call_times if call['delay'] >= 0.1)
        
        print(f"Fast calls (< 0.1s delay): {fast_calls}")
        print(f"Slow calls (>= 0.1s delay): {slow_calls}")
        
        # Should have some fast calls (under limit) and potentially some slow calls (over limit)
        assert fast_calls <= rpm_limit or slow_calls > 0, "Rate limiting should activate when over limit" 
        # Total time should indicate rate limiting occurred 
        if calls_over_limit > 0:
            assert total_elapsed >= expected_min_time, f"Expected at least {expected_min_time:.2f}s for rate limiting, got {total_elapsed:.2f}s"
        
        # Verify final state - calls may have been cleaned up from rolling window
        # Just verify it has some recent calls (within window)
        assert len(limiter._calls) <= num_calls, "Should not have more calls than made"
        assert len(limiter._calls) > 0, "Should have some recent calls in window"

    def test_rolling_window_behavior(self):
        """Test that old calls expire from the rolling window.""" 
        limiter = RateLimiter(rpm=2, window_seconds=0.5)  # Very short window
        
        # Make calls at limit
        limiter.acquire()
        limiter.acquire()
        assert len(limiter._calls) == 2
        
        # Wait for window to expire
        time.sleep(0.6)
        
        # Next call should clean up expired calls and proceed quickly
        start_time = time.monotonic()
        limiter.acquire()
        end_time = time.monotonic()
        
        elapsed = end_time - start_time
        assert elapsed < 0.1, "Call should be fast after window expiry"
        # Should have cleaned up expired calls, leaving only the new one
        assert len(limiter._calls) == 1


class TestRateLimiterEdgeCases:
    """Test edge cases and error conditions."""

    def test_very_high_rpm_limit(self):
        """Test behavior with very high RPM limits."""
        limiter = RateLimiter(rpm=1000000)  # Very high limit
        
        start_time = time.monotonic()
        
        # Make many calls - should all be fast
        for _ in range(100):
            limiter.acquire()
        
        end_time = time.monotonic()
        elapsed = end_time - start_time
        
        # Should be very fast since limit is high
        assert elapsed < 0.5
        assert len(limiter._calls) == 100

    def test_rpm_limit_of_one(self):
        """Test behavior with RPM limit of 1."""
        limiter = RateLimiter(rpm=1, window_seconds=1.0)
        
        # First call should be fast
        start_time = time.monotonic()
        limiter.acquire()
        first_call_time = time.monotonic() - start_time
        assert first_call_time < 0.01
        
        # Second call should be delayed
        start_time = time.monotonic()
        limiter.acquire()
        second_call_time = time.monotonic() - start_time
        assert second_call_time >= 0.9  # Should wait nearly full window

    @patch('time.monotonic')  
    @patch('time.sleep')
    def test_time_handling_edge_cases(self, mock_sleep, mock_monotonic):
        """Test edge cases with time handling and window expiry."""
        # Mock time to control timing precisely
        # Test scenario: calls within limit, then a big time jump to test window cleanup
        mock_monotonic.side_effect = [
            0.0,    # acquire() #1 - start time  
            0.0,    # acquire() #1 - record time
            0.1,    # acquire() #2 - start time
            0.1,    # acquire() #2 - record time  
            65.0,   # acquire() #3 - start time (after window expiry)
            65.0    # acquire() #3 - record time
        ]
        
        # Don't actually sleep
        mock_sleep.return_value = None
        
        limiter = RateLimiter(rpm=3, window_seconds=60.0)  # 3 per minute
        
        # Make 2 calls within limit
        limiter.acquire()  # t=0.0
        limiter.acquire()  # t=0.1  
        assert len(limiter._calls) == 2
        
        # Time jumps to t=65.0 (past the 60s window)
        # This should clean up old calls automatically
        limiter.acquire()  # t=65.0
        
        # Should have cleaned up expired calls, leaving only the recent one
        assert len(limiter._calls) == 1

    def test_concurrent_window_cleanup(self):
        """Test that window cleanup works correctly during acquire."""
        limiter = RateLimiter(rpm=3, window_seconds=0.3)
        
        # Make calls to fill the limit
        limiter.acquire()
        limiter.acquire() 
        limiter.acquire()
        assert len(limiter._calls) == 3
        
        # Wait for partial expiry
        time.sleep(0.35)
        
        # Next acquire should clean up and allow call
        start_time = time.monotonic()
        limiter.acquire()
        end_time = time.monotonic()
        
        # Should be fast (no blocking)
        assert (end_time - start_time) < 0.1


class TestRateLimiterIntegrationScenarios:
    """Test realistic integration scenarios."""

    def test_api_provider_simulation(self):
        """Simulate realistic API provider usage pattern."""
        # Simulate a provider that makes API calls with rate limiting
        limiter = RateLimiter(rpm=30, window_seconds=10.0)  # 30 calls per 10 seconds
        
        call_delays = []
        total_start = time.monotonic()
        
        # Simulate analyzing a batch of articles
        for i in range(15):  # Half the limit
            call_start = time.monotonic()
            limiter.acquire()
            # Simulate API call time
            time.sleep(0.01)  # 10ms simulated API latency
            call_end = time.monotonic()
            
            call_delays.append(call_end - call_start)
        
        total_end = time.monotonic()
        total_time = total_end - total_start
        
        # Most calls should be fast since we're under the limit
        fast_calls = sum(1 for delay in call_delays if delay < 0.1)
        assert fast_calls >= 10, "Most calls should be fast when under limit"
        
        # Total time should be reasonable
        assert total_time < 5.0, "Should complete quickly when under limit"

    def test_burst_then_steady_pattern(self):
        """Test burst of calls followed by steady pattern."""
        limiter = RateLimiter(rpm=4, window_seconds=2.0)
        
        # Burst: make calls up to limit quickly
        burst_start = time.monotonic()
        for _ in range(4):
            limiter.acquire()
        burst_end = time.monotonic()
        
        burst_time = burst_end - burst_start
        assert burst_time < 0.1, "Burst should be fast"
        
        # Now make additional calls that should be rate limited
        steady_delays = []
        for _ in range(3):
            call_start = time.monotonic()
            limiter.acquire()
            call_end = time.monotonic()
            steady_delays.append(call_end - call_start)
        
        # These calls should have been delayed
        delayed_calls = sum(1 for delay in steady_delays if delay >= 0.1)
        assert delayed_calls > 0, "Should have some delayed calls after burst"


if __name__ == "__main__":
    # Quick manual test for demonstration
    print("Manual Rate Limiter Test")
    print("=" * 40)
    
    limiter = RateLimiter(rpm=3, window_seconds=2.0)
    
    print(f"Testing {limiter.rpm} RPM with {limiter.window_seconds}s window")
    print("Making 5 calls...")
    
    for i in range(5):
        start = time.monotonic()
        limiter.acquire()
        end = time.monotonic()
        delay = end - start
        
        print(f"Call {i+1}: {delay:.3f}s delay, calls in window: {len(limiter._calls)}")
    
    print("\\nTest completed!")
    print("Expected: first 3 calls fast, remaining calls delayed")