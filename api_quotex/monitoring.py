"""Enhanced Error Handling and Monitoring for Quotex API"""
import asyncio
import time
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
from collections import defaultdict, deque
from loguru import logger

logger.remove()
log_filename = f"log-{time.strftime('%Y-%m-%d')}.txt"
logger.add(log_filename, level="INFO", encoding="utf-8", backtrace=True, diagnose=True)

class ErrorSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class ErrorCategory(Enum):
    CONNECTION = "connection"
    AUTHENTICATION = "authentication"
    TRADING = "trading"
    DATA = "data"
    SYSTEM = "system"
    RATE_LIMIT = "rate_limit"
    INSUFFICIENT_FUNDS = "insufficient_funds"
    BASE64_DECODE = "base64_decode"

@dataclass
class ErrorEvent:
    timestamp: datetime
    error_type: str
    severity: ErrorSeverity
    category: ErrorCategory
    message: str
    context: Dict[str, Any]
    stack_trace: Optional[str] = None
    resolved: bool = False
    resolution_time: Optional[datetime] = None

@dataclass
class PerformanceMetrics:
    timestamp: datetime
    operation: str
    duration: float
    success: bool
    memory_usage: Optional[int] = None
    cpu_usage: Optional[float] = None
    active_connections: int = 0

class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: type = Exception,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"

    async def call(self, func: Callable, *args, **kwargs):
        if self.state == "OPEN":
            if time.time() - self.last_failure_time < self.recovery_timeout:
                raise Exception("Circuit breaker is OPEN")
            else:
                self.state = "HALF_OPEN"
        try:
            result = await func(*args, **kwargs)
            self.on_success()
            return result
        except self.expected_exception as e:
            self.on_failure()
            raise e

    def on_success(self):
        self.failure_count = 0
        self.state = "CLOSED"

    def on_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning(f"Circuit breaker opened after {self.failure_count} failures")

class RetryPolicy:
    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter

    async def execute(self, func: Callable, *args, **kwargs):
        import random
        last_exception = None
        for attempt in range(self.max_attempts):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                if attempt == self.max_attempts - 1:
                    break
                delay = min(self.base_delay * (self.exponential_base**attempt), self.max_delay)
                if self.jitter:
                    delay *= 0.5 + random.random() * 0.5
                logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay:.2f}s")
                await asyncio.sleep(delay)
        raise last_exception

class ErrorMonitor:
    def __init__(
        self, max_errors: int = 1000, alert_threshold: int = 10, alert_window: int = 300
    ):
        self.max_errors = max_errors
        self.alert_threshold = alert_threshold
        self.alert_window = alert_window
        self.errors: deque = deque(maxlen=max_errors)
        self.error_counts: Dict[str, int] = defaultdict(int)
        self.error_patterns: Dict[str, List[datetime]] = defaultdict(list)
        self.alert_callbacks: List[Callable] = []
        self.circuit_breakers = {
            "connection": CircuitBreaker(failure_threshold=3, recovery_timeout=30),
            "trading": CircuitBreaker(failure_threshold=5, recovery_timeout=60),
            "data": CircuitBreaker(failure_threshold=10, recovery_timeout=30),
            "insufficient_funds": CircuitBreaker(failure_threshold=3, recovery_timeout=60),
            "base64_decode": CircuitBreaker(failure_threshold=5, recovery_timeout=30),
        }
        self.retry_policies = {
            "connection": RetryPolicy(max_attempts=3, base_delay=2.0),
            "trading": RetryPolicy(max_attempts=2, base_delay=1.0),
            "data": RetryPolicy(max_attempts=5, base_delay=0.5),
            "insufficient_funds": RetryPolicy(max_attempts=2, base_delay=1.0),
            "base64_decode": RetryPolicy(max_attempts=3, base_delay=1.0),
        }

    def add_alert_callback(self, callback: Callable):
        self.alert_callbacks.append(callback)

    async def record_error(
        self,
        error_type: str,
        severity: ErrorSeverity,
        category: ErrorCategory,
        message: str,
        context: Dict[str, Any] = None,
        stack_trace: str = None,
    ):
        error_event = ErrorEvent(
            timestamp=datetime.now(),
            error_type=error_type,
            severity=severity,
            category=category,
            message=message,
            context=context or {},
            stack_trace=stack_trace,
        )
        self.errors.append(error_event)
        self.error_counts[error_type] += 1
        self.error_patterns[error_type].append(error_event.timestamp)
        await self._check_alert_conditions(error_event)
        logger.error(f"[{severity.value.upper()}] {category.value}: {message}")
        return error_event

    async def _check_alert_conditions(self, error_event: ErrorEvent):
        current_time = datetime.now()
        window_start = current_time - timedelta(seconds=self.alert_window)
        recent_errors = [
            timestamp
            for timestamp in self.error_patterns[error_event.error_type]
            if timestamp >= window_start
        ]
        if len(recent_errors) >= self.alert_threshold:
            await self._trigger_alert(error_event, len(recent_errors))

    async def _trigger_alert(self, error_event: ErrorEvent, error_count: int):
        alert_data = {
            "error_type": error_event.error_type,
            "error_count": error_count,
            "time_window": self.alert_window,
            "severity": error_event.severity,
            "category": error_event.category,
            "latest_message": error_event.message,
        }
        logger.critical(
            f"ALERT: High error rate for {error_event.error_type}: "
            f"{error_count} errors in {self.alert_window}s"
        )
        for callback in self.alert_callbacks:
            try:
                await callback(alert_data)
            except Exception as e:
                logger.error(f"Alert callback failed: {e}")

    def get_error_summary(self, hours: int = 24) -> Dict[str, Any]:
        cutoff_time = datetime.now() - timedelta(hours=hours)
        recent_errors = [
            error for error in self.errors if error.timestamp >= cutoff_time
        ]
        summary = {
            "total_errors": len(recent_errors),
            "error_by_type": defaultdict(int),
            "error_by_category": defaultdict(int),
            "error_by_severity": defaultdict(int),
            "top_errors": [],
            "error_rate": len(recent_errors) / hours if hours > 0 else 0,
        }
        for error in recent_errors:
            summary["error_by_type"][error.error_type] += 1
            summary["error_by_category"][error.category.value] += 1
            summary["error_by_severity"][error.severity.value] += 1
        summary["top_errors"] = sorted(
            summary["error_by_type"].items(), key=lambda x: x[1], reverse=True
        )[:10]
        return summary

    async def execute_with_monitoring(
        self,
        func: Callable,
        operation_name: str,
        category: ErrorCategory,
        use_circuit_breaker: bool = False,
        use_retry: bool = False,
        *args,
        **kwargs,
    ):
        start_time = time.time()
        try:
            if use_circuit_breaker and category.value in self.circuit_breakers:
                circuit_breaker = self.circuit_breakers[category.value]
                if use_retry and category.value in self.retry_policies:
                    retry_policy = self.retry_policies[category.value]
                    result = await circuit_breaker.call(
                        retry_policy.execute, func, *args, **kwargs
                    )
                else:
                    result = await circuit_breaker.call(func, *args, **kwargs)
            elif use_retry and category.value in self.retry_policies:
                retry_policy = self.retry_policies[category.value]
                result = await retry_policy.execute(func, *args, **kwargs)
            else:
                result = await func(*args, **kwargs)
            duration = time.time() - start_time
            logger.debug(f"Operation '{operation_name}' completed in {duration:.3f}s")
            return result
        except Exception as e:
            duration = time.time() - start_time
            await self.record_error(
                error_type=f"{operation_name}_error",
                severity=ErrorSeverity.MEDIUM,
                category=category,
                message=str(e),
                context={
                    "operation": operation_name,
                    "duration": duration,
                    "args": str(args)[:200],
                    "kwargs": str({k: str(v)[:100] for k, v in kwargs.items()})[:200],
                },
                stack_trace=None,
            )
            raise e

class HealthChecker:
    def __init__(self, check_interval: int = 25):
        self.check_interval = check_interval
        self.health_checks: Dict[str, Callable] = {}
        self.health_status: Dict[str, Dict[str, Any]] = {}
        self._running = False
        self._health_task: Optional[asyncio.Task] = None

    def register_health_check(self, name: str, check_func: Callable):
        self.health_checks[name] = check_func

    async def start_monitoring(self):
        self._running = True
        self._health_task = asyncio.create_task(self._health_check_loop())

    async def stop_monitoring(self):
        self._running = False
        if self._health_task:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass

    async def _health_check_loop(self):
        while self._running:
            try:
                for name, check_func in self.health_checks.items():
                    try:
                        start_time = time.time()
                        result = await check_func()
                        duration = time.time() - start_time
                        self.health_status[name] = {
                            "status": "healthy" if result else "unhealthy",
                            "last_check": datetime.now(),
                            "response_time": duration,
                            "details": result if isinstance(result, dict) else {},
                        }
                    except Exception as e:
                        self.health_status[name] = {
                            "status": "error",
                            "last_check": datetime.now(),
                            "error": str(e),
                            "response_time": None,
                        }
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check loop error: {e}")
                await asyncio.sleep(self.check_interval)

    def get_health_report(self) -> Dict[str, Any]:
        overall_status = "healthy"
        unhealthy_services = []
        for service, status in self.health_status.items():
            if status["status"] != "healthy":
                overall_status = (
                    "degraded" if overall_status == "healthy" else "unhealthy"
                )
                unhealthy_services.append(service)
        return {
            "overall_status": overall_status,
            "services": self.health_status,
            "unhealthy_services": unhealthy_services,
            "timestamp": datetime.now(),
        }

error_monitor = ErrorMonitor()
health_checker = HealthChecker()

async def default_alert_handler(alert_data: Dict[str, Any]):
    logger.critical(f"ALERT: {alert_data['error_type']} - {alert_data['error_count']} errors")

error_monitor.add_alert_callback(default_alert_handler)
