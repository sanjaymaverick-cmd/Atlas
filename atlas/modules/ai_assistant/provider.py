"""Swappable inference boundary; disabled until owner hosting sign-off."""

from __future__ import annotations

from typing import Protocol

from atlas.modules.ai_assistant.schemas import ModelResult, SafePrompt


class HostingNotConfiguredError(Exception):
    pass


class InferenceProvider(Protocol):
    async def generate(self, prompt: SafePrompt) -> ModelResult: ...


class DisabledInferenceProvider:
    async def generate(self, prompt: SafePrompt) -> ModelResult:
        raise HostingNotConfiguredError("AI hosting has not received owner sign-off")
