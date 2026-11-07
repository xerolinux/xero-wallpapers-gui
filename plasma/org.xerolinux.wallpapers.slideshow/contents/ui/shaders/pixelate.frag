#version 440
layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    float progress;
    vec2 resolution;
};
layout(binding = 1) uniform sampler2D fromSource;
layout(binding = 2) uniform sampler2D toSource;

void main()
{
    float cell = max(1.0, sin(progress * 3.14159265) * 56.0);
    vec2 cells = max(resolution, vec2(1.0)) / cell;
    vec2 uv = (floor(qt_TexCoord0 * cells) + 0.5) / cells;
    float m = smoothstep(0.4, 0.6, progress);
    fragColor = mix(texture(fromSource, uv), texture(toSource, uv), m) * qt_Opacity;
}
