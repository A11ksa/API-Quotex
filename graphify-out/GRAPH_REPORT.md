# Graph Report - API-Quotex  (2026-10-22)

## Corpus Check
- Corpus is ~20,342 words - fits in a single context window. You may not need a graph.

## Summary
- 444 nodes · 989 edges · 14 communities (12 shown, 2 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 48 edges (avg confidence: 0.93)
- Token cost: unavailable (semantic extraction usage metadata was not provided)

## Community Hubs (Navigation)
- Client Operations
- Domain Models and Settings
- Session Configuration
- WebSocket Transport
- Connection Keep-Alive
- Login Automation
- Orders and Candle Utilities
- Error Types
- Monitoring and Resilience
- Project Documentation
- WebSocket Batching
- Candle Cache
- Client Feature Overview
- Package Namespace

## God Nodes (most connected - your core abstractions)
1. `AsyncQuotexClient` - 92 edges
2. `AsyncWebSocketClient` - 46 edges
3. `ConnectionKeepAlive` - 33 edges
4. `Config` - 21 edges
5. `get_ssid()` - 20 edges
6. `QuotexError` - 16 edges
7. `ErrorCategory` - 15 edges
8. `ErrorSeverity` - 14 edges
9. `QuotexBot` - 14 edges
10. `ConnectionError` - 13 edges

## Surprising Connections (you probably didn't know these)
- `check_win_task()` --uses--> `AsyncQuotexClient`  [INFERRED]
  test1.py → api_quotex/client.py
- `main()` --calls--> `AsyncQuotexClient`  [EXTRACTED]
  test1.py → api_quotex/client.py
- `AsyncQuotexClient` --uses--> `Config`  [INFERRED]
  api_quotex/client.py → api_quotex/config.py
- `AsyncQuotexClient` --uses--> `ConnectionKeepAlive`  [INFERRED]
  api_quotex/client.py → api_quotex/connection_keep_alive.py
- `AsyncQuotexClient` --uses--> `AuthenticationError`  [INFERRED]
  api_quotex/client.py → api_quotex/exceptions.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Playwright Session Authentication Flow** — setup_api_quotex_setup_guide, setup_playwright_chromium_installation, setup_qxbroker_sign_in, setup_sessions_config_json, setup_sessions_session_json [EXTRACTED 1.00]

## Communities (14 total, 2 thin omitted)

### Community 0 - "Client Operations"
Cohesion: 0.06
Nodes (19): AsyncQuotexClient, Any, DataFrame, datetime, Consolidates concurrent requests per (asset,timeframe) and resolves all waiters…, Handles both history/list/v2 & chart_notification/get payloads. - Resolves the…, Robust parser for [ts, open, low, high, close, vol?] lists (order seen in…, Parse timestamp which could be a number (Unix timestamp) or a string in 'YYYY-… (+11 more)

### Community 1 - "Domain Models and Settings"
Cohesion: 0.08
Nodes (44): README.md, Repository Guidance, setup.md, test1.py Network Smoke Script, Professional Async Quotex API Client – Unified & Cleaned., ConnectionConfig, LoggingConfig, Configuration file for the async Quotex API (+36 more)

### Community 2 - "Session Configuration"
Cohesion: 0.08
Nodes (34): Config, Any, _cookies_string_to_dict(), _extract_csrf_from_signin(), _extract_session_cookie_value(), _extract_token_from_trade(), get_ssid(), load_config() (+26 more)

### Community 3 - "WebSocket Transport"
Cohesion: 0.09
Nodes (15): ConnectionInfo, ServerTime, AsyncWebSocketClient, Any, Asynchronous WebSocket client for Quotex API (Engine.IO/Socket.IO v3)., Queue outgoing Socket.IO frame and send in small batches to reduce syscalls.…, Flush pending messages after a short delay to coalesce bursts., Compatibility: rate-limited wrapper that delegates to the batched send_message. (+7 more)

### Community 4 - "Connection Keep-Alive"
Cohesion: 0.08
Nodes (11): ConnectionKeepAlive, Any, Engine.IO heartbeat: send '2' periodically; upstream will reply '3' (PONG)., Periodically request instruments list to keep local cache fresh. Uses a…, Watchdog: if connection drops, attempt a clean reconnect and resubscribe to…, Old-compat + New-compat Engine.IO / Socket.IO message handler. Old library…, Expose basic connection stats to the outer client., Regions (+3 more)

### Community 5 - "Login Automation"
Cohesion: 0.09
Nodes (27): Frame, getpass, Credentials, _extract_ssid_from_payload(), _extract_ssid_from_socketio(), main(), _print(), prompt_for_credentials() (+19 more)

### Community 6 - "Orders and Candle Utilities"
Cohesion: 0.07
Nodes (21): Return OrderResult by requestId (preferred) or broker_order_id (fallback).…, Candle, OrderResult, analyze_candles(), calculate_order_expiration(), calculate_support_resistance(), calculate_volatility(), candles_to_dataframe() (+13 more)

### Community 7 - "Error Types"
Cohesion: 0.12
Nodes (21): on_auth_error(), AssetError, AuthenticationError, Base64DecodeError, ConnectionError, InsufficientFundsError, InvalidParameterError, OrderError (+13 more)

### Community 8 - "Monitoring and Resilience"
Cohesion: 0.10
Nodes (7): CircuitBreaker, default_alert_handler(), ErrorEvent, ErrorMonitor, HealthChecker, Any, RetryPolicy

### Community 9 - "Project Documentation"
Cohesion: 0.11
Nodes (18): API-Quotex, API-Quotex README, Chromium, Demo and Live Sessions, Health Checks, Monitoring, Playwright Login, sessions/session.json (+10 more)

### Community 10 - "WebSocket Batching"
Cohesion: 0.18
Nodes (4): ConnectionPool, MessageBatcher, Batch outgoing messages to reduce WebSocket send calls under high load., Manages multiple WebSocket connections and tracks their performance statistics.

### Community 12 - "Client Feature Overview"
Cohesion: 0.40
Nodes (6): AsyncIO, AsyncQuotexClient, Market Data, Quotex WebSocket, Real-Time Candles, Trade Lifecycle

## Knowledge Gaps
- **20 isolated node(s):** `PerformanceMetrics`, `api_quotex`, `README.md`, `setup.md`, `test1.py Network Smoke Script` (+15 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 137 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **2 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `AsyncQuotexClient` connect `Client Operations` to `Domain Models and Settings`, `Session Configuration`, `WebSocket Transport`, `Connection Keep-Alive`, `Orders and Candle Utilities`, `Error Types`?**
  _High betweenness centrality (0.321) - this node is a cross-community bridge._
- **Why does `AsyncWebSocketClient` connect `WebSocket Transport` to `Client Operations`, `Domain Models and Settings`, `Session Configuration`, `Connection Keep-Alive`, `Error Types`, `WebSocket Batching`?**
  _High betweenness centrality (0.168) - this node is a cross-community bridge._
- **Why does `ConnectionKeepAlive` connect `Connection Keep-Alive` to `Client Operations`, `Domain Models and Settings`, `WebSocket Transport`?**
  _High betweenness centrality (0.128) - this node is a cross-community bridge._
- **Are the 18 inferred relationships involving `AsyncQuotexClient` (e.g. with `Config` and `ConnectionKeepAlive`) actually correct?**
  _`AsyncQuotexClient` has 18 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `AsyncWebSocketClient` (e.g. with `AsyncQuotexClient` and `ConnectionKeepAlive`) actually correct?**
  _`AsyncWebSocketClient` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `ConnectionKeepAlive` (e.g. with `AsyncQuotexClient` and `ErrorCategory`) actually correct?**
  _`ConnectionKeepAlive` has 4 INFERRED edges - model-reasoned connections that need verification._
- **What connects `PerformanceMetrics`, `api_quotex`, `README.md` to the rest of the system?**
  _20 weakly-connected nodes found - possible documentation gaps or missing edges._