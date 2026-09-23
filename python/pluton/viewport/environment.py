"""Viewport environment: background, sky, ground, and the ink drawn against them.

Pure data. No Qt, no GL, no Scene, so the codec and headless tests can both
import it.

The ink colours live here rather than in RenderStyle because a preset that
changes the background without changing what is drawn on top of it is not a
complete preset: the pre-M7.7 edge colour was 0.85 light grey, which is
invisible on white. tests/test_environment.py holds the contrast floor that
keeps that from happening again.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Environment:
    """One viewport environment.

    Held by DocumentSettings and saved in .pluton, so it travels with the model
    rather than following the machine that opens it. Frozen and replaced
    wholesale, exactly like Units.
    """

    background: tuple[float, float, float]
    sky_enabled: bool
    sky_color: tuple[float, float, float]
    ground_enabled: bool
    ground_color: tuple[float, float, float]
    ground_opacity: float
    edge_color: tuple[float, float, float]
    grid_color: tuple[float, float, float]
    grid_centerline_color: tuple[float, float, float]


# SketchUp's modelling default: a blue sky over tan ground, meeting at the
# horizon. background is white because hidden-line faces fill with it (it is a
# separate swatch from sky in SketchUp's Styles panel for the same reason).
SKY_AND_GROUND = Environment(
    background=(1.00, 1.00, 1.00),
    sky_enabled=True,
    sky_color=(0.53, 0.71, 0.87),
    ground_enabled=True,
    ground_color=(0.72, 0.66, 0.56),
    ground_opacity=1.0,
    edge_color=(0.15, 0.15, 0.15),
    grid_color=(0.45, 0.45, 0.45),
    grid_centerline_color=(0.30, 0.30, 0.30),
)

# The documentation look: no sky, no ground, white page. sky_color and
# ground_color repeat the background rather than holding a dead value, so a
# reader does not have to wonder whether they leak.
PLAIN_WHITE = Environment(
    background=(1.00, 1.00, 1.00),
    sky_enabled=False,
    sky_color=(1.00, 1.00, 1.00),
    ground_enabled=False,
    ground_color=(1.00, 1.00, 1.00),
    ground_opacity=1.0,
    edge_color=(0.10, 0.10, 0.10),
    grid_color=(0.75, 0.75, 0.75),
    grid_centerline_color=(0.55, 0.55, 0.55),
)

# Pluton through v0.12.0, preserved exactly. Every value here was a module
# constant in scene_renderer.py, and test_studio_preset_matches_the_pre_m77_
# renderer_constants pins them, so the ink refactor is provably a no-op for a
# user who keeps this environment.
STUDIO = Environment(
    background=(0.15, 0.15, 0.18),
    sky_enabled=False,
    sky_color=(0.15, 0.15, 0.18),
    ground_enabled=False,
    ground_color=(0.15, 0.15, 0.18),
    ground_opacity=1.0,
    edge_color=(0.85, 0.85, 0.85),
    grid_color=(0.40, 0.40, 0.40),
    grid_centerline_color=(0.60, 0.60, 0.60),
)

SKY_AND_GROUND_KEY = "sky_and_ground"
PLAIN_WHITE_KEY = "plain_white"
STUDIO_KEY = "studio"

PRESETS: dict[str, Environment] = {
    SKY_AND_GROUND_KEY: SKY_AND_GROUND,
    PLAIN_WHITE_KEY: PLAIN_WHITE,
    STUDIO_KEY: STUDIO,
}

# A new document is a modelling document, so it opens in the modelling
# environment. A file written before M7.7 was authored against the dark
# background and must reopen looking the way its author left it, so the CODEC
# defaults to LEGACY_ENVIRONMENT instead. The two differ on purpose (spec D5).
DEFAULT_ENVIRONMENT = SKY_AND_GROUND
LEGACY_ENVIRONMENT = STUDIO


def preset_key(env: Environment) -> str | None:
    """The key of the preset equal to `env`, or None if no preset matches.

    Used by the View menu to decide which entry is checked after a document
    loads. None rather than an exception: a document may legitimately carry a
    value no preset matches once colour picking exists (spec D9), and refusing
    to open it would be a worse answer than leaving every entry unchecked.
    """
    for key, preset in PRESETS.items():
        if preset == env:
            return key
    return None


def environment_pass_needed(env: Environment) -> bool:
    """True when the sky/ground draw pass has anything to contribute.

    With both halves disabled, glClearColor has already painted every pixel the
    pass would paint, so running it is pure overhead. Pulled out as a function
    rather than left inline in the renderer so it can be tested headlessly.
    """
    return env.sky_enabled or env.ground_enabled
