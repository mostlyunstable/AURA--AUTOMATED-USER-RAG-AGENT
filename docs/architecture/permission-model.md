# Permission Model

AURA's permission model explicitly tracks the capabilities of `Agents` and `Policies`.

**Agent**: Represents a registered worker with a subset of allowed execution traits (`capabilities`).
**Policy**: Governs what is allowed in a given Context (`allowed_capabilities`, `denied_capabilities`).

*Note: Enforcement logic and Tool Gateway integration are slated for future phases.*
