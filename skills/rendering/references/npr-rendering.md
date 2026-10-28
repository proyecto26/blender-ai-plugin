# NPR Rendering

## Toon Shader (Shader to RGB)

```
Principled BSDF → Shader to RGB → ColorRamp (2–3 steps) → Output
Light threshold controls cel band count
```

## Outline Methods

| Method | Quality | Performance |
|--------|---------|-------------|
| Inverted hull | Good | Medium |
| Freestyle | Best control | Slow |
| Compositor edge | Post effect | Fast |

## Inverted Hull Setup

```
Solidify modifier (negative thickness)
Flip normals
Assign pure black emission material
Render on top of toon fill
```

## Rim Light in Shader

```
Fresnel (IOR 2.0) → ColorRamp → Mix into Emission
Warm rim color for stylized characters
```

## EEVEE NPR Settings (Blender 5.x)

- Bloom: compositor Glare node with `Type` = Bloom on emissive accents
- Ray tracing OFF (`eevee.use_raytracing = False`) - glossy reflections break toon bands
- Hard shadows: small sun `angle` (0.5-1 deg); `shadow_filter_radius` 0 on the key light
- View transform `Standard` so ColorRamp bands stay exact

## Stylized Style Integration

Coordinate with stylized-style skill for palette and exaggeration levels.
