"""Outbound messaging channel adapters (Facebook Messenger, …).

Each adapter is a thin delivery layer over a provider API. The chat pipeline stays
channel-agnostic; adapters only translate a reply into a provider call.
"""
