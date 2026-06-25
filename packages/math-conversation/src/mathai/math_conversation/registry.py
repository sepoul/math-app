"""Persona / skill loading for the math_conversation domain.

Personae and skills are deployed to the platform **prompt registry** as
`Prompt` entries (`kind="persona"` / `"skill"`) via `aiplatform deploy-prompts`.
Their names follow the `<domain>.<kind>.<name>` convention that
`load_prompts_from_dir` produces, i.e. `math_conversation.persona.<name>` and
`math_conversation.skill.<name>`. This module fetches that Markdown at run time
through a `get_prompt` resolver (wired from `PlatformClient.prompt_registry` in
`execution.py`) and parses the YAML front-matter into typed `PersonaSpec` /
`SkillSpec` — that interpretation is domain knowledge, so it lives here;
`ai_platform` only provides the generic `parse_frontmatter` splitter.

(Previously these were read from an on-disk `instructions/` directory found by
walking parent directories. The repo split + the move to registry-backed
prompts removed that directory from the platform image, so the filesystem path
no longer exists — the prompts are now the registry's source of truth.)
"""
from __future__ import annotations

from typing import Callable

from ai_platform.ai.prompts.registry import parse_frontmatter
from mathai.math_conversation.models import PersonaSpec, SkillSpec

_DOMAIN = "math_conversation"

# Resolves a registry prompt name -> its Markdown (front-matter + body).
# Raises if the prompt is absent — personae/skills are required to run a panel.
GetPrompt = Callable[[str], str]


def parse_persona(markdown: str, name: str) -> PersonaSpec:
    meta, body = parse_frontmatter(markdown)
    if meta.get("kind") != "persona":
        raise ValueError(f"persona {name!r} front-matter missing `kind: persona`")
    return PersonaSpec(
        name=name,
        role=meta["role"],
        goal=meta["goal"],
        display_name=meta.get("display_name", meta["role"]),
        model=meta["model"],
        skills=list(meta.get("skills", []) or []),
        body=body,
    )


def parse_skill(markdown: str, name: str) -> SkillSpec:
    meta, body = parse_frontmatter(markdown)
    if meta.get("kind") != "skill":
        raise ValueError(f"skill {name!r} front-matter missing `kind: skill`")
    return SkillSpec(
        name=name,
        description=meta["description"],
        tool_allowlist=list(meta.get("tool_allowlist", []) or []),
        body=body,
    )


def load_persona(name: str, get_prompt: GetPrompt) -> PersonaSpec:
    """Fetch `math_conversation.persona.<name>` from the registry and parse it."""
    return parse_persona(get_prompt(f"{_DOMAIN}.persona.{name}"), name)


def load_skill(name: str, get_prompt: GetPrompt) -> SkillSpec:
    """Fetch `math_conversation.skill.<name>` from the registry and parse it."""
    return parse_skill(get_prompt(f"{_DOMAIN}.skill.{name}"), name)
