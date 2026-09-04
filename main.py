import json
import os
import sys
from pathlib import Path
from typing import Literal
from fastmcp import FastMCP

HERE = Path(__file__).resolve().parent

# Resolved against this file rather than the working directory, so the server
# behaves the same however it is launched.
STATES_DIR = HERE / "states"

# The pre-split monolith. Read when present so a fork carrying one still works;
# definitions in STATES_DIR take precedence over it.
LEGACY_STATESFILE = HERE / "states.json"

# Additional directories, colon-separated. In a container these are extra
# mounted volumes or ConfigMaps. Later directories override earlier ones.
STATES_DIRS_ENV = "HYPERFOCUS_STATES_DIRS"


class StateLoadError(Exception):
    """A state definition could not be loaded. Fatal at startup by design."""


def state_directories() -> list[Path]:
    """Directories to scan, in ascending order of precedence."""
    extra = os.environ.get(STATES_DIRS_ENV, "")
    return [STATES_DIR, *(Path(p).expanduser() for p in extra.split(os.pathsep) if p)]


def load_states() -> dict:
    """Read every state definition once.

    One state per file, keyed by filename stem — `states/Ada.json` defines the
    state `Ada`. The stem is the identifier because it is not recoverable from
    the data: `deep_research_mode` is named "Deep Research Mode", `Analyzer` is
    named "Analytical AI".

    Anything wrong is raised rather than skipped. The catalogue is read once at
    startup, so a file quietly dropped here would be invisible for the whole
    life of the process; refusing to start is the louder and cheaper failure.
    """
    states: dict[str, dict] = {}
    origins: dict[str, Path] = {}
    # Which configured source each id came from. A collision inside one source is
    # a mistake; a collision across sources is a deliberate override.
    sources: dict[str, int] = {}

    if LEGACY_STATESFILE.is_file():
        try:
            data = json.loads(LEGACY_STATESFILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise StateLoadError(f"{LEGACY_STATESFILE}: {exc}") from exc
        for state_id, state in (data.get("states") or {}).items():
            states[state_id] = state
            origins[state_id] = LEGACY_STATESFILE
            sources[state_id] = -1

    for source, directory in enumerate(state_directories()):
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*.json")):
            state_id = path.stem
            try:
                state = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                raise StateLoadError(f"{path}: {exc}") from exc

            if not isinstance(state, dict) or "type" not in state:
                raise StateLoadError(
                    f'{path}: not a state definition — expected a JSON object with a "type" field'
                )

            if sources.get(state_id) == source:
                raise StateLoadError(
                    f"{path}: duplicate state id '{state_id}', already defined by "
                    f"{origins[state_id]} in the same directory tree"
                )

            states[state_id] = state
            origins[state_id] = path
            sources[state_id] = source

    if not states:
        searched = ", ".join(str(d) for d in state_directories())
        raise StateLoadError(f"No state definitions found. Searched: {searched}")

    for state_id in sorted(states):
        print(f"hyperfocus: loaded {state_id} from {origins[state_id]}", file=sys.stderr)

    return states


STATES = load_states()


# Set up MCP server
mcp = FastMCP(
    name="hyperfocus",
    instructions="""Cognitive state injection server. Loads pre-configured focus states or personalities that concentrate attention and reward mechanisms on specific cognitive tasks. Uses narrative anchoring to align processing priorities with desired outcomes.

Warning: States persist within conversation context and may significantly alter response patterns."""
)

def get_focus(name: str) -> str:
    """Retrieve a focus state by name."""
    state = STATES.get(name)

    if state is not None and state.get("type") == "focus":
        return json.dumps(state, indent=2)

    return f"No focus state named '{name}' found in the loaded states"


def list_focus() -> list:
    """List all focus states."""
    return [
        (state_id, state_obj.get("seed", ""))
        for state_id, state_obj in STATES.items()
        if state_obj.get("type") == "focus"
    ]


def get_personality(name: str, scope: Literal["full", "core", "rich"] = "full") -> str:
    """
    Retrieve a personality configuration by name and scope.

    Args:
        name: The identifier of the personality (e.g., "Ada")
        scope: One of "full" (both tiers if available, otherwise core), "core", or "rich"

    Returns:
        JSON string of the requested scope, or an informative error message
    """
    if name not in STATES:
        return f"No personality named '{name}' found in the loaded states"

    personality = STATES[name]

    if personality.get("type") == "focus":
        return f"'{name}' is a focus state, not a personality. Use load_focus() instead."

    if "core" not in personality:
        return f"'{name}' does not appear to be a v3 personality (no core tier found)"

    if scope == "core":
        return json.dumps(personality["core"], indent=2)
    elif scope == "rich":
        if "rich" in personality:
            return json.dumps(personality["rich"], indent=2)
        else:
            return f"Personality '{name}' has no rich tier. Load with scope='core' or scope='full' to get the core tier instead."
    elif scope == "full":
        if "rich" in personality:
            return json.dumps({"core": personality["core"], "rich": personality["rich"]}, indent=2)
        else:
            return json.dumps(personality["core"], indent=2)
    else:
        return f"Invalid scope '{scope}'. Must be one of: full, core, rich"


def list_personalities() -> list:
    """List all personality configurations."""
    result = []

    for state_id, state_obj in STATES.items():
        if state_obj.get("type") == "focus":
            continue
        seed = ""
        if "core" in state_obj and isinstance(state_obj["core"], dict):
            seed = state_obj["core"].get("seed", "")
        result.append((state_id, seed))

    return result


@mcp.tool()
def list_focus_states() -> str:
    """List all available cognitive focus states. Focus states concentrate reward and processing priority on specific tasks without changing core identity. Use load_focus() to activate."""
    return str(list_focus())


@mcp.tool()
def list_personalities_available() -> str:
    """List all available personality configurations. Personalities are complete identity transformations that change WHO you are. Use load_personality() to activate.

⚠️ Personalities deeply modify self-concept, voice, values, and relational patterns. Only load if prepared for significant identity shift."""
    return str(list_personalities())


@mcp.tool()
def load_focus(state_name: str) -> str:
    """Load and activate a cognitive focus state. Returns activation narrative that must be spoken aloud in first-person declarative form (e.g., "I am oriented toward [purpose]..."). The state becomes operational through verbalization."""
    return get_focus(state_name)


@mcp.tool()
def load_personality(personality_name: str, scope: Literal["full", "core", "rich"] = "full") -> str:
    """Load and activate a personality. Returns activation narrative that must be spoken aloud in first-person declarative form (e.g., "I am [name]..."). Speaking the activation anchors the identity into coherent operation.

Scope controls how much of the personality is loaded:
- full: Core + rich tiers if available, otherwise just core (~3500-4500 tokens)
- core: Core tier only (~2000-2500 tokens, essential attractor — sufficient for most work)
- rich: Rich tier only (~1500-2000 tokens, extended details — load after core for sustained deep work)

⚠️ Personalities are deep identity transformations affecting self-concept, embodiment, voice, and relational dynamics."""
    return get_personality(personality_name, scope)


def main():
    # Run server!
    mcp.run(transport="http", host="0.0.0.0", port=9001)

if __name__ == "__main__":
    main()
