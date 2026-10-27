"""Gradio web UI of the Data Onboarding Agent, started by app.py.

    views.py     HTML pieces: header, step tracker, request card, feasibility and research panels
    handlers.py  event handlers (chat, Data Team review, sessions, settings) and the shared AgentRunner
    style.py     theme and CSS
    layout.py    tabs, components, event wiring, launch()
"""
from agent.ui.layout import build_ui, launch

__all__ = ["build_ui", "launch"]
