"""Constructor defaults used by the FX decompiler.

EFFDIR records contain the completed descriptor, so they do not record
whether a source command was omitted or explicitly supplied its default
value. The decompiler therefore produces canonical minimal source: a
command group that still matches the descriptor constructor is omitted.

The factories imported here are the executable constructor profiles. Keep
them in the model layer as the single source of truth so newly-created editor
records and decompiler comparisons cannot drift apart.
"""

from ..model.components import default_sound
from ..model.decal import default_decal
from ..model.dynamic_particle import default_dynamic_particle
from ..model.effect import default_effect_description
from ..model.light import default_light
from ..model.particle import default_particle


PARTICLE_DEFAULT = default_particle()
DECAL_DEFAULT = default_decal()
LIGHT_DEFAULT = default_light()
DYNAMIC_PARTICLE_DEFAULT = default_dynamic_particle()
SOUND_DEFAULT = default_sound()
EFFECT_DEFAULT = default_effect_description()

# MSVC debug-build fill left in the two cSC4EffectDescription words that its
# constructor does not initialize.
UNINITIALIZED_U32 = 0xCCCCCCCC
