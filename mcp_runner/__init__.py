"""Standalone MCP Runner service.

A single long-lived supervisor that spawns and multiplexes stdio MCP servers on
behalf of the WebTerm backend, so MCP processes run isolated from the backend
host, are reused across tool calls (no per-call cold start), and are capped by
idle-TTL and an LRU session limit — one container instead of one-container-per-MCP.
"""
